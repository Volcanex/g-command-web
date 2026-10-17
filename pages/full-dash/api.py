"""full-dash API, mounted at /api/full-dash.

Exposes the instance's system architecture diagram (render.diagram_elements) as
Cytoscape elements for the topology panel, and proxies the Voice service's
localhost-only /health for the voice panel. Admin-gated inline, same pattern
as pages/gcore/api.py: the page gate in server.py does not cover /api/*.
"""
import json
import os
import sys
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request

from core.auth import cookie_ok
from core.instance import gcore_dir

router = APIRouter()

GCORE = str(gcore_dir())
VOICE_URL = os.environ.get("VOICE_URL", "http://127.0.0.1:8077")


@router.get("/diagram")
def diagram(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    try:
        if GCORE not in sys.path:
            sys.path.insert(0, GCORE)
        from render import diagram_elements
        return {"elements": diagram_elements()}
    except Exception as exc:
        raise HTTPException(503, f"gcore render unavailable: {exc}")


@router.get("/voice-health")
def voice_health(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    try:
        with urllib.request.urlopen(f"{VOICE_URL}/health", timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # The service answered, it just said it is unwell: /health returns 503
        # with a full check breakdown when any dependency is down. Passing that
        # through as a 502 turned "Telnyx is out of credit" into "voice service
        # unreachable", which sent the panel looking for the wrong fault.
        try:
            return json.loads(e.read())
        except (json.JSONDecodeError, OSError):
            raise HTTPException(502, f"voice service returned {e.code} with no readable body")
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        raise HTTPException(502, f"voice service unreachable: {getattr(e, 'reason', e)}")
