import logging
from pathlib import Path

from aiohttp import web

from config import PAYMENT_CONTACT_USERNAME, SERIALS_PER_PAGE
from database import repository as repo
from database.connection import get_db
from services.messages import format_date, format_month_year
from services.payment_contact import payment_contact_label, payment_contact_url
from services.serial_matcher import search_serials
from services.settings import format_free_limit_label, get_free_daily_limit
from web.templates import render_template

logger = logging.getLogger(__name__)

SITE_STATIC_DIR = Path(__file__).resolve().parent / "static" / "site"
WEB_SERIALS_PER_PAGE = 12
WEB_EPISODES_PER_PAGE = 15

_bot_username: str | None = None


async def _resolve_bot_username(app: web.Application) -> str:
    global _bot_username
    if _bot_username:
        return _bot_username
    create_bot = app.get("create_bot")
    if not create_bot:
        return ""
    bot = create_bot()
    try:
        me = await bot.get_me()
        _bot_username = me.username or ""
    except Exception:
        logger.exception("Failed to fetch bot username for user site")
        _bot_username = ""
    finally:
        await bot.session.close()
    return _bot_username


def _site_context(request: web.Request, app: web.Application, **extra) -> dict:
    ctx = {
        "path": request.path,
        "bot_username": app.get("bot_username") or "",
        "bot_url": app.get("bot_url") or "",
        "payment_contact": payment_contact_label(),
        "payment_contact_url": payment_contact_url(),
        "format_date": format_date,
        "format_month_year": format_month_year,
    }
    ctx.update(extra)
    return ctx


def _html(
    app: web.Application, name: str, request: web.Request, status: int = 200, **ctx
) -> web.Response:
    body = render_template(name, **_site_context(request, app, **ctx))
    return web.Response(text=body, content_type="text/html", status=status)


async def home(request: web.Request) -> web.Response:
    app = request.app
    serial_count = await repo.count_active_serials()
    episode_count = await get_db().episodes.count_documents({})
    serials, _ = await repo.list_serials_catalog(0, 6)
    free_limit = await get_free_daily_limit()
    return _html(
        app,
        "site/home.html",
        request,
        serial_count=serial_count,
        episode_count=episode_count,
        featured=serials,
        free_limit_label=format_free_limit_label(free_limit),
    )


async def serials_list(request: web.Request) -> web.Response:
    app = request.app
    page = max(0, int(request.rel_url.query.get("page", "0")))
    serials, total = await repo.list_serials_catalog(page, WEB_SERIALS_PER_PAGE)
    total_pages = max(1, (total + WEB_SERIALS_PER_PAGE - 1) // WEB_SERIALS_PER_PAGE)
    return _html(
        app,
        "site/serials.html",
        request,
        serials=serials,
        page=page,
        total=total,
        total_pages=total_pages,
    )


async def serial_detail(request: web.Request) -> web.Response:
    app = request.app
    slug = request.match_info["slug"]
    serial = await repo.get_serial_by_slug(slug)
    if not serial or not serial.get("active", True):
        raise web.HTTPFound("/serials")

    months = await repo.get_episode_months(slug)
    episode_count = sum(m["count"] for m in months)
    return _html(
        app,
        "site/serial.html",
        request,
        serial=serial,
        months=months,
        episode_count=episode_count,
    )


async def serial_episodes(request: web.Request) -> web.Response:
    app = request.app
    slug = request.match_info["slug"]
    year = int(request.match_info["year"])
    month = int(request.match_info["month"])
    page = max(0, int(request.rel_url.query.get("page", "0")))

    serial = await repo.get_serial_by_slug(slug)
    if not serial or not serial.get("active", True):
        raise web.HTTPFound("/serials")

    episodes, total = await repo.get_episodes_by_month(
        slug, year, month, page, WEB_EPISODES_PER_PAGE
    )
    total_pages = max(1, (total + WEB_EPISODES_PER_PAGE - 1) // WEB_EPISODES_PER_PAGE)
    return _html(
        app,
        "site/episodes.html",
        request,
        serial=serial,
        year=year,
        month=month,
        episodes=episodes,
        page=page,
        total=total,
        total_pages=total_pages,
    )


async def search_page(request: web.Request) -> web.Response:
    app = request.app
    query = request.rel_url.query.get("q", "").strip()
    results = await search_serials(query) if query else []
    return _html(
        app,
        "site/search.html",
        request,
        query=query,
        results=results,
    )


async def plan_page(request: web.Request) -> web.Response:
    app = request.app
    free_limit = await get_free_daily_limit()
    return _html(
        app,
        "site/plan.html",
        request,
        free_limit_label=format_free_limit_label(free_limit),
    )


async def site_static(request: web.Request) -> web.Response:
    name = request.match_info["path"]
    if ".." in name or name.startswith("/"):
        raise web.HTTPNotFound()
    path = SITE_STATIC_DIR / name
    if not path.is_file():
        raise web.HTTPNotFound()
    content_type = "text/css" if name.endswith(".css") else "application/octet-stream"
    return web.FileResponse(path, headers={"Content-Type": content_type})


def setup_user_routes(app: web.Application, create_bot) -> None:
    app["create_bot"] = create_bot

    @web.middleware
    async def inject_bot_meta(request: web.Request, handler):
        if not app.get("bot_username"):
            username = await _resolve_bot_username(app)
            app["bot_username"] = username
            app["bot_url"] = f"https://t.me/{username}" if username else ""
        return await handler(request)

    app.middlewares.insert(0, inject_bot_meta)

    app.router.add_get("/", home)
    app.router.add_get("/serials", serials_list)
    app.router.add_get("/serials/{slug}", serial_detail)
    app.router.add_get("/serials/{slug}/{year:\\d+}/{month:\\d+}", serial_episodes)
    app.router.add_get("/search", search_page)
    app.router.add_get("/plan", plan_page)
    app.router.add_get("/static/{path:.+}", site_static)
    logger.info("User website enabled at /")
