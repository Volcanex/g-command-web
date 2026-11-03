import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

import compile as compiler
from core.panels import layout
from core.panels.manifest import build_manifest


PAGES = Path(__file__).resolve().parent.parent / "pages"


class Navigation(HTMLParser):
    """The rail as data: sections of top-level entries, each nav-child link
    nested under the entry before it."""
    def __init__(self):
        super().__init__()
        self.sections = []
        self.link = None
        self.capture = None
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and "nav-head" in (attrs.get("class") or "").split():
            self.capture = "section"
            self.text = ""
        if tag == "a":
            self.capture = "link"
            self.text = ""
            self.link = {"slug": attrs["href"].lstrip("/"), "child": "nav-child" in attrs["class"].split()}
        if tag == "i" and self.link:
            self.link["icon"] = attrs["class"].split("ph-")[-1]

    def handle_data(self, data):
        if self.capture:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "div" and self.capture == "section":
            self.sections.append({"title": self.text, "entries": []})
            self.capture = None
        if tag == "a" and self.link:
            link, self.link = self.link, None
            link["label"] = self.text
            self.capture = None
            entries = self.sections[-1]["entries"]
            if link.pop("child"):
                entries[-1].setdefault("children", []).append({"slug": link["slug"], "label": link["label"]})
            else:
                entries.append(link)


def configs(pages):
    result = []
    for page in sorted(pages.iterdir()):
        if page.is_dir() and not page.name.startswith("_") and (page / "config.json").is_file():
            try:
                config = json.loads((page / "config.json").read_text())
            except json.JSONDecodeError:
                continue
            config.setdefault("slug", page.name)
            result.append(config)
    return result


def check_navigation(pages):
    """The apps' manifest and the web rail come from one tree: the same
    sections and entries, and an entry's tabs (less itself) are its nested
    children in the rail. The rail's own extras (web_nav, app_nav) aside."""
    manifest = build_manifest(pages)
    source = configs(pages)
    parser = Navigation()
    # app_nav false is a web-only entry (Home, Chat): the apps leave it out;
    # web_nav false (Full dash) is the reverse, so compare the tree without both.
    parser.feed(compiler.build_nav_html([dict(c, web_nav=True) for c in source if c.get("app_nav", True)]))
    actual = []
    for section in manifest["sections"]:
        entries = []
        for entry in section["entries"]:
            row = {key: entry[key] for key in ("slug", "label", "icon")}
            kids = [{"slug": tab["slug"], "label": tab["label"]} for tab in entry.get("tabs", []) if tab["slug"] != entry["slug"]]
            if kids:
                row["children"] = kids
            entries.append(row)
        actual.append({"title": section["title"], "entries": entries})
    assert actual == parser.sections
    return manifest


def test_manifest_matches_real_sidebar_and_tabs():
    manifest = check_navigation(PAGES)
    assert manifest["v"] == 1
    assert manifest["name"] == "G-Command"
    assert manifest["panels"] == {
        "calendar": {"title": "Today", "icon": "calendar-blank"},
        "brief": {"title": "Brief", "icon": "sun-horizon"},
        "agenda": {"title": "This week", "icon": "calendar-check"},
        "tasks": {"title": "Undated", "icon": "check-square"},
        "money": {"title": "Money", "icon": "wallet"},
        "health": {"title": "Health", "icon": "heartbeat"},
        "compute": {"title": "Compute", "icon": "gauge"},
        "tickets": {"title": "Tickets", "icon": "ticket"},
        "crons": {"title": "Crons", "icon": "clock"},
    }
    # Overview first: the apps take the first section as their dash (Life, System, Full dash)
    assert [section["title"] for section in manifest["sections"]] == ["Overview", "Work", "Knowledge", "Publish", "Setup"]
    assert [entry["slug"] for entry in manifest["sections"][0]["entries"]] == ["home", "ops", "full-dash"]


def test_manifest_defaults_ties_tabs_panel_flags_and_bad_configs(tmp_path):
    data = {
        "a": {"title": "Alpha & tools", "nav": True, "order": 3, "tabs": 5, "panels": ["money"]},
        "b": {"title": "Beta", "nav": True, "order": 3, "nav_section": "Together", "nav_label": "B <label>"},
        "c": {"title": "Charlie", "nav": True, "order": 1, "nav_section": "Together", "nav_icon": "clock"},
        "d": {"title": "Hidden tab", "nav": False, "order": 0, "tabs": "5", "tab_label": "First & tab", "panels": []},
        "e": {"title": "Last tab", "nav": False, "tabs": 5, "nav_label": "Last"},
        "_ignored": {"nav": True, "order": -10},
    }
    for slug, config in data.items():
        (tmp_path / slug).mkdir()
        (tmp_path / slug / "config.json").write_text(json.dumps(config))
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "config.json").write_text("{broken")
    (tmp_path / "missing").mkdir()
    (tmp_path / "file").write_text("not a page")
    manifest = check_navigation(tmp_path)
    assert [section["title"] for section in manifest["sections"]] == ["Together", "Alpha & tools"]
    entry = manifest["sections"][1]["entries"][0]
    assert entry == {"slug": "a", "label": "Alpha & tools", "icon": "circle", "panels": ["money"], "tabs": [
        {"slug": "d", "label": "First & tab", "panels": []},
        {"slug": "a", "label": "Alpha & tools", "panels": ["money"]},
        {"slug": "e", "label": "Last"}]}
    assert "panels" not in manifest["sections"][0]["entries"][0]


@pytest.mark.parametrize("slug", ["home", "ops", "full-dash"])
def test_dash_layout_order_matches_compiled_tokens_and_manifest(slug, tmp_path, monkeypatch):
    page = PAGES / slug
    config = json.loads((page / "config.json").read_text())
    order = layout.panels(config["layout"])
    content = (page / "content.html").read_text().replace("<!-- seed:dash-layout -->", layout.render(slug, config["layout"]))
    tokens = re.findall(r"<!--\s*seed:panel-([\w-]+)\s*-->", content)
    assert order == [token for token in tokens if token != "kit"]
    manifest = build_manifest(PAGES)
    entry = next(entry for section in manifest["sections"] for entry in section["entries"] if entry["slug"] == slug)
    assert entry["panels"] == order
    assert entry["layout"] == layout.normalise(config["layout"])
    if slug == "ops":
        assert next(tab for tab in entry["tabs"] if tab["slug"] == "ops")["panels"] == order


@pytest.mark.parametrize("slug", ["home", "ops", "full-dash"])
def test_compile_accepts_panel_configs_unchanged(slug, tmp_path, monkeypatch):
    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path)
    path, config, error = compiler.compile_page(PAGES / slug, "{{! content }}")
    assert not error
    assert path.is_file()
    assert config == json.loads((PAGES / slug / "config.json").read_text())
    assert "seed:panel-" not in path.read_text()
