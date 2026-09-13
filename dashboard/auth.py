"""
Optional dashboard password gate.

Set env DASHBOARD_PASSWORD to enable. Clients send header:
  X-MulT-Auth: <password>
or Authorization: Bearer <password>

Login endpoint issues a short-lived token (HMAC of password) stored client-side.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

AUTH_HEADER = "x-mult-auth"
BEARER_PREFIX = "bearer "


def password_configured() -> bool:
    return bool(os.environ.get("DASHBOARD_PASSWORD", "").strip())


def get_password() -> str:
    return os.environ.get("DASHBOARD_PASSWORD", "").strip()


def make_token(password: str) -> str:
    salt = os.environ.get("DASHBOARD_AUTH_SALT", "mult-ops-console")
    return hmac.new(salt.encode(), password.encode(), hashlib.sha256).hexdigest()


def verify_secret(value: Optional[str]) -> bool:
    if not password_configured():
        return True
    if not value:
        return False
    expected_pw = get_password()
    expected_tok = make_token(expected_pw)
    v = value.strip()
    return secrets.compare_digest(v, expected_pw) or secrets.compare_digest(v, expected_tok)


def extract_credential(request: Request) -> Optional[str]:
    h = request.headers.get(AUTH_HEADER) or request.headers.get("X-MulT-Auth")
    if h:
        return h
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith(BEARER_PREFIX):
        return auth[len(BEARER_PREFIX) :].strip()
    # query token for WebSocket (browsers cannot set custom WS headers easily)
    q = request.query_params.get("token") or request.query_params.get("auth")
    if q:
        return q
    return request.cookies.get("mult_auth")


PUBLIC_PREFIXES = (
    "/api/auth/",
    "/api/healthz",
    "/favicon",
    "/_next/",
    "/static/",
)


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not password_configured():
            return await call_next(request)

        path = request.url.path or "/"
        if request.method == "OPTIONS":
            return await call_next(request)
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)
        if path in ("/", "/robots.txt", "/index.html"):
            return await call_next(request)
        # Protect API + websocket only — static UI uses client gate
        if not (path.startswith("/api/") or path.startswith("/ws")):
            return await call_next(request)

        cred = extract_credential(request)
        if verify_secret(cred):
            return await call_next(request)

        return JSONResponse(
            {"ok": False, "reason": "unauthorized", "auth_required": True},
            status_code=401,
        )
