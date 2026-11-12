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
    """The rail as data: sections of top-level entries (the first, the rail's
    top, has no heading), a group as an entry with its nav-child links nested
    under it. A group is a button, not a link: `slug` is None."""
    def __init__(self):
        super().__init__()
        self.sections = [{"title": None, "entries": []}]
        self.link = None
        self.capture = None
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = (attrs.get("class") or "").split()
        if tag == "div" and "nav-head" in cls:
            self.capture = "section"
            self.text = ""
        if tag == "a" or (tag == "button" and "nav-group-toggle" in cls):
            self.capture = "link"
            self.text = ""
            self.link = {"slug": attrs["href"].lstrip("/") if tag == "a" else None, "child": "nav-child" in cls,
                         "group": tag == "button"}
        if tag == "i" and self.link:
            self.link["icon"] = attrs["class"].split("ph-")[-1]

    def handle_data(self, data):
        if self.capture:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "div" and self.capture == "section":
            self.sections.append({"title": self.text, "entries": []})
            self.capture = None
        if tag in ("a", "button") and self.link:
            link, self.link = self.link, None
            link["label"] = self.text
            self.capture = None
            entries = self.sections[-1]["entries"]
            group = link.pop("group")
            if link.pop("child"):
                entries[-1].setdefault("children", []).append(link)
            else:
                if group:
                    link["children"] = []
                entries.append(link)


def moved():
    """server.py MOVED, read without importing the server (its import sets up
    state other tests' contexts would then see)."""
    import ast
    tree = ast.parse((PAGES.parent / "server.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MOVED")
    return ast.literal_eval(node.value)


def rail(configs_):
    parser = Navigation()
    parser.feed(compiler.build_nav_html(configs_))
    return [s for s in parser.sections if s["entries"] or s["title"]]


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
    """The apps' manifest and the web rail come from one tree. The web rail
    differs only where a config says so: a group is a disclosure row whose
    own page leads its children unless `web_page` is false (then server.py
    MOVED sends the URL on), `web_section`/`web_order` move an entry on the
    web only, and app_nav/web_nav keep an entry to one side. So every page
    the apps can open is on the web rail, or is a group whose URL moved."""
    manifest = build_manifest(pages)
    source = {c["slug"]: c for c in configs(pages)}
    web = rail([dict(c, web_nav=True) for c in source.values()])
    links = {e["slug"] for s in web for e in s["entries"] for e in [e, *e.get("children", [])] if e["slug"] is not None}
    groups = {e["label"]: e for s in web for e in s["entries"] if e["slug"] is None}
    for section in manifest["sections"]:
        for entry in section["entries"]:
            for page in [entry, *entry.get("tabs", [])]:
                config = source[page["slug"]]
                if config.get("web_page", True) is False:
                    assert page["slug"] in moved(), page["slug"]
                else:
                    assert compiler.page_href(config).lstrip("/") in links, page["slug"]
            if entry.get("tabs"):
                group = groups[entry["label"]]
                assert group["icon"] == entry["icon"]
                kids = [t["slug"] for t in entry["tabs"] if source[t["slug"]].get("web_page", True)]
                assert sorted(k["slug"] for k in group["children"] if k["slug"] in kids) == sorted(kids)
    for section in web:
        for entry in section["entries"]:
            for child in entry.get("children", []):
                assert child.get("icon") and child["icon"] != "circle", child
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


def test_web_rail_puts_what_is_needed_at_the_top_and_nests_the_rest():
    """g-navigation: Home (the full dash), Studio, Upload, Life, System at the
    top with no heading, then the other sections; groups are open disclosure
    rows, never pages, and every child carries its own icon."""
    web = rail(configs(PAGES))
    assert [s["title"] for s in web] == [None, "Work", "Knowledge", "Publish", "Setup", "Additional tools"]
    top = web[0]["entries"]
    assert [(e["slug"], e["label"]) for e in top] == [("", "Home"), ("studio", "Studio"), ("upload", "Upload"), (None, "Life"), (None, "System")]
    assert [k["slug"] for k in top[3]["children"]] == ["calendar", "pulse"]
    assert [k["slug"] for k in top[4]["children"]] == ["diagram", "system", "compute", "crons", "tickets", "projects", "levels", "alerts"]
    brain = [e for e in web[2]["entries"] if e["label"] == "Brain"][0]
    assert brain["slug"] is None and [k["slug"] for k in brain["children"]][:2] == ["graph", "notes"]
    setup = web[4]["entries"][0]
    assert setup["slug"] is None and [k["label"] for k in setup["children"]] == ["Bootstrap", "Install", "Passport"]
    design = [e for e in web[1]["entries"] if e["label"] == "Design"][0]
    assert design["slug"] is None and [(k["slug"], k["label"]) for k in design["children"]] == [("design", "Language"), ("showcase", "Showcase")]
    research = [e for e in web[2]["entries"] if e["label"] == "Research"][0]
    assert research["slug"] is None and [k["slug"] for k in research["children"]] == [
        "research/thesis", "research/making-ladder", "research/ans", "research/dissertation"]
    html = compiler.build_nav_html(configs(PAGES))
    assert html.count('class="nav-group"') == 7 and html.count("data-open") == 7
    assert "hub" not in html and 'class="nav-twist"' not in html


def test_nav_pins_match_the_command_rail_without_other_markup_changes():
    pages = configs(PAGES)
    html = compiler.build_nav_html(pages)
    assert dict(re.findall(r'<a class="[^"]*" href="([^"]*)" data-pin="([1-4])"', html)) == {
        "/": "1", "/calendar": "2", "/studio": "3", "/upload": "4"}
    assert '<a class="nav-item nav-child" href="/calendar" data-pin="2">' in html
    unpinned = [{k: v for k, v in page.items() if k != "nav_pin"} for page in pages]
    assert re.sub(r' data-pin="[1-4]"', "", html) == compiler.build_nav_html(unpinned)


def test_nav_emits_pins_and_escaped_dock_labels_on_links_only():
    pages = [
        {"slug": "top", "nav": True, "nav_pin": 1, "dock_label": 'Top & "<place>"'},
        {"slug": "group", "nav": True, "tabs": "group", "nav_pin": 2, "dock_label": "Group"},
        {"slug": "child", "nav": False, "tabs": "group", "nav_pin": 3, "dock_label": 'Child\'s & "place"'},
        {"slug": "other", "nav": True, "dock_label": "Other"},
    ]
    html = compiler.build_nav_html(pages)
    assert '<a class="nav-item" href="/top" data-pin="1" data-dock-label="Top &amp; &quot;&lt;place&gt;&quot;">' in html
    assert '<a class="nav-item nav-child" href="/group" data-pin="2" data-dock-label="Group">' in html
    assert '<a class="nav-item nav-child" href="/child" data-pin="3" data-dock-label="Child&#x27;s &amp; &quot;place&quot;">' in html
    assert '<a class="nav-item" href="/other" data-dock-label="Other">' in html
    plain = [{k: v for k, v in page.items() if k not in ("nav_pin", "dock_label")} for page in pages]
    assert re.sub(r' data-(?:pin|dock-label)="[^"]*"', "", html) == compiler.build_nav_html(plain)


@pytest.mark.parametrize("pin", [0, 5, -1, 1.0, "1", True, False, None, [], {}])
def test_nav_rejects_invalid_pin_values(pin):
    with pytest.raises(ValueError, match="bad: nav_pin must be an integer from 1 to 4"):
        compiler.build_nav_html([{"slug": "bad", "nav": True, "nav_pin": pin}])


def test_nav_rejects_duplicate_pins_across_top_level_and_child_links():
    with pytest.raises(ValueError, match="nav_pin 1 is shared by pages 'top' and 'child'"):
        compiler.build_nav_html([
            {"slug": "top", "nav": True, "nav_pin": 1},
            {"slug": "group", "nav": True, "tabs": "group", "web_page": False},
            {"slug": "child", "nav": False, "tabs": "group", "nav_pin": 1},
        ])


@pytest.mark.parametrize("pages", [
    [{"slug": "hidden", "nav": False, "nav_pin": 1}],
    [{"slug": "hidden", "nav": True, "web_nav": False, "nav_pin": 1}],
    [{"slug": "hidden", "nav": False, "tabs": "missing", "nav_pin": 1}],
    [{"slug": "group", "nav": True, "tabs": "group", "web_nav": False},
     {"slug": "hidden", "nav": False, "tabs": "group", "nav_pin": 1}],
    [{"slug": "hidden", "nav": True, "tabs": "group", "web_page": False, "nav_pin": 1},
     {"slug": "child", "nav": False, "tabs": "group"}],
])
def test_nav_rejects_pins_on_pages_without_a_rail_link(pages):
    with pytest.raises(ValueError, match="hidden: nav_pin is set on a page that is not on the rail"):
        compiler.build_nav_html(pages)


def test_compile_exits_with_a_clear_pin_error(tmp_path, monkeypatch):
    pages = tmp_path / "pages"
    page = pages / "bad"
    page.mkdir(parents=True)
    (page / "config.json").write_text(json.dumps({"nav": True, "nav_pin": 5}))
    monkeypatch.setattr(compiler, "PAGES_DIR", pages)
    monkeypatch.setattr(compiler, "OUTPUT_DIR", tmp_path / "output")
    with pytest.raises(SystemExit, match="ERROR: bad: nav_pin must be an integer from 1 to 4"):
        compiler.main()


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
    (tmp_path / "d" / "config.json").write_text(json.dumps(dict(data["d"], nav_icon="clock")))
    (tmp_path / "e" / "config.json").write_text(json.dumps(dict(data["e"], nav_icon="clock")))
    (tmp_path / "a" / "config.json").write_text(json.dumps(dict(data["a"], tab_icon="clock")))
    manifest = check_navigation(tmp_path)
    assert [section["title"] for section in manifest["sections"]] == ["Together", "Alpha & tools"]
    # the web rail: the first section is the top, unheaded; a group leads with its own page
    web = rail(configs(tmp_path))
    assert [s["title"] for s in web] == [None, "Alpha & tools"]
    group = web[1]["entries"][0]
    assert group["slug"] is None and [k["slug"] for k in group["children"]] == ["a", "d", "e"]
    entry = manifest["sections"][1]["entries"][0]
    assert entry == {"slug": "a", "label": "Alpha & tools", "icon": "circle", "panels": ["money"], "tabs": [
        {"slug": "d", "label": "First & tab", "icon": "clock", "panels": []},
        {"slug": "a", "label": "Alpha & tools", "icon": "circle", "panels": ["money"]},
        {"slug": "e", "label": "Last", "icon": "clock"}]}
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
