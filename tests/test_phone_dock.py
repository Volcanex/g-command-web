"""The phone dock consumes nav data; thin shells keep the web chrome."""
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

import compile as c


ROOT = Path(__file__).resolve().parent.parent


class Links(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.links = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


def test_nav_pin_is_opt_in_for_top_level_and_group_child_links():
    pages = [
        {"slug": "index", "href": "/", "nav": True, "order": 0, "nav_pin": 1},
        {"slug": "plain", "nav": True, "order": 1},
        {"slug": "life", "nav": True, "order": 2, "tabs": "life", "web_page": False, "nav_pin": 3},
        {"slug": "calendar", "nav": False, "tabs": "life", "order": 3, "nav_pin": 2},
        {"slug": "pulse", "nav": False, "tabs": "life", "order": 4},
        {"slug": "off-rail", "nav": False, "nav_pin": 4},
    ]
    nav = c.build_nav_html(pages)
    links = {a["href"]: a for a in Links(nav).links}
    assert links["/"]["data-pin"] == "1"
    assert links["/calendar"]["data-pin"] == "2"
    assert "nav-child" in links["/calendar"]["class"].split()
    assert "data-pin" not in links["/plain"]
    assert "data-pin" not in links["/pulse"]
    assert "/off-rail" not in links
    assert nav.count("data-pin=") == 2


@pytest.mark.parametrize("pin", [0, 5, -1, "2", True, None, 1.0])
def test_nav_pin_requires_an_integer_from_one_to_four(pin):
    assert "data-pin" not in c.build_nav_html([{"slug": "page", "nav": True, "nav_pin": pin}])


def test_command_pins_preserve_the_existing_rail():
    pages = []
    for path in sorted((ROOT / "pages").glob("*/config.json")):
        config = json.loads(path.read_text())
        config.setdefault("slug", path.parent.name)
        pages.append(config)
    before = c.build_nav_html([{k: v for k, v in page.items() if k != "nav_pin"} for page in pages])
    after = c.build_nav_html(pages)
    assert re.sub(r' data-pin="[1-4]"', "", after) == before
    assert {a["href"]: a["data-pin"] for a in Links(after).links if "data-pin" in a} == {
        "/": "1", "/calendar": "2", "/studio": "3",
    }


@pytest.mark.parametrize("ua,gshell,expected", [
    ("Browser", False, False),
    ("Browser GCommandApp/1", False, True),
    ("GCommandApp/1", False, False),
    ("Browser GCommandApp/1 GShell/1", False, False),
    ("Browser GShell/1 GCommandApp/1", False, False),
    ("Browser GCommandApp/1", True, False),
    ("Browser GCommandApp/1 GShell/1", True, False),
    ("Browser", True, False),
])
def test_shell_head_hides_chrome_only_for_legacy_apps(ua, gshell, expected):
    head = (ROOT / "core/templates/shell.html").read_text().split("</head>")[0]
    script, = [s for s in re.findall(r"<script>(.*?)</script>", head, re.S) if "data-app" in s]
    runner = """
const fs = require("node:fs"), vm = require("node:vm");
const { script, ua, gshell } = JSON.parse(fs.readFileSync(0, "utf8"));
const attrs = new Set(gshell ? ["data-gshell"] : []);
vm.runInNewContext(script, {
  navigator: { userAgent: ua },
  document: { documentElement: {
    hasAttribute: name => attrs.has(name),
    setAttribute: name => attrs.add(name),
  } },
});
process.stdout.write(JSON.stringify(attrs.has("data-app")));
"""
    result = subprocess.run(["node", "-e", runner],
                            input=json.dumps({"script": script, "ua": ua, "gshell": gshell}),
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) is expected


def test_shell_exposes_safe_area_insets():
    head = (ROOT / "core/templates/shell.html").read_text().split("</head>")[0]
    viewport, = re.findall(r'<meta name="viewport" content="([^"]+)">', head)
    assert {part.strip() for part in viewport.split(",")} == {
        "width=device-width", "initial-scale=1", "viewport-fit=cover",
    }
