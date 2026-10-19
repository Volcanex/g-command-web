from core.panels import builder
from core.panels.helpers import chip, fixed, london, parsed, rel, rounded, span


QUOTAS = (("claude 7d", "Claude week", "claude"), ("claude 5h", "Claude 5 hour", "claude"),
          ("codex 7d", "Codex week", "codex"))
TONES = {"EBURN": "ok", "BURN": "ok", "HOT": "ok", "WARM": "ok", "COOL": "plain", "COLD": "warn", "FREEZING": "danger"}
STATUS = {"EBURN": "About to be wasted, spend all of it", "BURN": "Plenty spare, spend it",
          "HOT": "Ahead, spend more", "WARM": "Slightly ahead", "COOL": "On pace",
          "COLD": "Behind, go easy", "FREEZING": "Will run out, ration it"}


@builder("compute")
def build(ctx):
    pace = ctx.get("/api/compute/pace")
    try:
        state = ctx.get("/api/compute/state") or {}
    except Exception:
        state = {}
    temps = state.get("temps") or {}
    quotas = {quota["id"]: quota for quota in pace.get("quotas") or []}
    blocks = []
    for key, name, provider in QUOTAS:
        quota = quotas.get(key)
        if not quota:
            blocks.append({"type": "rows", "title": name, "empty": "No reading yet", "rows": []})
            continue
        left = rounded(quota["remaining_pct"])
        short = bool(quota.get("runs_out_at") and parsed(quota["runs_out_at"]).timestamp() < parsed(quota["resets_at"]).timestamp())
        temp = (temps.get(provider) or {}).get("temp") if key.endswith("7d") else None
        if temp:
            blocks.append({"type": "line", "items": [chip(str(temp).lower().capitalize(), TONES.get(temp, "plain"), True,
                                                          tip=STATUS.get(temp, ""))]})
        blocks.append({"type": "meter", "label": name, "value": left, "max": 100,
                       "text": f"{left}% left", "tone": "warn" if short else "plain"})
        reset = chip("Resets " + london(quota["resets_at"], key.endswith("7d")), "muted")
        if short:
            remaining = chip("Runs out " + london(quota["runs_out_at"], "weekday"), "warn")
        else:
            seconds = parsed(quota["resets_at"]).timestamp() - ctx.now.timestamp()
            remaining = chip("in " + span(seconds), "muted")
        blocks.append({"type": "line", "items": [reset, remaining]})
    foot = []
    credit = pace.get("openrouter")
    if credit and credit.get("remaining_usd") is not None:
        amount = float(credit["remaining_usd"])
        text = f"OpenRouter ${fixed(amount, 2)} left"
        if credit.get("limit_usd"):
            text += f" of ${rounded(credit['limit_usd'])}"
        foot.append(chip(text, "warn" if amount < 5 else "muted"))
    hours = pace.get("hours")
    if hours and hours.get("today") is not None:
        foot.append(chip(f"{fixed(hours['today'], 1)}h worked today", "muted"))
    if foot:
        blocks.append({"type": "line", "items": foot})
    return {"meta": "Read " + rel(pace["computed_at"], ctx.now) if pace.get("computed_at") else "", "blocks": blocks}
