import logging
from pathlib import Path
from urllib.parse import quote

from aiohttp import web
from bson import ObjectId

from database import repository as repo
from database.connection import get_db
from config import NOTIFY_PROMO_INTERVAL_HOURS
from services import admin_actions
from services.messages import format_date, format_datetime
from services.serial_utils import parse_add_serial_input
from services.settings import (
    format_free_limit_label,
    format_trial_ttl_label,
    get_free_daily_limit,
    get_trial_episode_ttl_seconds,
    parse_trial_ttl_setting,
    set_free_daily_limit,
    set_trial_episode_ttl_seconds,
)
from services.upload_parser import parse_episode_date
from web.auth import (
    clear_session_cookies,
    get_admin_id,
    require_admin,
    set_session_cookies,
    template_context,
    verify_csrf,
    verify_login,
    web_admin_enabled,
)
from web.templates import render_template

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
USERS_PER_PAGE = 15
EPISODES_PER_PAGE = 8
SERIALS_PER_PAGE = 20

FREE_LIMIT_PRESETS = [0, 3, 4, 5, 6, 7, 8, 9, 10]
TRIAL_PRESETS = [
    (0, "Off"),
    (10, "10 sec"),
    (30, "30 sec"),
    (60, "1 min"),
    (120, "2 min"),
    (300, "5 min"),
    (3600, "1 hr"),
    (7200, "2 hr"),
    (86400, "24 hr"),
]


def _html(name: str, request: web.Request, status: int = 200, **ctx) -> web.Response:
    body = render_template(name, **template_context(request, **ctx))
    return web.Response(text=body, content_type="text/html", status=status)


def _redirect(path: str, msg: str | None = None) -> None:
    if msg:
        sep = "&" if "?" in path else "?"
        path = f"{path}{sep}msg={quote(msg)}"
    raise web.HTTPFound(path)


def _flash_from_query(request: web.Request) -> str | None:
    return request.rel_url.query.get("msg")


def _create_bot(request: web.Request):
    return request.app["create_bot"]()


async def admin_entry(request: web.Request) -> web.Response:
    if get_admin_id(request) is not None:
        raise web.HTTPFound("/admin/")
    raise web.HTTPFound("/admin/login")


async def login_page(request: web.Request) -> web.Response:
    if get_admin_id(request) is not None:
        raise web.HTTPFound("/admin/")
    error = request.rel_url.query.get("error")
    return _html("login.html", request, error=error)


async def login_submit(request: web.Request) -> web.Response:
    if not web_admin_enabled():
        return _html("login.html", request, error="Web admin is not configured.", status=503)

    post = await request.post()
    raw_id = str(post.get("telegram_id", "")).strip()
    password = str(post.get("password", ""))

    if not raw_id.isdigit():
        raise web.HTTPFound("/admin/login?error=Invalid+Telegram+ID")
    if not verify_login(int(raw_id), password):
        raise web.HTTPFound("/admin/login?error=Invalid+credentials")

    response = web.HTTPFound("/admin/")
    set_session_cookies(response, int(raw_id))
    return response


async def logout(request: web.Request) -> web.Response:
    if request.method == "POST" and not await verify_csrf(request):
        raise web.HTTPForbidden(text="Invalid CSRF token")
    response = web.HTTPFound("/admin/login")
    clear_session_cookies(response)
    return response


@require_admin
async def dashboard(request: web.Request) -> web.Response:
    stats = await repo.get_user_stats()
    episode_count = await get_db().episodes.count_documents({})
    serial_count = await repo.count_active_serials()
    total_views = await repo.get_total_episode_views()
    free_limit = await get_free_daily_limit()
    trial_ttl = await get_trial_episode_ttl_seconds()
    open_requests = await get_db().episode_requests.count_documents({"status": "open"})
    open_tickets = await get_db().support_tickets.count_documents({"status": "open"})
    referral_count = await repo.count_referrals()
    return _html(
        "dashboard.html",
        request,
        flash=_flash_from_query(request),
        stats=stats,
        episode_count=episode_count,
        serial_count=serial_count,
        total_views=total_views,
        referral_count=referral_count,
        free_limit_label=format_free_limit_label(free_limit),
        trial_ttl_label=format_trial_ttl_label(trial_ttl),
        open_requests=open_requests,
        open_tickets=open_tickets,
        format_date=format_date,
    )


@require_admin
async def users_list(request: web.Request) -> web.Response:
    page = max(0, int(request.rel_url.query.get("page", "0")))
    search = request.rel_url.query.get("q", "").strip()

    if search.isdigit():
        user = await repo.get_user(int(search))
        users = [user] if user else []
        total = len(users)
        total_pages = 1
        page = 0
        referrers: dict[int, dict] = {}
        if user and user.get("referred_by"):
            ref = await repo.get_user(user["referred_by"])
            if ref:
                referrers[ref["telegram_id"]] = ref
    else:
        users, total = await repo.list_users(page, USERS_PER_PAGE)
        total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)

    referrers: dict[int, dict] = {}
    referrer_ids = list({u["referred_by"] for u in users if u.get("referred_by")})
    if referrer_ids:
        async for doc in get_db().users.find({"telegram_id": {"$in": referrer_ids}}):
            referrers[doc["telegram_id"]] = doc

    free_limit = await get_free_daily_limit()
    return _html(
        "users.html",
        request,
        flash=_flash_from_query(request),
        users=users,
        referrers=referrers,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        free_limit=free_limit,
        format_date=format_date,
    )


@require_admin
async def user_detail(request: web.Request) -> web.Response:
    telegram_id = int(request.match_info["telegram_id"])
    user = await repo.get_user(telegram_id)
    if not user:
        raise web.HTTPFound("/admin/users?msg=User+not+found")
    free_limit = await get_free_daily_limit()
    referrer = None
    if user.get("referred_by"):
        referrer = await repo.get_user(user["referred_by"])
    referred_users = await repo.list_referred_users(telegram_id)
    return _html(
        "user_detail.html",
        request,
        flash=_flash_from_query(request),
        user=user,
        referrer=referrer,
        referred_users=referred_users,
        free_limit=free_limit,
        format_date=format_date,
        format_datetime=format_datetime,
    )


REFERRALS_PER_PAGE = 25


@require_admin
async def referrals_list(request: web.Request) -> web.Response:
    page = max(0, int(request.rel_url.query.get("page", "0")))
    pairs, total = await repo.list_referral_pairs(page, REFERRALS_PER_PAGE)
    total_pages = max(1, (total + REFERRALS_PER_PAGE - 1) // REFERRALS_PER_PAGE)
    return _html(
        "referrals.html",
        request,
        flash=_flash_from_query(request),
        pairs=pairs,
        page=page,
        total=total,
        total_pages=total_pages,
        format_date=format_date,
        format_datetime=format_datetime,
    )


async def _post_action(request: web.Request, handler) -> web.Response:
    if not await verify_csrf(request):
        raise web.HTTPForbidden(text="Invalid CSRF token")
    return await handler(request)


@require_admin
async def user_ban(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        await repo.set_banned(telegram_id, True)
        _redirect(f"/admin/users/{telegram_id}", "User banned.")

    return await _post_action(request, action)


@require_admin
async def user_unban(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        await repo.set_banned(telegram_id, False)
        _redirect(f"/admin/users/{telegram_id}", "User unbanned.")

    return await _post_action(request, action)


@require_admin
async def user_grant_vip(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        post = await req.post()
        days_raw = str(post.get("days", "30")).strip()
        days = int(days_raw) if days_raw.isdigit() else 30
        bot = _create_bot(req)
        try:
            expires = await admin_actions.grant_vip_with_notify(bot, telegram_id, days)
        finally:
            await bot.session.close()
        _redirect(f"/admin/users/{telegram_id}", f"VIP granted until {format_date(expires)}.")

    return await _post_action(request, action)


@require_admin
async def user_revoke_vip(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        bot = _create_bot(req)
        try:
            removed = await admin_actions.revoke_vip_with_notify(bot, telegram_id)
        finally:
            await bot.session.close()
        if removed:
            _redirect(f"/admin/users/{telegram_id}", "VIP access removed.")
        else:
            _redirect(f"/admin/users/{telegram_id}", "User is not a VIP member.")

    return await _post_action(request, action)


@require_admin
async def user_grant_notify(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        post = await req.post()
        plan_id = str(post.get("notify_plan", "")).strip()
        days_raw = str(post.get("days", "30")).strip()
        days = int(days_raw) if days_raw.isdigit() else 30
        serials_raw = str(post.get("notify_serials", "")).strip()
        bot = _create_bot(req)
        try:
            expires = await admin_actions.grant_notify_with_notify(
                bot, telegram_id, plan_id, days=days
            )
            if serials_raw:
                slugs = [s.strip() for s in serials_raw.replace("\n", ",").split(",") if s.strip()]
                await repo.set_notify_serials(telegram_id, slugs)
        finally:
            await bot.session.close()
        _redirect(
            f"/admin/users/{telegram_id}",
            f"Episode Alerts granted until {format_date(expires)}.",
        )

    return await _post_action(request, action)


@require_admin
async def user_revoke_notify(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        bot = _create_bot(req)
        try:
            removed = await admin_actions.revoke_notify_with_notify(bot, telegram_id)
        finally:
            await bot.session.close()
        if removed:
            _redirect(f"/admin/users/{telegram_id}", "Episode Alerts removed.")
        else:
            _redirect(f"/admin/users/{telegram_id}", "User has no alert membership.")

    return await _post_action(request, action)


@require_admin
async def notify_membership_page(request: web.Request) -> web.Response:
    subscriber_count = await repo.count_notify_subscribers()
    eligible_promo = len(await repo.get_users_without_notify_membership())
    return _html(
        "notify_membership.html",
        request,
        flash=_flash_from_query(request),
        subscriber_count=subscriber_count,
        eligible_promo=eligible_promo,
        promo_interval_hours=NOTIFY_PROMO_INTERVAL_HOURS,
    )


@require_admin
async def notify_membership_promo_send(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        from services.notify_promo import send_notify_membership_promo

        bot = _create_bot(req)
        try:
            sent, total = await send_notify_membership_promo(bot)
        finally:
            await bot.session.close()
        _redirect(
            "/admin/notify-membership",
            f"Alert membership promo sent to {sent}/{total} users.",
        )

    return await _post_action(request, action)


@require_admin
async def user_delete(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        await repo.delete_user(telegram_id)
        _redirect("/admin/users", "User deleted.")

    return await _post_action(request, action)


@require_admin
async def user_grant_unlock(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        telegram_id = int(req.match_info["telegram_id"])
        post = await req.post()
        episode_id = str(post.get("episode_id", "")).strip()
        if not ObjectId.is_valid(episode_id):
            _redirect(f"/admin/users/{telegram_id}", "Invalid episode ID.")
        episode = await repo.get_episode(episode_id)
        if not episode:
            _redirect(f"/admin/users/{telegram_id}", "Episode not found.")
        await repo.grant_episode_unlock(telegram_id, episode_id)
        _redirect(f"/admin/users/{telegram_id}", "Episode unlock granted.")

    return await _post_action(request, action)


@require_admin
async def episodes_index(request: web.Request) -> web.Response:
    slug = request.rel_url.query.get("slug", "").strip().lower().replace(" ", "-")
    page = max(0, int(request.rel_url.query.get("page", "0")))
    serials = await repo.list_serials()

    serial = None
    episodes = []
    total = 0
    total_pages = 1

    if slug:
        serial = await repo.get_serial_by_slug(slug)
        if serial:
            episodes, total = await repo.get_episodes(slug, page, EPISODES_PER_PAGE)
            total_pages = max(1, (total + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)

    return _html(
        "episodes.html",
        request,
        flash=_flash_from_query(request),
        serials=serials,
        serial=serial,
        slug=slug,
        episodes=episodes,
        page=page,
        total=total,
        total_pages=total_pages,
        format_date=format_date,
    )


@require_admin
async def episode_delete_confirm(request: web.Request) -> web.Response:
    episode_id = request.match_info["episode_id"]
    if not ObjectId.is_valid(episode_id):
        raise web.HTTPNotFound()
    episode = await repo.get_episode(episode_id)
    if not episode:
        raise web.HTTPFound("/admin/episodes?msg=Episode+not+found")

    slug = request.rel_url.query.get("slug", episode.get("serial_slug", ""))
    page = request.rel_url.query.get("page", "0")
    return _html(
        "episode_delete.html",
        request,
        episode=episode,
        episode_id=episode_id,
        slug=slug,
        page=page,
        format_date=format_date,
    )


@require_admin
async def episode_delete(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        episode_id = req.match_info["episode_id"]
        episode = await repo.delete_episode(episode_id)
        slug = str((await req.post()).get("slug", "")).strip()
        if episode:
            slug = slug or episode.get("serial_slug", "")
            name = episode.get("serial_name", "")
            date_label = format_date(episode["date"])
            msg = f"Deleted {name} — {date_label}."
        else:
            msg = "Episode not found."
        dest = f"/admin/episodes?slug={quote(slug)}" if slug else "/admin/episodes"
        _redirect(dest, msg)

    return await _post_action(request, action)


@require_admin
async def episode_delete_by_date(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        post = await req.post()
        slug = str(post.get("slug", "")).strip().lower().replace(" ", "-")
        date_text = str(post.get("date", "")).strip()
        episode_date = parse_episode_date(date_text)
        if not slug:
            _redirect("/admin/episodes", "Serial slug is required.")
        if not episode_date:
            _redirect(f"/admin/episodes?slug={quote(slug)}", "Could not parse date. Use DD-MM-YYYY.")
        episode = await repo.delete_episode_by_serial_date(slug, episode_date)
        if episode:
            msg = f"Deleted {episode.get('serial_name', '')} — {format_date(episode['date'])}."
        else:
            msg = "Episode not found for that serial and date."
        _redirect(f"/admin/episodes?slug={quote(slug)}", msg)

    return await _post_action(request, action)


@require_admin
async def episode_stats_index(request: web.Request) -> web.Response:
    slug = request.rel_url.query.get("slug", "").strip().lower().replace(" ", "-")
    serials = await repo.list_serials()
    top_episodes = await repo.get_top_viewed_episodes(10)

    serial = None
    all_episodes: list = []
    total = 0
    serial_total_views = 0
    top_serial_ids: set[str] = set()

    if slug:
        serial = await repo.get_serial_by_slug(slug)
        if serial:
            all_episodes = await repo.get_all_episodes_for_serial(slug)
            total = len(all_episodes)
            serial_total_views = await repo.get_serial_episode_view_total(slug)
            top_for_serial = await repo.get_top_viewed_episodes(10, serial_slug=slug)
            top_serial_ids = {str(ep["_id"]) for ep in top_for_serial}

    return _html(
        "episode_stats.html",
        request,
        flash=_flash_from_query(request),
        serials=serials,
        serial=serial,
        slug=slug,
        top_episodes=top_episodes,
        all_episodes=all_episodes,
        total=total,
        serial_total_views=serial_total_views,
        top_serial_ids=top_serial_ids,
        format_date=format_date,
    )


@require_admin
async def episode_detail(request: web.Request) -> web.Response:
    episode_id = request.match_info["episode_id"]
    if not ObjectId.is_valid(episode_id):
        raise web.HTTPNotFound()
    episode = await repo.get_episode(episode_id)
    if not episode:
        raise web.HTTPFound("/admin/episodes/stats?msg=Episode+not+found")

    slug = request.rel_url.query.get("slug", episode.get("serial_slug", ""))
    page = request.rel_url.query.get("page", "0")
    watchers = await repo.get_episode_watchers(episode_id, limit=50)
    views = episode.get("view_count", 0)

    return _html(
        "episode_detail.html",
        request,
        episode=episode,
        episode_id=episode_id,
        slug=slug,
        page=page,
        views=views,
        watchers=watchers,
        format_date=format_date,
        format_datetime=format_datetime,
    )


@require_admin
async def serials_list(request: web.Request) -> web.Response:
    page = max(0, int(request.rel_url.query.get("page", "0")))
    serials, total = await repo.list_serials_admin(page, SERIALS_PER_PAGE)
    total_pages = max(1, (total + SERIALS_PER_PAGE - 1) // SERIALS_PER_PAGE)
    return _html(
        "serials.html",
        request,
        flash=_flash_from_query(request),
        serials=serials,
        page=page,
        total=total,
        total_pages=total_pages,
    )


@require_admin
async def serial_new_page(request: web.Request) -> web.Response:
    return _html(
        "serial_form.html",
        request,
        mode="create",
        form_action="/admin/serials/new",
        name="",
        aliases="",
        slug="",
        error=request.rel_url.query.get("error"),
    )


@require_admin
async def serial_create(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        post = await req.post()
        raw_name = str(post.get("name", "")).strip()
        raw_aliases = str(post.get("aliases", "")).strip()

        name, pipe_aliases = parse_add_serial_input(raw_name)
        if raw_aliases:
            extra = [part.strip() for part in raw_aliases.split(",") if part.strip()]
            aliases = list(dict.fromkeys(pipe_aliases + extra))
        else:
            aliases = pipe_aliases

        doc, err = await repo.create_serial(name, aliases)
        if not doc:
            return _html(
                "serial_form.html",
                req,
                mode="create",
                form_action="/admin/serials/new",
                name=raw_name,
                aliases=raw_aliases,
                slug="",
                error=err.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""),
            )
        _redirect("/admin/serials", f"Created serial {doc['name']}.")

    return await _post_action(request, action)


@require_admin
async def serial_edit_page(request: web.Request) -> web.Response:
    slug = request.match_info["slug"]
    serial = await repo.get_serial_by_slug(slug)
    if not serial or not serial.get("active", True):
        raise web.HTTPFound("/admin/serials?msg=Serial+not+found")
    aliases = ", ".join(serial.get("aliases") or [])
    return _html(
        "serial_form.html",
        request,
        mode="edit",
        form_action=f"/admin/serials/{slug}/edit",
        name=serial.get("name", ""),
        aliases=aliases,
        slug=slug,
        error=request.rel_url.query.get("error"),
    )


@require_admin
async def serial_update(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        slug = req.match_info["slug"]
        post = await req.post()
        raw_name = str(post.get("name", "")).strip()
        raw_aliases = str(post.get("aliases", "")).strip()
        name, pipe_aliases = parse_add_serial_input(raw_name)
        if raw_aliases:
            extra = [part.strip() for part in raw_aliases.split(",") if part.strip()]
            aliases = list(dict.fromkeys(pipe_aliases + extra))
        else:
            aliases = pipe_aliases

        doc, err = await repo.update_serial(slug, name, aliases)
        if not doc:
            return _html(
                "serial_form.html",
                req,
                mode="edit",
                form_action=f"/admin/serials/{slug}/edit",
                name=raw_name,
                aliases=raw_aliases,
                slug=slug,
                error=err,
            )
        _redirect("/admin/serials", f"Updated {doc['name']}.")

    return await _post_action(request, action)


@require_admin
async def serial_delete_confirm(request: web.Request) -> web.Response:
    slug = request.match_info["slug"]
    serial = await repo.get_serial_by_slug(slug)
    if not serial or not serial.get("active", True):
        raise web.HTTPFound("/admin/serials?msg=Serial+not+found")
    episode_count = await get_db().episodes.count_documents({"serial_slug": slug})
    return _html(
        "serial_delete.html",
        request,
        serial=serial,
        episode_count=episode_count,
    )


@require_admin
async def serial_delete(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        slug = req.match_info["slug"]
        serial, ep_count = await repo.delete_serial(slug)
        if not serial:
            _redirect("/admin/serials", "Serial not found.")
        name = serial.get("name", slug)
        _redirect("/admin/serials", f"Deleted {name} and {ep_count} episode(s).")

    return await _post_action(request, action)


@require_admin
async def settings_page(request: web.Request) -> web.Response:
    free_limit = await get_free_daily_limit()
    trial_ttl = await get_trial_episode_ttl_seconds()
    return _html(
        "settings.html",
        request,
        flash=_flash_from_query(request),
        free_limit=free_limit,
        free_limit_label=format_free_limit_label(free_limit),
        trial_ttl=trial_ttl,
        trial_ttl_label=format_trial_ttl_label(trial_ttl),
        free_limit_presets=FREE_LIMIT_PRESETS,
        trial_presets=TRIAL_PRESETS,
    )


@require_admin
async def settings_free_limit(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        post = await req.post()
        raw = str(post.get("limit", "")).strip()
        if not raw.isdigit():
            _redirect("/admin/settings", "Invalid limit value.")
        limit = await set_free_daily_limit(int(raw))
        _redirect("/admin/settings", f"Free limit set to {format_free_limit_label(limit)}.")

    return await _post_action(request, action)


@require_admin
async def settings_trial(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        post = await req.post()
        seconds_raw = str(post.get("seconds", "")).strip()
        duration = str(post.get("duration", "")).strip()

        if seconds_raw.isdigit():
            seconds = int(seconds_raw)
        elif duration:
            parsed = parse_trial_ttl_setting(duration)
            if parsed is None:
                _redirect("/admin/settings", "Could not parse duration. Try off, 10s, 1min, 2hr.")
            seconds = parsed
        else:
            _redirect("/admin/settings", "Choose a preset or enter a duration.")

        seconds = await set_trial_episode_ttl_seconds(seconds)
        _redirect("/admin/settings", f"Trial timer set to {format_trial_ttl_label(seconds)}.")

    return await _post_action(request, action)


@require_admin
async def requests_list(request: web.Request) -> web.Response:
    requests_list_data = await repo.get_open_episode_requests(100)
    return _html(
        "requests.html",
        request,
        flash=_flash_from_query(request),
        requests=requests_list_data,
        format_datetime=format_datetime,
    )


@require_admin
async def request_close(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        request_id = req.match_info["request_id"]
        ok = await repo.close_episode_request(request_id)
        msg = "Request closed." if ok else "Request not found or already closed."
        _redirect("/admin/requests", msg)

    return await _post_action(request, action)


@require_admin
async def support_list(request: web.Request) -> web.Response:
    tickets = await repo.get_open_support_tickets(100)
    return _html(
        "support.html",
        request,
        flash=_flash_from_query(request),
        tickets=tickets,
        format_datetime=format_datetime,
    )


@require_admin
async def support_reply(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        ticket_id = req.match_info["ticket_id"]
        post = await req.post()
        reply_text = str(post.get("reply", "")).strip()
        if not reply_text:
            _redirect("/admin/support", "Reply cannot be empty.")
        bot = _create_bot(req)
        try:
            ok, msg = await admin_actions.reply_support_ticket(
                bot, ticket_id, reply_text, req["admin_id"]
            )
        finally:
            await bot.session.close()
        _redirect("/admin/support", msg if ok else f"Error: {msg}")

    return await _post_action(request, action)


@require_admin
async def broadcast_page(request: web.Request) -> web.Response:
    return _html("broadcast.html", request, flash=_flash_from_query(request))


@require_admin
async def broadcast_send(request: web.Request) -> web.Response:
    async def action(req: web.Request) -> web.Response:
        post = await req.post()
        message = str(post.get("message", "")).strip()
        if not message:
            _redirect("/admin/broadcast", "Message cannot be empty.")
        bot = _create_bot(req)
        try:
            sent, total = await admin_actions.broadcast_message(bot, message)
        finally:
            await bot.session.close()
        _redirect("/admin/broadcast", f"Broadcast sent to {sent}/{total} users.")

    return await _post_action(request, action)


async def static_file(request: web.Request) -> web.Response:
    name = request.match_info["path"]
    if ".." in name or name.startswith("/"):
        raise web.HTTPNotFound()
    path = STATIC_DIR / name
    if not path.is_file():
        raise web.HTTPNotFound()
    content_type = "text/css" if name.endswith(".css") else "application/octet-stream"
    return web.FileResponse(path, headers={"Content-Type": content_type})


def setup_admin_routes(app: web.Application, create_bot) -> None:
    if not web_admin_enabled():
        logger.warning("Web admin disabled — set ADMIN_SECRET and ADMIN_IDS to enable /admin")
        return

    app["create_bot"] = create_bot
    app.router.add_get("/admin", admin_entry)
    app.router.add_get("/admin/login", login_page)
    app.router.add_post("/admin/login", login_submit)
    app.router.add_post("/admin/logout", logout)
    app.router.add_get("/admin/logout", logout)
    app.router.add_get("/admin/", dashboard)
    app.router.add_get("/admin/users", users_list)
    app.router.add_get("/admin/users/{telegram_id:\\d+}", user_detail)
    app.router.add_get("/admin/referrals", referrals_list)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/ban", user_ban)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/unban", user_unban)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/vip", user_grant_vip)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/revoke-vip", user_revoke_vip)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/notify", user_grant_notify)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/revoke-notify", user_revoke_notify)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/unlock", user_grant_unlock)
    app.router.add_post("/admin/users/{telegram_id:\\d+}/delete", user_delete)
    app.router.add_get("/admin/serials", serials_list)
    app.router.add_get("/admin/serials/new", serial_new_page)
    app.router.add_post("/admin/serials/new", serial_create)
    app.router.add_get("/admin/serials/{slug}/edit", serial_edit_page)
    app.router.add_post("/admin/serials/{slug}/edit", serial_update)
    app.router.add_get("/admin/serials/{slug}/delete", serial_delete_confirm)
    app.router.add_post("/admin/serials/{slug}/delete", serial_delete)
    app.router.add_get("/admin/episodes", episodes_index)
    app.router.add_get("/admin/episodes/stats", episode_stats_index)
    app.router.add_get("/admin/episodes/view/{episode_id}", episode_detail)
    app.router.add_post("/admin/episodes/delete-by-date", episode_delete_by_date)
    app.router.add_get("/admin/episodes/delete/{episode_id}", episode_delete_confirm)
    app.router.add_post("/admin/episodes/delete/{episode_id}", episode_delete)
    app.router.add_get("/admin/settings", settings_page)
    app.router.add_post("/admin/settings/free-limit", settings_free_limit)
    app.router.add_post("/admin/settings/trial", settings_trial)
    app.router.add_get("/admin/requests", requests_list)
    app.router.add_post("/admin/requests/{request_id}/close", request_close)
    app.router.add_get("/admin/support", support_list)
    app.router.add_post("/admin/support/{ticket_id}/reply", support_reply)
    app.router.add_get("/admin/broadcast", broadcast_page)
    app.router.add_post("/admin/broadcast", broadcast_send)
    app.router.add_get("/admin/notify-membership", notify_membership_page)
    app.router.add_post("/admin/notify-membership/promo", notify_membership_promo_send)
    app.router.add_get("/admin/static/{path:.+}", static_file)
    logger.info("Web admin panel enabled at /admin")
