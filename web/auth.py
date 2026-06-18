import base64
import hashlib
import hmac
import json
import secrets
import time
from functools import wraps
from typing import Any, Callable

from aiohttp import web

from config import ADMIN_IDS, ADMIN_SECRET, ADMIN_SESSION_SECRET

SESSION_COOKIE = "admin_session"
CSRF_COOKIE = "admin_csrf"
SESSION_TTL_SEC = 60 * 60 * 12


def web_admin_enabled() -> bool:
    return bool(ADMIN_SECRET and ADMIN_IDS)


def verify_login(telegram_id: int, password: str) -> bool:
    if telegram_id not in ADMIN_IDS:
        return False
    return secrets.compare_digest(password, ADMIN_SECRET)


def _sign(payload: str) -> str:
    return hmac.new(
        ADMIN_SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def create_session_token(admin_id: int) -> str:
    payload = json.dumps(
        {"admin_id": admin_id, "exp": int(time.time()) + SESSION_TTL_SEC},
        separators=(",", ":"),
    )
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{encoded}.{_sign(encoded)}"


def read_session_token(token: str | None) -> int | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(encoded), signature):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(encoded.encode()))
    except (json.JSONDecodeError, ValueError):
        return None
    if data.get("exp", 0) < time.time():
        return None
    admin_id = data.get("admin_id")
    if not isinstance(admin_id, int) or admin_id not in ADMIN_IDS:
        return None
    return admin_id


def get_admin_id(request: web.Request) -> int | None:
    return read_session_token(request.cookies.get(SESSION_COOKIE))


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


async def verify_csrf(request: web.Request) -> bool:
    post = await request.post()
    raw = post.get("csrf_token")
    form_token = str(raw) if raw is not None else None
    cookie_token = request.cookies.get(CSRF_COOKIE)
    return bool(form_token and cookie_token and secrets.compare_digest(form_token, cookie_token))


def require_admin(handler: Callable) -> Callable:
    @wraps(handler)
    async def wrapper(request: web.Request) -> web.StreamResponse:
        admin_id = get_admin_id(request)
        if admin_id is None:
            raise web.HTTPFound("/admin/login")
        request["admin_id"] = admin_id
        return await handler(request)

    return wrapper


def set_session_cookies(response: web.Response, admin_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(admin_id),
        httponly=True,
        samesite="Lax",
        max_age=SESSION_TTL_SEC,
    )
    response.set_cookie(
        CSRF_COOKIE,
        create_csrf_token(),
        httponly=True,
        samesite="Lax",
        max_age=SESSION_TTL_SEC,
    )


def clear_session_cookies(response: web.Response) -> None:
    response.del_cookie(SESSION_COOKIE)
    response.del_cookie(CSRF_COOKIE)


def template_context(request: web.Request, **extra: Any) -> dict[str, Any]:
    ctx = {
        "admin_id": request.get("admin_id"),
        "csrf_token": request.cookies.get(CSRF_COOKIE) or "",
        "flash": request.get("flash"),
        "path": request.path,
    }
    ctx.update(extra)
    return ctx
