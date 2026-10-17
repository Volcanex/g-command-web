"""The admin session secret, read in one place for every router.

ADMIN_COOKIE_VALUE is the session secret: holding it is being logged in.
It used to default to "ok", which anyone could forge, and each router read
it for itself, so one missed copy reopened the hole. Everything now imports
it from here, and importing this module without it stops the process.
server.py imports it before mounting any router, so the server refuses to
start rather than serve a gate that a constant opens. cookie_ok is the one
compare, constant time and on bytes so a non-ASCII cookie is a refusal, not
a TypeError.
"""

import hmac
import os

ADMIN_COOKIE = os.environ.get("ADMIN_COOKIE", "seed_admin")
ADMIN_VALUE = os.environ.get("ADMIN_COOKIE_VALUE", "")
if not ADMIN_VALUE:
    raise SystemExit(
        "refusing to start: ADMIN_COOKIE_VALUE is unset. It is the admin session "
        "secret; set it to a long random value, for example "
        "`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`."
    )


def cookie_ok(cookies) -> bool:
    return hmac.compare_digest(cookies.get(ADMIN_COOKIE, "").encode(), ADMIN_VALUE.encode())
