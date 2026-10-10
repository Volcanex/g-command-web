import datetime as dt
import json
import shutil
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.compute import api as compute_api  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("COMPUTE_READ_TOKEN", raising=False)
    context = tmp_path / "context"
    context.mkdir()
    for name in ("temperature.py", "providers.json", "models.json"):
        shutil.copyfile(compute_api.G_ENV / "context" / name, context / name)
    monkeypatch.setenv("COMPUTE_TEMPERATURE_PY", str(context / "temperature.py"))
    app = FastAPI()
    app.include_router(compute_api.router, prefix="/api/compute")
    monkeypatch.setattr(compute_api, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(compute_api, "ADMIN_VALUE", "ok")
    return TestClient(app)


def _write_cache(home, rows):
    d = home / ".cache/genv"
    d.mkdir(parents=True)
    (d / "compute-usage-latest.json").write_text(json.dumps({"rows": rows}))


def _write_snapshot(home, name, data):
    path = home / ".cache/genv" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _row(provider, fetched_at, status="ok"):
    return {"provider": provider, "metric": "m", "status": status, "remaining": 50,
            "used": 50, "limit": 100, "unit": "percent", "resets_at": None,
            "fetched_at": fetched_at, "note": None, "label": None}


def test_requires_cookie(client):
    assert client.get("/api/compute/usage").status_code == 401


def test_missing_cache_is_503(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/compute/usage").status_code == 503


def test_stale_is_derived_from_age(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    now = time.time()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(t))
    _write_cache(tmp_path, [_row("claude", iso(now - 60)), _row("codex", iso(now - 7200))])
    client.cookies.set("seed_admin", "ok")
    body = client.get("/api/compute/usage").json()
    by = {r["provider"]: r for r in body["rows"]}
    assert by["claude"]["stale"] is False
    assert by["codex"]["stale"] is True and by["codex"]["age_seconds"] >= 7200


def test_pace_requires_cookie_and_missing_is_503(client, tmp_path, monkeypatch):
    assert client.get("/api/compute/pace").status_code == 401
    monkeypatch.setenv("HOME", str(tmp_path))
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/compute/pace").status_code == 503


def test_pace_serves_cache_with_age(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / ".cache/genv"
    d.mkdir(parents=True)
    iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 120))
    (d / "compute-pace.json").write_text(json.dumps({"computed_at": iso, "quotas": [], "hours": {}}))
    client.cookies.set("seed_admin", "ok")
    body = client.get("/api/compute/pace").json()
    assert body["age_seconds"] >= 120 and body["quotas"] == []


@pytest.mark.parametrize("path", ("/state", "/sync"))
def test_reads_require_auth(client, path):
    assert client.get("/api/compute" + path).status_code == 401
    client.cookies.set("seed_admin", "wrong")
    assert client.get("/api/compute" + path).status_code == 401


def test_state_accepts_cookie_but_sync_does_not(client):
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/compute/state").status_code == 200
    assert client.get("/api/compute/sync").status_code == 401


@pytest.mark.parametrize("path", ("/state", "/sync"))
def test_reads_accept_only_matching_bearer(client, monkeypatch, path):
    monkeypatch.setenv("COMPUTE_READ_TOKEN", "read-token")
    assert client.get("/api/compute" + path,
                      headers={"Authorization": "Bearer read-token"}).status_code == 200
    for authorization in ("Bearer wrong", "Basic read-token", "Bearer"):
        assert client.get("/api/compute" + path,
                          headers={"Authorization": authorization}).status_code == 401


@pytest.mark.parametrize("path", ("/state", "/sync"))
@pytest.mark.parametrize("token", (None, ""))
@pytest.mark.parametrize("authorization", ("Bearer ", "Bearer read-token"))
def test_empty_or_unset_token_never_matches(client, monkeypatch, path, token, authorization):
    if token is not None:
        monkeypatch.setenv("COMPUTE_READ_TOKEN", token)
    assert client.get("/api/compute" + path,
                      headers={"Authorization": authorization}).status_code == 401


def test_mode_requires_cookie_and_rejects_bearer(client, tmp_path, monkeypatch):
    body = {"provider": "claude", "temp": "HOT", "speed": "FAST"}
    assert client.post("/api/compute/mode", json=body).status_code == 401
    monkeypatch.setenv("COMPUTE_READ_TOKEN", "read-token")
    assert client.post("/api/compute/mode", json=body,
                       headers={"Authorization": "Bearer read-token"}).status_code == 401
    assert not (tmp_path / ".cache/genv/compute-mode.json").exists()
    assert not (tmp_path / ".cache/genv/compute-mode.log").exists()


@pytest.mark.parametrize("origin", ("https://other.example", "http://testserver:8443", "null", "", "https://[bad"))
def test_mode_rejects_cross_origin(client, tmp_path, origin):
    client.cookies.set("seed_admin", "ok")
    response = client.post("/api/compute/mode", headers={"Origin": origin},
                           json={"provider": "codex", "temp": "HOT", "speed": "FAST"})
    assert response.status_code == 403
    assert not (tmp_path / ".cache/genv/compute-mode.json").exists()
    assert not (tmp_path / ".cache/genv/compute-mode.log").exists()


def test_state_reads_genv_data(client, tmp_path):
    now = time.time()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(t))
    pace = {"computed_at": iso(now - 120), "hours": {}, "quotas": [{
        "id": "codex 7d", "provider": "codex", "resets_at": iso(now + 86400),
        "window_hours": 168, "used_pct": 25, "burn_pct_per_work_hour": 1,
        "safe_burn_pct_per_work_hour": 1, "low_sample": False}]}
    spend = {"days": [{"date": "2026-10-05", "usd": 1.25}]}
    _write_snapshot(tmp_path, "compute-pace.json", pace)
    _write_snapshot(tmp_path, "compute-spend.json", spend)
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/compute/state")
    assert response.status_code == 200
    body = response.json()
    assert body["pace"]["age_seconds"] >= 120
    assert body["pace"]["quotas"][0]["seconds_to_reset"] > 0
    assert body["pace"]["computed_at"] == pace["computed_at"]
    assert body["temps"]["codex"]["measured"] == "COOL"
    assert body["temps"]["codex"]["temp"] == "COOL"
    assert body["temps"]["codex"]["ratio"] == 1
    assert body["temps"]["codex"]["window"] == "codex 7d"
    assert body["overrides"] == {}
    assert body["spend"] == spend
    context = tmp_path / "context"
    assert body["models"] == json.loads((context / "models.json").read_text())
    providers = json.loads((context / "providers.json").read_text())
    assert body["roles"] == {"order": providers["roles"], "base_effort": providers["effort"],
                             "web": providers.get("web", {}),
                             "effective_codex_effort": providers["effort"]}
    assert body["levels"] == {"temps": ["BURN", "HOT", "WARM", "COOL", "COLD", "FREEZING"],
                              "speeds": ["FAST", "NORMAL", "SLOW"]}


def test_state_missing_caches_are_null(client):
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/compute/state")
    assert response.status_code == 200
    body = response.json()
    assert body["pace"] is None and body["spend"] is None
    assert body["overrides"] == {}
    assert body["temps"]["claude"]["temp"] is None
    assert body["temps"]["codex"]["speed"] == "NORMAL"


@pytest.mark.parametrize("name", ("temperature.py", "providers.json", "models.json"))
@pytest.mark.parametrize("failure", ("missing", "invalid"))
def test_state_missing_or_invalid_pieces_are_null(client, tmp_path, name, failure):
    path = tmp_path / "context" / name
    if failure == "missing":
        path.unlink()
    else:
        path.write_text("{")
    cache = tmp_path / ".cache/genv"
    cache.mkdir(parents=True)
    for filename in ("compute-pace.json", "compute-spend.json"):
        (cache / filename).write_text("{")
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/compute/state")
    assert response.status_code == 200
    body = response.json()
    assert body["pace"] is None and body["spend"] is None
    if name == "temperature.py":
        assert body["temps"] == {"claude": None, "codex": None}
        assert body["overrides"] is None
        assert body["levels"] == {"temps": None, "speeds": None}
        assert body["roles"]["effective_codex_effort"] is None
        assert body["models"] is not None
    elif name == "providers.json":
        assert body["roles"] == {"order": None, "base_effort": None,
                                 "web": None, "effective_codex_effort": None}
    else:
        assert body["models"] is None


def test_state_missing_pace_module_is_null(client, tmp_path, monkeypatch):
    monkeypatch.setattr(compute_api, "PACE_BIN", str(tmp_path / "missing-compute-pace"))
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/compute/state")
    assert response.status_code == 200
    assert response.json()["pace"] is None


def test_state_defaults_missing_web_to_empty_dict(client, tmp_path):
    path = tmp_path / "context/providers.json"
    providers = json.loads(path.read_text())
    providers.pop("web", None)
    path.write_text(json.dumps(providers))
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/compute/state").json()["roles"]["web"] == {}


@pytest.mark.parametrize("provider,temp,speed,headers,ip", (
    ("claude", "HOT", "FAST", {"Origin": "http://testserver", "X-Real-IP": "203.0.113.8"}, "203.0.113.8"),
    ("codex", "BURN", "SLOW", {"Origin": "http://testserver"}, "testclient"),
    ("claude", "WARM", "NORMAL", {}, "testclient"),
))
def test_mode_set_then_read_round_trip(client, tmp_path, provider, temp, speed, headers, ip):
    client.cookies.set("seed_admin", "ok")
    response = client.post("/api/compute/mode", headers=headers,
                           json={"provider": provider, "temp": temp, "speed": speed})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"temps", "overrides"}
    assert set(body["temps"]) == {"claude", "codex"}
    assert body["temps"][provider]["temp"] == temp
    assert body["temps"][provider]["temp_override"] == temp
    assert body["temps"][provider]["speed"] == speed
    override = body["overrides"][provider]
    assert override["temp"] == temp
    assert override["speed"] == (None if speed == "NORMAL" else speed)
    assert override["by"] == "gcommand"
    assert dt.datetime.fromisoformat(override["expires_at"]) > dt.datetime.fromisoformat(override["set_at"])
    response = client.get("/api/compute/state")
    assert response.status_code == 200
    state = response.json()
    assert state["temps"] == body["temps"]
    assert state["overrides"] == body["overrides"]
    if provider == "codex":
        assert state["roles"]["effective_codex_effort"]["gather"] == "xhigh"
        assert state["roles"]["effective_codex_effort"]["build"] == "xhigh"
    lines = (tmp_path / ".cache/genv/compute-mode.log").read_text().splitlines()
    assert len(lines) == 1
    change = json.loads(lines[0])
    assert change == {"ts": change["ts"], "provider": provider, "temp": temp, "speed": speed, "ip": ip}
    assert dt.datetime.fromisoformat(change["ts"]).tzinfo == dt.timezone.utc
    stored = json.loads((tmp_path / ".cache/genv/compute-mode.json").read_text())
    assert stored[provider] == override


@pytest.mark.parametrize("provider", ("claude", "codex"))
def test_mode_nulls_clear_only_selected_provider(client, tmp_path, provider):
    client.cookies.set("seed_admin", "ok")
    other = "codex" if provider == "claude" else "claude"
    for name in (provider, other):
        assert client.post("/api/compute/mode", json={
            "provider": name, "temp": "HOT", "speed": "SLOW"}).status_code == 200
    response = client.post("/api/compute/mode", json={"provider": provider, "temp": None, "speed": None})
    assert response.status_code == 200
    body = response.json()
    assert set(body["overrides"]) == {other}
    assert body["temps"][provider]["temp_override"] is None
    assert body["temps"][provider]["temp"] is None
    assert body["temps"][provider]["speed"] == "NORMAL"
    assert client.get("/api/compute/state").json()["overrides"] == body["overrides"]
    stored = json.loads((tmp_path / ".cache/genv/compute-mode.json").read_text())
    assert stored[provider] is None
    lines = (tmp_path / ".cache/genv/compute-mode.log").read_text().splitlines()
    assert len(lines) == 3
    change = json.loads(lines[-1])
    assert change["provider"] == provider and change["temp"] is None and change["speed"] is None


@pytest.mark.parametrize("provider", ("openrouter", None))
def test_mode_bad_provider_is_400(client, tmp_path, provider):
    client.cookies.set("seed_admin", "ok")
    assert client.post("/api/compute/mode", json={
        "provider": provider, "temp": "HOT", "speed": "FAST"}).status_code == 400
    assert not (tmp_path / ".cache/genv/compute-mode.log").exists()


@pytest.mark.parametrize("field,value", (("temp", "invalid"), ("speed", "invalid"),
                                         ("temp", ""), ("speed", ""), ("temp", False), ("speed", 0)))
def test_mode_bad_levels_are_400(client, tmp_path, field, value):
    client.cookies.set("seed_admin", "ok")
    body = {"provider": "claude", "temp": "HOT", "speed": "FAST", field: value}
    assert client.post("/api/compute/mode", json=body).status_code == 400
    assert not (tmp_path / ".cache/genv/compute-mode.json").exists()
    assert not (tmp_path / ".cache/genv/compute-mode.log").exists()


def test_sync_returns_raw_cache_json(client, tmp_path, monkeypatch):
    pace = {"computed_at": "2026-01-01T00:00:00+00:00", "quotas": [], "hours": {}}
    mode = {"claude": None, "codex": {"temp": "HOT", "speed": "SLOW",
                                     "expires_at": "2026-01-01T00:00:00+00:00", "by": "gcommand"}}
    _write_snapshot(tmp_path, "compute-pace.json", pace)
    _write_snapshot(tmp_path, "compute-mode.json", mode)
    monkeypatch.setenv("COMPUTE_READ_TOKEN", "read-token")
    response = client.get("/api/compute/sync", headers={"Authorization": "Bearer read-token"})
    assert response.status_code == 200
    assert response.json() == {"pace": pace, "mode": mode}


@pytest.mark.parametrize("failure", ("missing", "invalid"))
def test_sync_missing_or_invalid_caches_are_null(client, tmp_path, monkeypatch, failure):
    if failure == "invalid":
        cache = tmp_path / ".cache/genv"
        cache.mkdir(parents=True)
        for name in ("compute-pace.json", "compute-mode.json"):
            (cache / name).write_text("{")
    monkeypatch.setenv("COMPUTE_READ_TOKEN", "read-token")
    response = client.get("/api/compute/sync", headers={"Authorization": "Bearer read-token"})
    assert response.status_code == 200
    assert response.json() == {"pace": None, "mode": None}


def _value_client(client, tmp_path):
    shutil.copyfile(compute_api.G_ENV / "context" / "value.py", tmp_path / "context" / "value.py")
    client.cookies.set("seed_admin", "ok")
    return client


def test_value_requires_auth(client):
    assert client.get("/api/compute/value").status_code == 401
    client.cookies.set("seed_admin", "wrong")
    assert client.get("/api/compute/value").status_code == 401


def test_value_matches_genv_pick_and_explains_every_point(client, tmp_path):
    _value_client(client, tmp_path)
    for role, stakes, domain in (("build", "normal", ""), ("gather", "critical", ""), ("build", "routine", "ui")):
        body = client.get("/api/compute/value", params={"role": role, "stakes": stakes, "domain": domain}).json()
        value = compute_api._value_module()
        pick = value.pick(role, stakes, domain=domain or None)["pick"]["id"]
        assert body["explain"]["pick"] == pick == body["explain"]["ranked"][0]["id"]
        assert {p["id"] for p in body["points"]} == {p["id"] for p in body["explain"]["points"]}
        assert all(p["reason"] for p in body["explain"]["points"] if not p["eligible"])
        assert set(body["grid"]) >= {"build", "gather", "build ui"}
        assert all("price_now" in p for p in body["points"])
    assert body["explain"]["stakes"] == body["explain"]["requested_stakes"] == "routine"
    assert body["preview"] is None and body["live"]["grid"] == body["grid"]
    assert list(body["flips"]) == body["explain"]["rivals"]


def test_value_previews_a_mode_without_saving_it(client, tmp_path):
    _value_client(client, tmp_path)
    params = {"role": "build", "stakes": "critical", "claude_temp": "HOT", "codex_speed": "SLOW"}
    body = client.get("/api/compute/value", params=params).json()
    value = compute_api._value_module()
    overrides = {"claude": {"temp": "HOT"}, "codex": {"speed": "SLOW"}}
    assert body["preview"] == overrides
    assert body["explain"]["pick"] == value.pick("build", "critical", overrides=overrides)["pick"]["id"]
    assert body["live"]["pick"] == value.pick("build", "critical")["pick"]["id"]
    assert body["live"]["grid"] == value.snapshot()["grid"]
    assert body["grid"] == value.snapshot(overrides=overrides)["grid"]
    assert body["prices"]["claude"]["source"] == "preview"
    assert body["tuning"]["base"] == value.BASE
    assert not (tmp_path / ".cache/genv/compute-mode.json").exists()
    cleared = client.get("/api/compute/value", params={"claude_temp": "auto", "claude_speed": "NORMAL"}).json()
    assert cleared["preview"] == {"claude": {"temp": None, "speed": None}}


@pytest.mark.parametrize("params", ({"role": "nope"}, {"stakes": "huge"}, {"domain": "nope"},
                                    {"claude_temp": "TEPID"}, {"codex_speed": "LUDICROUS"}))
def test_value_bad_params_are_400(client, tmp_path, params):
    _value_client(client, tmp_path)
    assert client.get("/api/compute/value", params=params).status_code == 400


def test_value_missing_model_is_503(client):
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/compute/value").status_code == 503
