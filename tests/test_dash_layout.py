"""The dash layout has one source: `layout` in a panel page's config.json.

The web compiles it, the manifest serves it to the Mac app. A dash whose
placement is written by hand in content.html drifts from the app.
"""
import json
import re
from pathlib import Path

import pytest

from core.panels import PANELS, layout
from core.panels.manifest import build_manifest

PAGES = Path(__file__).resolve().parent.parent / "pages"
CONFIGS = {page.name: json.loads((page / "config.json").read_text())
           for page in sorted(PAGES.iterdir()) if (page / "config.json").is_file()}
DASHES = sorted(slug for slug, config in CONFIGS.items() if "layout" in config)


def test_dashes_exist():
    assert DASHES == ["full-dash", "home", "ops"]


@pytest.mark.parametrize("slug", sorted(CONFIGS))
def test_no_hand_placed_dash(slug):
    content = (PAGES / slug / "content.html").read_text() if (PAGES / slug / "content.html").is_file() else ""
    assert not re.search(r'class="[^"]*\bfd-(dash|col|row)\b', content), "dash placement belongs in config.json layout"
    assert "panels" not in CONFIGS[slug], "panel order comes from layout"
    if slug in DASHES:
        assert content == "<!-- seed:panel-kit -->\n<!-- seed:dash-layout -->\n"


@pytest.mark.parametrize("slug", DASHES)
def test_layout_shape(slug):
    spec = CONFIGS[slug]["layout"]
    assert set(spec) <= {"top", "columns"}
    assert spec["columns"]
    names = layout.panels(spec)
    assert len(names) == len(set(names))
    assert set(names) <= set(PANELS)
    for column in spec["columns"]:
        assert set(column) <= {"width", "min", "items"}
        for item in column["items"]:
            item = {"panel": item} if isinstance(item, str) else item
            assert set(item) <= {"panel", "row", "grow", "fit", "shrink", "max"}
            assert ("panel" in item) != ("row" in item)
            assert not (item.get("fit") and "grow" in item)
            assert "shrink" not in item or item.get("fit")


@pytest.mark.parametrize("slug", DASHES)
def test_render_places_every_panel_once(slug):
    spec = CONFIGS[slug]["layout"]
    html = layout.render(slug, spec)
    assert re.findall(r"seed:panel-([\w-]+)", html) == layout.panels(spec)
    assert html.count('class="fd-col"') == len(spec["columns"])


def test_manifest_serves_every_dash_layout():
    entries = [entry for section in build_manifest(PAGES)["sections"] for entry in section["entries"]]
    entries += [tab for entry in entries for tab in entry.get("tabs", [])]
    served = {entry["slug"]: entry for entry in entries if "layout" in entry}
    assert set(served) == set(DASHES)
    for slug, entry in served.items():
        assert entry["layout"] == layout.normalise(CONFIGS[slug]["layout"])
        for column in entry["layout"]["columns"]:
            assert {"width", "min", "items"} <= set(column)
