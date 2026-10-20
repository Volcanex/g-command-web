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
    def __init__(self):
        super().__init__()
        self.sections = []
        self.links = []
        self.capture = None
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h3":
            self.capture = "section"
            self.text = ""
        if tag == "a":
            self.capture = "link"
            self.text = ""
            self.links.append({"slug": attrs["href"].lstrip("/")})
        if tag == "i" and self.links:
            self.links[-1]["icon"] = attrs["class"].split("ph-")[-1]

    def handle_data(self, data):
        if self.capture:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "h3":
            self.sections.append({"title": self.text, "entries": []})
            self.capture = None
        if tag == "a":
            self.links[-1]["label"] = self.text
            if self.sections:
                self.sections[-1]["entries"].append(self.links[-1])
            self.capture = None


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
    manifest = build_manifest(pages)
    source = configs(pages)
    parser = Navigation()
    parser.feed(compiler.build_nav_html(source))
    actual = [{"title": section["title"], "entries": [
        {key: entry[key] for key in ("slug", "label", "icon")} for entry in section["entries"]]}
        for section in manifest["sections"]]
    assert actual == parser.sections
    subnavs = compiler.build_subnavs(source)
    for section in manifest["sections"]:
        for entry in section["entries"]:
            if entry["slug"] in subnavs:
                parser = Navigation()
                parser.feed(subnavs[entry["slug"]])
                assert [{"slug": tab["slug"], "label": tab["label"]} for tab in entry["tabs"]] == parser.links
            else:
                assert "tabs" not in entry
    return manifest


def test_manifest_matches_real_sidebar_and_tabs():
    manifest = check_navigation(PAGES)
    assert manifest["v"] == 1
    assert manifest["name"] == "G-Command"
    assert manifest["panels"] == {
        "calendar": {"title": "Today", "icon": "calendar-blank"},
        "brief": {"title": "Brief", "icon": "sun-horizon"},
        "tasks": {"title": "Todos", "icon": "check-square"},
        "money": {"title": "Money", "icon": "wallet"},
        "health": {"title": "Health", "icon": "heartbeat"},
        "compute": {"title": "Compute", "icon": "gauge"},
        "tickets": {"title": "Tickets", "icon": "ticket"},
        "crons": {"title": "Crons", "icon": "clock"},
    }
    assert [section["title"] for section in manifest["sections"]] == ["Dash", "Daily", "Tools"]


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
