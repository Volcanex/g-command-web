import json
import urllib.request
from datetime import datetime

from core.panels.helpers import TZ


class Context:
    def __init__(self, request, now=None):
        self.request = request
        self.now = (now or datetime.now(TZ)).astimezone(TZ)

    def get(self, path):
        if path in ("/api/compute/pace", "/api/compute/state"):
            from pages.compute import api
            return getattr(api, path.rsplit("/", 1)[1])(self.request)
        if path == "/api/crons/list":
            from pages.crons.api import listing
            return listing(self.request)
        if path == "/api/gadmin_panel/tickets?status=open":
            from core.api.gadmin_panel import list_tickets
            return list_tickets(self.request, status="open", project=None, severity=None)
        from core.api.brain import UPSTREAM
        req = urllib.request.Request(UPSTREAM + path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
