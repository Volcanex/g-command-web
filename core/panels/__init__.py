from functools import wraps
from importlib import import_module


PANELS = {
    "calendar": ("Today", "calendar-blank", "/calendar", "Open calendar", 300,
                 "Calendar unavailable. The panel retries every 5 minutes."),
    "brief": ("Brief", "sun-horizon", "/pulse", "Open pulse", 600,
              "Brief unavailable. The panel retries every 10 minutes."),
    "tasks": ("Todos", "check-square", "/todos", "Open todos", 300,
              "Todos unavailable. The panel retries every 5 minutes."),
    "money": ("Money", "wallet", "/todos", "Open todos", 300,
              "Money unavailable. The panel retries every 5 minutes."),
    "health": ("Health", "heartbeat", "/system", "Open services", 60,
               "Health unavailable. The panel retries every minute."),
    "compute": ("Compute", "gauge", "/compute", "Open compute", 300,
                "Compute unavailable. The panel retries every 5 minutes."),
    "tickets": ("Tickets", "ticket", "/tickets", "Open tickets", 120,
                "Tickets unavailable. The panel retries every 2 minutes."),
    "crons": ("Crons", "clock", "/crons", "Open crons", 300,
              "Crons unavailable. The panel retries every 5 minutes."),
}


def builder(name):
    def decorate(fn):
        @wraps(fn)
        def build(ctx):
            title, icon, link, label, refresh, message = PANELS[name]
            result = {"v": 1, "id": name, "title": title, "icon": icon,
                      "link": link, "link_label": label, "meta": "", "state": "ok",
                      "message": "", "refresh": refresh, "blocks": []}
            try:
                result.update(fn(ctx))
            except Exception:
                result.update(state="error", message=message)
            return result
        return build
    return decorate


def build(name, ctx):
    if name not in PANELS:
        raise KeyError(name)
    return import_module(f"core.panels.{name}").build(ctx)
