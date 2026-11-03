"""Todos merged into the calendar (2026-11-03): one view, every item dated,
the essentials line from the brain's agenda with a fallback to the calendar
feed, and /todos a permanent redirect."""
import json
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

import pytest

from core.panels import agenda, layout
from core.panels.helpers import TZ
from core.panels.manifest import build_manifest

PAGES = Path(__file__).resolve().parent.parent / "pages"
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=TZ)  # a Monday
CAL = "/api/todos/calendar?date_from=2026-10-19&date_to=2026-10-26"
AGENDA = "/api/todos/agenda"


class Ctx:
    def __init__(self, sources):
        self.sources, self.now, self.calls = sources, NOW, []

    def get(self, path):
        self.calls.append(path)
        value = self.sources[path]
        if isinstance(value, Exception):
            raise value
        return value


def item(slug, date, **kw):
    return {"slug": slug, "title": kw.pop("title", slug), "date": date, **kw}


def lines(panel):
    return [i["text"] for i in panel["blocks"][0]["items"]]


def not_found():
    return HTTPError(AGENDA, 404, "Not Found", {}, None)


def test_agenda_uses_the_brain_lines_when_live_and_caps_them_at_three():
    panel = agenda.build(Ctx({AGENDA: {"lines": ["**Today**: A", "B", "C", "D"], "today": []}}))
    assert panel["state"] == "ok" and panel["source"] == "agenda"
    assert lines(panel) == ["Today: A", "B", "C"]
    assert panel["meta"] == "Today: A"


def test_agenda_shows_the_brain_failure_line_never_a_blank():
    panel = agenda.build(Ctx({AGENDA: {"lines": ["Calendar unavailable: store unreadable"]}}))
    assert lines(panel) == ["Calendar unavailable: store unreadable"]


def test_agenda_with_nothing_due_still_says_so():
    assert lines(agenda.build(Ctx({AGENDA: {"lines": []}}))) == ["Nothing due this week."]


def test_agenda_falls_back_to_the_calendar_feed_until_the_endpoint_is_live():
    feed = [
        item("late", "2026-10-19", title="Book the boiler service", late_days=3),
        item("habit", "2026-10-19", recurring=True),
        item("dentist", "2026-10-19", time="09:30"),
        item("ticked", "2026-10-19", done=True),
        item("chatgpt", "2026-10-21", title="ChatGPT £118.34", category="finance", recurring=True),
        item("proxies", "2026-10-20", title="Webshare proxies £7.24", category="finance"),
        item("rent", "2026-10-20", title="Rent", category="finance", amount=950),
        item("call", "2026-10-20", title="Call Kumar"),
    ]
    ctx = Ctx({AGENDA: not_found(), CAL: feed})
    panel = agenda.build(ctx)
    assert ctx.calls == [AGENDA, CAL]
    assert panel["source"] == "calendar"
    assert lines(panel) == [
        "Overdue: Book the boiler service",
        "Today: dentist",
        "Bills: Rent tomorrow, ChatGPT £118.34 Wed",
    ]


def test_agenda_reports_a_failure_line_when_both_sources_fail():
    panel = agenda.build(Ctx({AGENDA: not_found(), CAL: TimeoutError("private http://brain")}))
    assert panel["state"] == "ok" and panel["source"] == "error"
    assert lines(panel) == ["Calendar unavailable: the brain did not answer."]
    assert "private" not in json.dumps(panel)


def test_todos_page_is_gone_and_life_holds_calendar_first():
    assert not (PAGES / "todos").exists()
    sections = build_manifest(PAGES)["sections"]
    life = [e for s in sections for e in s["entries"] if e["slug"] == "home"][0]
    assert [t["slug"] for t in life.get("tabs", [])][:2] == ["home", "calendar"]  # the apps' Life dash, unchanged
    assert "todos" not in json.dumps(sections)


def test_home_is_the_full_dash_under_the_agenda_card():
    index = json.loads((PAGES / "index" / "config.json").read_text())
    full = json.loads((PAGES / "full-dash" / "config.json").read_text())
    assert index["layout"] == full["layout"]
    content = (PAGES / "index" / "content.html").read_text()
    assert content.index('data-lines="agenda"') < content.index("seed:dash-layout")
    assert "page-title" not in content and "seed:hub-" not in content  # the top bar already says Home


def test_calendar_page_lists_by_default_with_tick_move_and_a_dated_create_form():
    src = (PAGES / "calendar" / "content.html").read_text()
    assert 'name="date" required' in src and 'type="time" name="time"' in src
    assert 'value="list" checked' in src and "view') === 'month'" in src
    for bucket in ("'Overdue'", "'Today'", "'Tomorrow'", "'This week'", "'Later'"):
        assert bucket in src
    assert "reschedule_to" in src and 'data-act="tick"' in src and "done_date" in src
    assert "\u2014" not in src and "\u00b7" not in src

