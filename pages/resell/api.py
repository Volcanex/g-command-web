"""Resell's native admin. Resell owns its APIs, processes and data.

RESELL_<SERVICE>_URL may override each loopback origin. Only the existing
admin's endpoints are forwarded; no browser credentials go upstream.
"""
import asyncio
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from core.auth import cookie_ok


def require_admin(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "admin only")


router = APIRouter(dependencies=[Depends(require_admin)])
PORTS = {"pool": 7500, "registry": 7503, "config": 7504, "network": 8890, "telegram": 7505}
ITEM = r"[a-fA-F0-9]{24}"
SERVICE = r"arbitrage_[a-zA-Z0-9_-]+(?:@[a-zA-Z0-9_-]+)?"
READS = {
    "pool": rf"(?:stats|events|items|items/{ITEM}|images/{ITEM})",
    "registry": rf"(?:services|bots|bots/{SERVICE}/(?:schema|config|logs))",
    "config": rf"config/{SERVICE}",
}
WRITES = {
    ("DELETE", "pool"): rf"items/{ITEM}",
    ("POST", "registry"): rf"(?:bots/{SERVICE}/(?:scale|config)|services/create-variant)",
    ("DELETE", "registry"): rf"services/{SERVICE}",
    ("POST", "config"): rf"config/{SERVICE}",
}


async def upstream(service, path, method="GET", params=None, body=None):
    base = os.environ.get(f"RESELL_{service.upper()}_URL", f"http://127.0.0.1:{PORTS[service]}").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=3)) as client:
            response = await client.request(method, f"{base}/{path}", params=params,
                                            content=body, headers={"content-type": "application/json"})
    except httpx.HTTPError:
        raise HTTPException(503, f"Resell's {service} service is not answering. Try again when the service is available.") from None
    if response.is_error:
        status = response.status_code
        if status == 404:
            detail = "This record was not found. Refresh the list and try again."
        elif status in (400, 409, 422):
            detail = "Resell refused these values. Check the fields and try again."
        else:
            detail = f"Resell's {service} service could not complete the request. Try again."
        raise HTTPException(status, detail)
    return response


def json_body(response):
    try:
        return response.json()
    except ValueError:
        raise HTTPException(502, "Resell returned an unreadable response. Try again.") from None


@router.get("")
async def overview():
    async def probe(service, path):
        try:
            data = json_body(await upstream(service, path))
            return {"name": service, "available": True, "data": data}
        except HTTPException as exc:
            return {"name": service, "available": False, "message": exc.detail}

    services = await asyncio.gather(*(probe(service, path) for service, path in (
        ("pool", "stats"), ("registry", "services"), ("network", "health"),
        ("config", "health"), ("telegram", "health"))))
    return {"services": services}


@router.get("/bots")
async def bots():
    services, tasks = await asyncio.gather(upstream("registry", "services"), upstream("registry", "bots"))
    return {"services": json_body(services)["services"], "bots": json_body(tasks)["bots"]}


@router.get("/profit")
async def profit():
    items = []
    page = 1
    while True:
        result = json_body(await upstream("pool", "items", params={
            "status": "real_sold", "include_data": "true", "page": page, "page_size": 100,
        }))
        items.extend(result["items"])
        if page >= result["total_pages"]:
            return {"items": items}
        page += 1


@router.api_route("/{service}/{path:path}", methods=["GET", "POST", "DELETE"])
async def forward(service: str, path: str, request: Request):
    pattern = READS.get(service) if request.method == "GET" else WRITES.get((request.method, service))
    if not pattern or not re.fullmatch(pattern, path):
        raise HTTPException(404, "unknown Resell endpoint")
    try:
        response = await upstream(service, path, request.method,
                                  params=list(request.query_params.multi_items()),
                                  body=await request.body() if request.method != "GET" else None)
    except HTTPException as exc:
        if request.method == "GET" and service == "config" and exc.status_code == 404:
            return {"config": {}, "exists": False}
        raise
    return Response(response.content, status_code=response.status_code,
                    headers={"content-type": response.headers.get("content-type", "application/json"),
                             "cache-control": "no-store"})
