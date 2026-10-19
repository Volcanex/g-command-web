import copy
import importlib
import io
import json
from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from core.api import panels as api
from core.panels import PANELS, build
from core.panels.context import Context
from core.panels.helpers import TZ, chip, day, fixed, london, plain, rel, rounded, span


NOW = datetime(2026, 10, 19, 12, 0, tzinfo=TZ)
CALENDAR_PATH = "/api/todos/calendar?date_from=2026-10-19&date_to=2026-10-25"
CALENDAR_ERROR = {"title": "Not saved", "desc": "The brain did not accept the change. Try again from the calendar."}
SOURCES = {
    "calendar": CALENDAR_PATH,
    "brief": "/api/pulse/brief",
    "tasks": "/api/todos?status=open",
    "money": "/api/todos?status=open",
    "health": "/api/status",
    "compute": "/api/compute/pace",
    "tickets": "/api/gadmin_panel/tickets?status=open",
    "crons": "/api/crons/list",
}
ERRORS = {
    "calendar": "Calendar unavailable. The panel retries every 5 minutes.",
    "brief": "Brief unavailable. The panel retries every 10 minutes.",
    "tasks": "Todos unavailable. The panel retries every 5 minutes.",
    "money": "Money unavailable. The panel retries every 5 minutes.",
    "health": "Health unavailable. The panel retries every minute.",
    "compute": "Compute unavailable. The panel retries every 5 minutes.",
    "tickets": "Tickets unavailable. The panel retries every 2 minutes.",
    "crons": "Crons unavailable. The panel retries every 5 minutes.",
}


class FixtureContext:
    def __init__(self, sources, now=NOW):
        self.sources = sources
        self.now = now.astimezone(TZ)
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        value = self.sources[path]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


def expected(name, **fields):
    title, icon, link, label, refresh, _ = PANELS[name]
    return {"v": 1, "id": name, "title": title, "icon": icon, "link": link,
            "link_label": label, "meta": "", "state": "ok", "message": "",
            "refresh": refresh, "blocks": [], **fields}


def todo(slug, **fields):
    return {"slug": slug, "permalink": "todos/" + slug, "title": slug, **fields}


def test_tasks_groups_without_reordering_within_priority():
    items = [todo("fallback", priority="other"), todo("second", priority="P1", vital=True),
             todo("first", priority="P0", title="**First** [[work|job]]"),
             todo("third", priority="P1"), todo("dated", due="2026-10-20"),
             todo("started", start="2026-10-20"), todo("bill", category="bill"),
             todo("finance", category="finance"), todo("p2", priority="P2"), todo("missing")]
    ctx = FixtureContext({SOURCES["tasks"]: items})
    assert build("tasks", ctx) == expected("tasks", meta="6 undated", blocks=[
        {"type": "rows", "title": "P0 1", "rows": [
            {"id": "first", "title": "First job", "link": "/note/todos/first", "accent": "danger"}]},
        {"type": "rows", "title": "P1 2", "rows": [
            {"id": "second", "title": "second", "link": "/note/todos/second", "accent": "warn",
             "marks": [{"text": "Vital", "tone": "danger"}]},
            {"id": "third", "title": "third", "link": "/note/todos/third", "accent": "warn"}]},
        {"type": "rows", "title": "P2 1", "rows": [
            {"id": "p2", "title": "p2", "link": "/note/todos/p2", "accent": "accent"}]},
        {"type": "rows", "title": "P3 2", "rows": [
            {"id": "fallback", "title": "fallback", "link": "/note/todos/fallback", "accent": "muted"},
            {"id": "missing", "title": "missing", "link": "/note/todos/missing", "accent": "muted"}]},
    ])
    assert ctx.calls == [SOURCES["tasks"]]


def test_money_orders_dates_then_priority_and_title():
    items = [todo("undated-z", category="finance", priority="P1"),
             todo("today", category="bill", due="2026-10-19"),
             todo("tomorrow", category="bill", due="2026-10-20"),
             todo("late", category="finance", due="2026-10-18"),
             todo("earlier", category="bill", due="2026-10-16"),
             todo("undated-a", category="bill", priority="P1"),
             todo("undated-p0", category="bill", priority="P0"), todo("not-money")]
    rows = [
        {"id": "earlier", "title": "earlier", "link": "/note/todos/earlier", "trail": {"text": "3 days late", "tone": "danger"}},
        {"id": "late", "title": "late", "link": "/note/todos/late", "trail": {"text": "1 day late", "tone": "danger"}},
        {"id": "today", "title": "today", "link": "/note/todos/today", "trail": {"text": "Today", "tone": "warn"}},
        {"id": "tomorrow", "title": "tomorrow", "link": "/note/todos/tomorrow", "trail": {"text": "Tue 20 Oct", "tone": "muted"}},
        {"id": "undated-p0", "title": "undated-p0", "link": "/note/todos/undated-p0"},
        {"id": "undated-a", "title": "undated-a", "link": "/note/todos/undated-a"},
        {"id": "undated-z", "title": "undated-z", "link": "/note/todos/undated-z"},
    ]
    assert build("money", FixtureContext({SOURCES["money"]: items})) == expected(
        "money", meta="7 open, 2 late", blocks=[{"type": "rows", "rows": rows}])


def test_brief_stops_at_workings_and_skips_services_and_promotions():
    data = {"date": "2026-10-19", "body": "# Brief\n\n- **Services:** stale count\n- **Overdue:** [[pay|Pay tax]]\nA plain fact.\nPromote to brain? one\n- Promote to brain? two\n## Working\n- Never shown"}
    assert build("brief", FixtureContext({SOURCES["brief"]: data})) == expected(
        "brief", meta="Mon 19 Oct", blocks=[{"type": "bullets", "items": [
            {"label": "Overdue", "text": "Pay tax"}, {"text": "A plain fact."},
            {"text": "2 notes waiting to go into the brain", "link": "/pulse"}]}])


def test_brief_one_promotion_and_long_colon_prefix():
    text = "A prefix longer than forty characters stays: whole\nPromote to brain? this"
    body = build("brief", FixtureContext({SOURCES["brief"]: {"body": text}}))
    assert body["blocks"][0]["items"] == [
        {"text": "A prefix longer than forty characters stays: whole"},
        {"text": "1 note waiting to go into the brain", "link": "/pulse"}]


@pytest.mark.parametrize("line,item", [
    ("- **Money:** [[bills|Pay bills]]: today", {"label": "Money", "text": "Pay bills: today"}),
    ("A" * 39 + ": fact", {"label": "A" * 39, "text": "fact"}),
    ("A" * 40 + ": fact", {"text": "A" * 40 + ": fact"}),
    (": no lead", {"text": ": no lead"}), ("Money:", {"label": "Money", "text": ""}),
])
def test_brief_bold_label_uses_the_same_colon_boundary_as_javascript(line, item):
    result = build("brief", FixtureContext({SOURCES["brief"]: {"body": line}}))
    assert result["blocks"] == [{"type": "bullets", "items": [item]}]


def calendar_row(slug, **fields):
    return {"id": slug + ":2026-10-19", "title": slug, "link": "/note/todos/" + slug,
            "done": False, "struck": False, "accent": "muted", "title_tone": "plain",
            "action": {"label": "Mark done", "method": "PATCH", "path": "/api/brain/api/todos/" + slug,
                       "body": {"status": "done"}, "error": CALENDAR_ERROR}, **fields}


def next_days():
    return [{"type": "rows", "title": label, "empty": "Nothing planned", "rows": []} for label in
            ("Tue 20 Oct", "Wed 21 Oct", "Thu 22 Oct", "Fri 23 Oct", "Sat 24 Oct", "Sun 25 Oct")]


def test_calendar_today_chronological_carried_triage_future_and_actions():
    items = [todo("later", date="2026-10-19", time="12:00", urgent=True),
             todo("early", date="2026-10-19", time="08:00"),
             todo("untimed", date="2026-10-19"),
             todo("late", date="2026-10-19", late_days=3, time="07:00"),
             todo("vital", date="2026-10-19", late_days=1, vital=True),
             todo("star", date="2026-10-19", late_days=2, urgent=True, recurring=True),
             todo("drop", date="2026-10-19", dropped=True),
             todo("future-z", date="2026-10-20", urgent=True),
             todo("future-a", date="2026-10-20", time="09:00", recurring=True, done=True),
             todo("outside", date="2026-10-26")]
    following = next_days()
    following[0]["rows"] = [
        {"id": "future-a:2026-10-20", "title": "future-a", "link": "/note/todos/future-a", "done": True, "struck": True,
         "lead": {"text": "09:00", "tone": "muted"}, "accent": "muted", "title_tone": "muted"},
        {"id": "future-z:2026-10-20", "title": "future-z", "link": "/note/todos/future-z", "done": False, "struck": False,
         "accent": "muted", "title_tone": "plain"}]
    assert build("calendar", FixtureContext({CALENDAR_PATH: items})) == expected(
        "calendar", title="Today, Mon 19 Oct", meta="6 open today, 3 carried over", blocks=[
            {"type": "rows", "title": "Today 3", "rows": [
                calendar_row("early", lead={"text": "08:00", "tone": "muted"}),
                calendar_row("later", lead={"text": "12:00", "tone": "muted"}), calendar_row("untimed")]},
            {"type": "rows", "title": "Carried over 3", "rows": [
                calendar_row("star", trail={"text": "2 days late", "tone": "warn"}, action={
                    "label": "Mark done", "method": "PATCH", "path": "/api/brain/api/todos/star", "body": {"done_date": "2026-10-19"},
                    "error": CALENDAR_ERROR}),
                calendar_row("vital", marks=[{"text": "!", "tone": "danger", "tip": "Vital"}],
                             trail={"text": "1 day late", "tone": "warn"}),
                calendar_row("late", lead={"text": "07:00", "tone": "muted"}, trail={"text": "3 days late", "tone": "warn"})]},
            *following])


@pytest.mark.parametrize("recurring,done,failed,body", [
    (False, False, False, {"status": "done"}), (False, True, False, {"status": "open"}),
    (True, False, True, {"done_date": "2026-10-19"}),
    (True, True, False, {"undone_date": "2026-10-19", "unfailed_date": "2026-10-19"}),
])
def test_calendar_patch_for_and_settled_counts(recurring, done, failed, body):
    item = todo("one /?", date="2026-10-19", recurring=recurring, done=done, failed=failed, vital=True)
    result = build("calendar", FixtureContext({CALENDAR_PATH: [item]}))
    row = result["blocks"][0]["rows"][0]
    assert row["action"] == {"label": "Mark not done" if done else "Mark done", "method": "PATCH",
                             "path": "/api/brain/api/todos/one%20%2F%3F", "body": body, "error": CALENDAR_ERROR}
    assert row["done"] is done
    assert row["struck"] is (done or failed)
    assert row["marks"] == [{"text": "!", "tone": "danger", "tip": "Vital"}]
    assert "lead" not in row
    assert result["meta"] == f"{int(not done and not failed)} open today, 0 carried over"


def test_calendar_failed_carried_counts_like_javascript():
    items = [todo("failed", date="2026-10-19", late_days=1, failed=True),
             todo("done", date="2026-10-19", late_days=1, done=True)]
    result = build("calendar", FixtureContext({CALENDAR_PATH: items}))
    assert result["meta"] == "0 open today, 1 carried over"
    assert [row["title"] for row in result["blocks"][0]["rows"]] == ["done", "failed"]


@pytest.mark.parametrize("category,tone", [
    ("study", "accent"), ("deadline", "accent"), ("finance", "accent"), ("bill", "accent"),
    ("family", "ok"), ("social", "ok"), ("health", "warn"), ("chore", "warn"),
    ("work", "danger"), ("travel", "ok"), ("errand", "ok"), ("personal", "ok"),
    ("other", "muted"), (None, "muted"),
])
@pytest.mark.parametrize("date", ["2026-10-19", "2026-10-20"])
def test_calendar_category_accents_use_only_contract_tones(category, tone, date):
    item = todo("one", date=date, category=category)
    result = build("calendar", FixtureContext({CALENDAR_PATH: [item]}))
    row = next(row for block in result["blocks"] for row in block["rows"])
    assert row["accent"] == tone


@pytest.mark.parametrize("date,fields,tone", [
    ("2026-10-19", {}, "plain"), ("2026-10-19", {"done": True}, "ok"),
    ("2026-10-19", {"failed": True}, "danger"),
    ("2026-10-19", {"done": True, "failed": True}, "ok"),
    ("2026-10-19", {"recurring": True}, "muted"),
    ("2026-10-19", {"recurring": True, "done": True}, "muted"),
    ("2026-10-19", {"recurring": True, "failed": True}, "muted"),
    ("2026-10-19", {"recurring": True, "vital": True, "failed": True}, "danger"),
    ("2026-10-19", {"recurring": True, "urgent": True}, "plain"),
    ("2026-10-20", {"failed": True}, "plain"),
    ("2026-10-20", {"done": True}, "ok"),
    ("2026-10-20", {"recurring": True, "done": True}, "muted"),
    ("2026-10-20", {"recurring": True, "vital": True}, "plain"),
])
def test_calendar_title_tone_follows_javascript_classes_and_css_order(date, fields, tone):
    item = todo("one", date=date, **fields)
    result = build("calendar", FixtureContext({CALENDAR_PATH: [item]}))
    row = next(row for block in result["blocks"] for row in block["rows"])
    assert row["title_tone"] == tone


@pytest.mark.parametrize("date", ["2026-10-19", "2026-10-20"])
def test_calendar_time_vital_and_lateness_do_not_replace_each_other(date):
    item = todo("one", date=date, time="09:00", vital=True, urgent=True, late_days=2, category="health")
    result = build("calendar", FixtureContext({CALENDAR_PATH: [item]}))
    row = next(row for block in result["blocks"] for row in block["rows"])
    assert row["lead"] == {"text": "09:00", "tone": "muted"}
    assert row["marks"] == [{"text": "!", "tone": "danger", "tip": "Vital"}]
    assert row["accent"] == "warn"
    if date == "2026-10-19":
        assert row["trail"] == {"text": "2 days late", "tone": "warn"}
        assert row["action"]["error"] == CALENDAR_ERROR
    else:
        assert "trail" not in row
        assert "action" not in row


def test_health_ranks_services_and_dependencies_stably_and_counts_hosts():
    data = {"checked_at": "2026-10-19T10:58:00Z", "summary": {"up": 2, "total": 6, "paused": 1},
            "services": [{"id": "warning", "host": "h", "state": "warn", "detail": "**Slow**"},
                         {"id": "dead", "host": "b", "state": "down"},
                         {"id": "up1", "host": "h", "state": "up"},
                         {"id": "paused", "host": "c", "state": "paused"},
                         {"id": "up2", "host": "b", "state": "up"},
                         {"id": "unknown", "host": "b", "state": "unknown"}],
            "dependencies": [{"id": "dep-down", "state": "down", "criticality": "vital"},
                             {"id": "dep-warn", "state": "warn", "detail": "Late"},
                             {"id": "ignored", "state": "unknown"}],
            "disk": {"used_pct": 84.5, "free_gb": 40.5}}
    assert build("health", FixtureContext({SOURCES["health"]: data})) == expected(
        "health", meta="Checked 2m ago", blocks=[
            {"type": "rows", "rows": [
                {"id": "services:dead", "title": "dead", "detail": "b", "lead": {"text": "Down", "tone": "danger", "badge": True}},
                {"id": "dependencies:dep-down", "title": "dep-down", "detail": "vital", "lead": {"text": "Down", "tone": "danger", "badge": True}},
                {"id": "services:warning", "title": "warning", "detail": "Slow", "lead": {"text": "Warn", "tone": "warn", "badge": True}},
                {"id": "dependencies:dep-warn", "title": "dep-warn", "detail": "Late", "lead": {"text": "Warn", "tone": "warn", "badge": True}}]},
            {"type": "line", "items": [{"text": "2 of 5 up", "tone": "muted"}, {"text": "1 paused", "tone": "muted"},
                                       {"text": "b 1/3", "tone": "muted"}, {"text": "h 1/2", "tone": "muted"}]},
            {"type": "meter", "label": "Disk", "value": 85, "max": 100, "warn_at": 85, "danger_at": 95,
             "text": "85% used, 41 GB free"}])


def test_health_all_up_collapses_but_preserves_hosts_paused_and_zero_disk():
    data = {"summary": {"up": 1, "paused": 1}, "services": [
        {"id": "ok", "host": "h", "state": "up"}, {"id": "paused", "host": "b", "state": "paused"}],
        "dependencies": [{"id": "unprobed", "state": "unknown"}], "disk": {"used_pct": 0, "free_gb": 40}}
    result = build("health", FixtureContext({SOURCES["health"]: data}))
    assert result["blocks"][0] == {"type": "line", "items": [
        {"text": "All 1 services up", "tone": "ok", "badge": True},
        {"text": "1 paused", "tone": "muted"}, {"text": "h 1/1", "tone": "muted"}]}
    assert result["blocks"][1]["value"] == 0


def test_compute_fixed_quota_order_reset_copy_temperatures_and_footer():
    pace = {"computed_at": "2026-10-19T10:59:00Z", "quotas": [
        {"id": "codex 7d", "remaining_pct": 9.5, "resets_at": "2026-10-24T20:41:00Z", "seconds_to_reset": 466860,
         "runs_out_at": "2026-10-23T09:15:00Z"},
        {"id": "ignored", "remaining_pct": 99},
        {"id": "claude 5h", "remaining_pct": 60, "resets_at": "2026-10-19T14:30:00Z", "seconds_to_reset": 12600},
        {"id": "claude 7d", "remaining_pct": 80.5, "resets_at": "2026-10-25T01:00:00Z", "seconds_to_reset": 482400}],
        "openrouter": {"remaining_usd": 3.31, "limit_usd": 50}, "hours": {"today": 2.25}}
    state = {"temps": {"claude": {"temp": "HOT"}, "codex": {"temp": "FREEZING"}}}
    result = build("compute", FixtureContext({SOURCES["compute"]: pace, "/api/compute/state": state}))
    assert result == expected("compute", meta="Read 1m ago", blocks=[
        {"type": "line", "items": [{"text": "Hot", "tone": "ok", "badge": True, "tip": "Ahead, spend more"}]},
        {"type": "meter", "label": "Claude week", "value": 81, "max": 100, "text": "81% left", "tone": "plain"},
        {"type": "line", "items": [{"text": "Resets Sun 25 Oct, 01:00", "tone": "muted"}, {"text": "in 5d 14h", "tone": "muted"}]},
        {"type": "meter", "label": "Claude 5 hour", "value": 60, "max": 100, "text": "60% left", "tone": "plain"},
        {"type": "line", "items": [{"text": "Resets 15:30", "tone": "muted"}, {"text": "in 3h 30m", "tone": "muted"}]},
        {"type": "line", "items": [{"text": "Freezing", "tone": "danger", "badge": True, "tip": "Will run out, ration it"}]},
        {"type": "meter", "label": "Codex week", "value": 10, "max": 100, "text": "10% left", "tone": "warn"},
        {"type": "line", "items": [{"text": "Resets Sat 24 Oct, 21:41", "tone": "muted"}, {"text": "Runs out Fri 10:15", "tone": "warn"}]},
        {"type": "line", "items": [{"text": "OpenRouter $3.31 left of $50", "tone": "warn"}, {"text": "2.3h worked today", "tone": "muted"}]}])


@pytest.mark.parametrize("temp,tone,tip", [
    ("EBURN", "ok", "About to be wasted, spend all of it"), ("BURN", "ok", "Plenty spare, spend it"),
    ("WARM", "ok", "Slightly ahead"), ("COOL", "plain", "On pace"),
    ("COLD", "warn", "Behind, go easy"), ("NEW", "plain", ""),
])
def test_compute_other_temperature_tones(temp, tone, tip):
    pace = {"quotas": [{"id": "claude 7d", "remaining_pct": 20,
                        "resets_at": "2026-10-20T00:00:00Z", "seconds_to_reset": 46800}]}
    result = build("compute", FixtureContext({SOURCES["compute"]: pace,
                     "/api/compute/state": {"temps": {"claude": {"temp": temp}}}}))
    assert result["blocks"][0]["items"] == [{"text": temp.lower().capitalize(), "tone": tone, "badge": True, "tip": tip}]


def test_compute_state_failure_is_optional_and_zero_footers_are_shown():
    result = build("compute", FixtureContext({SOURCES["compute"]: {
        "openrouter": {"remaining_usd": 0}, "hours": {"today": 0}}, "/api/compute/state": TimeoutError("private")}))
    assert result["state"] == "ok"
    assert result["blocks"][-1] == {"type": "line", "items": [
        {"text": "OpenRouter $0.00 left", "tone": "warn"}, {"text": "0.0h worked today", "tone": "muted"}]}


def test_compute_countdown_uses_request_time_instead_of_snapshot_age():
    quota = {"id": "claude 5h", "remaining_pct": 40, "resets_at": "2026-10-19T12:00:00Z", "seconds_to_reset": 18000}
    result = build("compute", FixtureContext({SOURCES["compute"]: {"quotas": [quota]}, "/api/compute/state": {}}))
    assert result["blocks"][2] == {"type": "line", "items": [
        {"text": "Resets 13:00", "tone": "muted"}, {"text": "in 1h 00m", "tone": "muted"}]}


@pytest.mark.parametrize("key", ["claude 7d", "claude 5h", "codex 7d"])
@pytest.mark.parametrize("runs_out_at,tone", [
    (None, "plain"), ("2026-10-20T00:00:00Z", "warn"),
    ("2026-10-21T00:00:00Z", "plain"), ("2026-10-22T00:00:00Z", "plain"),
])
def test_compute_meter_warning_depends_on_runout_before_reset(key, runs_out_at, tone):
    quota = {"id": key, "remaining_pct": 80 if tone == "warn" else 1,
             "resets_at": "2026-10-21T00:00:00Z", "runs_out_at": runs_out_at}
    result = build("compute", FixtureContext({SOURCES["compute"]: {"quotas": [quota]}, "/api/compute/state": {}}))
    meter = next(block for block in result["blocks"] if block["type"] == "meter")
    assert meter["tone"] == tone


def test_tickets_preserves_source_order_fallbacks_tones_links_and_degradation():
    data = {"tickets": [
        {"id": "z&", "project": "a b", "severity": "minor", "note": "**Fix** [[thing|this]]", "created_at": "2026-10-19T10:00:00Z"},
        {"id": "a", "project": "p", "severity": "blocker", "page": {"title": "Page"}},
        {"id": "b", "project": "p", "severity": "major", "page": {"path": "/path"}},
        {"id": "c", "project": "p", "scope": "Scope"}], "degraded": ["one", "two"]}
    assert build("tickets", FixtureContext({SOURCES["tickets"]: data})) == expected(
        "tickets", meta="4 open", blocks=[{"type": "rows", "rows": [
            {"id": "a b:z&", "title": "Fix this", "detail": "a b", "lead": {"text": "Minor", "tone": "plain", "badge": True},
             "trail": {"text": "1h ago", "tone": "muted"}, "link": "/tickets?project=a%20b&id=z%26"},
            {"id": "p:a", "title": "Page", "detail": "p", "lead": {"text": "Blocker", "tone": "danger", "badge": True},
             "trail": {"text": "", "tone": "muted"}, "link": "/tickets?project=p&id=a"},
            {"id": "p:b", "title": "/path", "detail": "p", "lead": {"text": "Major", "tone": "warn", "badge": True},
             "trail": {"text": "", "tone": "muted"}, "link": "/tickets?project=p&id=b"},
            {"id": "p:c", "title": "Scope", "detail": "p", "lead": {"text": "Open", "tone": "plain", "badge": True},
             "trail": {"text": "", "tone": "muted"}, "link": "/tickets?project=p&id=c"}]},
            {"type": "line", "items": [{"text": "2 projects did not answer", "tone": "muted"}]}])


def test_tickets_empty_with_degraded_projects_keeps_both_messages():
    result = build("tickets", FixtureContext({SOURCES["tickets"]: {"degraded": ["p"]}}))
    assert result == expected("tickets", meta="0 open", blocks=[
        {"type": "rows", "empty": "No open tickets.", "rows": []},
        {"type": "line", "items": [{"text": "1 project did not answer", "tone": "muted"}]}])


def test_crons_problems_hosts_next_limit_order_and_stale_copy():
    base = datetime(2026, 10, 19, 13, 0, tzinfo=TZ).timestamp()
    jobs = [{"name": f"job{i}", "host": "h", "next": base + 60 * i} for i in reversed(range(14))]
    jobs.append({"name": "unscheduled", "host": "h", "next": None})
    data = {"jobs": jobs, "stale": True, "hosts": [
        {"id": "b", "status": "down", "error": "**Connection** timed out"}, {"id": "h", "status": "ok"}],
        "problems": [{"host": "h", "name": "failed", "problem": "last run failed", "detail": "**Exit status** `1`"},
                     {"host": "h", "name": "late", "problem": "overdue"}]}
    rows = [{"id": f"h:job{i}", "title": f"job{i}", "detail": "h",
             "trail": {"text": f"13:{i:02d}", "tone": "muted", "tip": f"job{i}"}} for i in range(12)]
    assert build("crons", FixtureContext({SOURCES["crons"]: data})) == expected(
        "crons", meta="15 jobs, stale", blocks=[
            {"type": "rows", "title": "Problems 3", "rows": [
                {"id": "host:b", "title": "b", "detail": "Connection timed out",
                 "lead": {"text": "Host", "tone": "danger", "badge": True, "tip": "Connection timed out"}},
                {"id": "h:failed", "title": "failed", "detail": "last run failed",
                 "lead": {"text": "h", "tone": "danger", "badge": True, "tip": "Exit status 1"}},
                {"id": "h:late", "title": "late", "detail": "overdue", "lead": {"text": "h", "tone": "warn", "badge": True}}]},
            {"type": "rows", "title": "Next", "rows": rows}])


def test_crons_description_tooltip_and_missing_host_error_fallback():
    base = datetime(2026, 10, 19, 13, 0, tzinfo=TZ).timestamp()
    data = {"jobs": [{"name": "backup", "host": "h", "next": base,
                      "description": "**Back up** [[brain|notes]]"}],
            "hosts": [{"id": "b", "status": "down"}]}
    result = build("crons", FixtureContext({SOURCES["crons"]: data}))
    assert result["blocks"][0]["rows"] == [
        {"id": "host:b", "title": "b", "detail": "Unreachable",
         "lead": {"text": "Host", "tone": "danger", "badge": True}}]
    assert result["blocks"][1]["rows"] == [
        {"id": "h:backup", "title": "backup", "detail": "h",
         "trail": {"text": "13:00", "tone": "muted", "tip": "Back up notes"}}]


EMPTY = [
    ("calendar", [], {"title": "Today, Mon 19 Oct", "meta": "0 open today, 0 carried over", "blocks": [
        {"type": "rows", "title": "Today", "empty": "Nothing on today.", "rows": []}, *next_days()]}),
    ("brief", {}, {"state": "empty", "message": "No brief yet today."}),
    ("tasks", [], {"state": "empty", "message": "No undated tasks.", "meta": "0 undated"}),
    ("money", [], {"state": "empty", "message": "Nothing owed or to sort.", "meta": "0 open"}),
    ("health", {}, {"blocks": [{"type": "line", "items": [{"text": "All 0 services up", "tone": "ok", "badge": True}]}]}),
    ("compute", {}, {"blocks": [{"type": "rows", "title": name, "empty": "No reading yet", "rows": []}
                                for name in ("Claude week", "Claude 5 hour", "Codex week")]}),
    ("tickets", {}, {"state": "empty", "message": "No open tickets.", "meta": "0 open"}),
    ("crons", {}, {"meta": "0 jobs", "blocks": [{"type": "line", "items": [{"text": "All 0 jobs ok", "tone": "ok", "badge": True}]}]}),
]


@pytest.mark.parametrize("name,data,fields", EMPTY)
def test_empty_panels(name, data, fields):
    assert build(name, FixtureContext({SOURCES[name]: data, "/api/compute/state": {}})) == expected(name, **fields)


@pytest.mark.parametrize("name", PANELS)
@pytest.mark.parametrize("failure", [TimeoutError("private http://brain.invalid"), HTTPException(503, "private"), ValueError("private JSON")])
def test_each_builder_returns_its_safe_error_panel(name, failure):
    module = importlib.import_module("core.panels." + name)
    assert module.build(FixtureContext({SOURCES[name]: failure})) == expected(name, state="error", message=ERRORS[name])


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/panels")
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    return TestClient(app)


def test_route_gate_runs_before_data_access_and_unknown_name(client, monkeypatch):
    def unexpected(*args):
        pytest.fail("data accessed before authentication/name check")
    monkeypatch.setattr(api, "Context", unexpected)
    assert client.get("/api/panels/tasks").status_code == 401
    assert client.get("/api/panels/missing").status_code == 401
    client.cookies.set("seed_admin", "forged")
    assert client.get("/api/panels/tasks").status_code == 401
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/panels/missing").status_code == 404


@pytest.mark.parametrize("name,data,fields", EMPTY)
def test_route_returns_panel_json(client, monkeypatch, name, data, fields):
    monkeypatch.setattr(api, "Context", lambda request: FixtureContext({SOURCES[name]: data, "/api/compute/state": {}}))
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/panels/" + name)
    assert response.status_code == 200
    assert response.json() == expected(name, **fields)


@pytest.mark.parametrize("name", PANELS)
def test_route_upstream_errors_are_200_without_diagnostics(client, monkeypatch, name):
    monkeypatch.setattr(api, "Context", lambda request: FixtureContext({SOURCES[name]: TimeoutError("private http://brain.invalid")}))
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/panels/" + name)
    assert response.status_code == 200
    assert response.json() == expected(name, state="error", message=ERRORS[name])


def test_context_reads_brain_directly(monkeypatch):
    from core.api import brain
    calls = []

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout, dict(request.headers)))
        return io.BytesIO(json.dumps({"summary": {"up": 2}}).encode())

    monkeypatch.setattr(brain, "UPSTREAM", "http://brain.test:8766")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert Context(None).get("/api/status") == {"summary": {"up": 2}}
    assert calls == [("http://brain.test:8766/api/status", 30, {"Accept": "application/json"})]


def test_context_calls_local_functions_with_real_request_and_explicit_defaults(monkeypatch):
    from core.api import gadmin_panel
    from pages.compute import api as compute
    from pages.crons import api as crons
    request = Request({"type": "http", "headers": [(b"cookie", b"seed_admin=ok")]})
    calls = []

    def local(name):
        def call(received, **kwargs):
            assert received is request
            calls.append((name, kwargs))
            return {"source": name}
        return call

    monkeypatch.setattr(compute, "pace", local("pace"))
    monkeypatch.setattr(compute, "state", local("state"))
    monkeypatch.setattr(crons, "listing", local("crons"))
    monkeypatch.setattr(gadmin_panel, "list_tickets", local("tickets"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("local API called over HTTP"))
    ctx = Context(request)
    for path, name in (("/api/compute/pace", "pace"), ("/api/compute/state", "state"),
                       ("/api/crons/list", "crons"), ("/api/gadmin_panel/tickets?status=open", "tickets")):
        assert ctx.get(path) == {"source": name}
    assert calls == [("pace", {}), ("state", {}), ("crons", {}),
                     ("tickets", {"status": "open", "project": None, "severity": None})]


@pytest.mark.parametrize("source,want", [
    (None, ""), ("**Title** [[note|label]] `code`", "Title label code"),
    ("[[bare]] [link](https://example.test) ![alt](img)", "bare link alt"),
    ("# Heading\n> quote\n- item\n2. second", "Heading quote item second"),
    ("***bold*** **open *single* ~~struck~~", "bold open single struck"),
    ("_word_ __strong__ ___both___ snake_case x_y_z", "word strong both snake_case x_y_z"),
    ("before ```hidden\ncode``` after", "before after"),
])
def test_plain_matches_loaded_fd_helper(source, want):
    assert plain(source) == want


def test_chip_supports_icon_only_marks_and_flattens_optional_tooltips():
    assert chip("", "warn", icon="star", tip="**Starred** [[todo|task]]") == {
        "text": "", "tone": "warn", "icon": "star", "tip": "Starred task"}
    assert chip("Hot", "ok", True, tip="Ahead, spend more") == {
        "text": "Hot", "tone": "ok", "badge": True, "tip": "Ahead, spend more"}
    assert chip("Plain") == {"text": "Plain", "tone": "plain"}
    assert chip("Unknown", tip="") == {"text": "Unknown", "tone": "plain", "tip": ""}


@pytest.mark.parametrize("value,want", [
    ("2026-10-19T10:59:30Z", "30s ago"), ("2026-10-19T10:58:30Z", "2m ago"),
    ("2026-10-19T09:30:00Z", "2h ago"), ("2026-10-17T23:00:00Z", "2d ago"),
    ("2026-10-19T11:01:30Z", "in 2m"), ("invalid", ""), (None, ""),
])
def test_relative_times_follow_javascript_rounding(value, want):
    assert rel(value, NOW) == want


def test_dates_use_london_and_dst_without_machine_locale():
    assert day("2026-10-21") == "Wed 21 Oct"
    assert london("2026-10-24T23:30:00Z", True) == "Sun 25 Oct, 00:30"
    assert london("2026-10-25T01:30:00Z", "weekday") == "Sun 01:30"
    ctx = Context(None, datetime.fromisoformat("2026-10-19T23:30:00+00:00"))
    assert ctx.now.date().isoformat() == "2026-10-20"
    assert span(-5) == "0h 00m"
    assert span(90061) == "1d 1h"
    assert rounded(2.5) == 3
    assert fixed(2.25, 1) == "2.3"
