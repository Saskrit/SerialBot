from datetime import datetime

from config import EPISODES_PER_PAGE, TZ, SERIALS_PER_PAGE
from database import repository as repo
from database.datetime_utils import ensure_aware
from services.date_query import UserDateQuery, format_user_date_label
from services.settings import format_free_limit_label, get_free_daily_limit, is_free_unlimited

DATE_EPISODES_PER_PAGE = 8


def format_date(dt: datetime) -> str:
    return dt.strftime("%d %B %Y")


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d %B %Y, %I:%M %p")


def plan_label(user: dict) -> str:
    if user.get("plan") == "vip":
        return "VIP Member"
    return "Free Tier"


def _usage_summary(user: dict, *, daily_limit: int) -> str:
    watched = user.get("daily_watches", 0)
    bonus = user.get("referral_watch_credits", 0)
    if user.get("plan") == "vip":
        return "Unlimited (VIP)"
    if is_free_unlimited(daily_limit):
        base = f"{watched} watched today · unlimited free access"
    else:
        remaining = max(0, daily_limit - watched)
        base = f"{watched}/{daily_limit} daily · {remaining} left today"
    if bonus > 0:
        base += f" · {bonus} bonus invite watch(es)"
    return base


async def usage_summary(user: dict) -> str:
    limit = await get_free_daily_limit()
    return _usage_summary(user, daily_limit=limit)


def _vip_time_remaining(user: dict) -> str | None:
    if user.get("plan") != "vip":
        return None
    expires = ensure_aware(user.get("vip_expires"))
    if not expires:
        return None
    now = datetime.now(TZ)
    if expires <= now:
        return "Expired — renew to continue VIP access"
    delta = expires - now
    days = delta.days
    hours = (delta.seconds // 3600) % 24
    if days > 0:
        return f"{days} day(s) {hours} hour(s) remaining"
    if hours > 0:
        return f"{hours} hour(s) remaining"
    minutes = delta.seconds // 60
    return f"{minutes} minute(s) remaining"


async def build_status_text(user: dict, *, is_admin: bool = False) -> str:
    daily_limit = await get_free_daily_limit()
    name = user.get("first_name") or "there"
    username = user.get("username")
    username_line = f"@{username}" if username else "Not set"

    lines = [
        "📋 <b>Your Status</b>",
        "",
        f"Name: <b>{name}</b>",
        f"Telegram ID: <code>{user['telegram_id']}</code>",
        f"Username: {username_line}",
        f"Plan: <b>{plan_label(user)}</b>",
        f"Account: {'🚫 Banned' if user.get('banned') else '✅ Active'}",
        "",
        "📊 <b>Usage Today</b>",
        f"Episodes: <b>{_usage_summary(user, daily_limit=daily_limit)}</b>",
    ]

    registered = user.get("registered_at")
    if registered:
        lines.append(f"Member since: {format_date(registered)}")

    if user.get("plan") == "vip":
        lines.extend(["", "⭐ <b>You are a VIP Member</b>"])
        expires = ensure_aware(user.get("vip_expires"))
        if expires:
            lines.append(f"Expires on: <b>{format_datetime(expires)}</b>")
            remaining = _vip_time_remaining(user)
            if remaining:
                lines.append(f"Time remaining: <b>{remaining}</b>")
        else:
            lines.append("Unlimited episodes · full archive access")

    unlocks = user.get("unlocked_episodes", [])
    if unlocks:
        lines.append(f"\n🔓 Unlocked episodes: <b>{len(unlocks)}</b>")

    if user.get("plan") != "vip":
        lines.extend(
            [
                "",
                "Upgrade to VIP for unlimited episodes · ₹99/month",
            ]
        )

    if is_admin:
        lines.append("\n🛠 <b>Admin:</b> /admin in Telegram · web panel at <code>/admin</code>")

    return "\n".join(lines)

async def build_user_info_text(user: dict, *, is_admin: bool = False) -> str:
    daily_limit = await get_free_daily_limit()
    name = user.get("first_name") or "there"
    username = user.get("username")
    username_line = f"@{username}" if username else "Not set"

    lines = [
        f"👋 Hi, <b>{name}</b>!",
        "",
        "👤 <b>Your Account</b>",
        f"Telegram ID: <code>{user['telegram_id']}</code>",
        f"Username: {username_line}",
        f"Plan: <b>{plan_label(user)}</b>",
        f"Status: {'🚫 Banned' if user.get('banned') else '✅ Active'}",
        "",
        "📊 <b>Usage Today</b>",
        f"Episodes: <b>{_usage_summary(user, daily_limit=daily_limit)}</b>",
    ]

    registered = user.get("registered_at")
    if registered:
        lines.append(f"Member since: {format_date(registered)}")

    if user.get("plan") == "vip":
        lines.extend(
            [
                "",
                "⭐ <b>You are a VIP Member</b>",
                "Unlimited episodes · full archive access",
            ]
        )
        expires = ensure_aware(user.get("vip_expires"))
        if expires:
            lines.append(f"VIP expires: <b>{format_date(expires)}</b>")
            remaining = _vip_time_remaining(user)
            if remaining:
                lines.append(f"Time remaining: <b>{remaining}</b>")
    else:
        unlocks = user.get("unlocked_episodes", [])
        if unlocks:
            lines.append(f"Unlocked episodes: <b>{len(unlocks)}</b>")

    lines.extend(
        [
            "",
            "🔍 Type a serial name to start watching.",
        ]
    )

    if is_admin:
        lines.append("\n🛠 <b>Admin:</b> /admin in Telegram · web panel at <code>/admin</code>")

    return "\n".join(lines)


async def build_plan_text(user: dict) -> str:
    daily_limit = await get_free_daily_limit()
    if user.get("plan") == "vip":
        lines = [
            "📋 <b>My Plan</b>",
            "",
            "⭐ <b>You are a VIP Member</b>",
            "",
            "✅ Unlimited episodes daily",
            "✅ Full archive access",
            "✅ Episode request priority",
            "✅ Priority support",
        ]
        expires = ensure_aware(user.get("vip_expires"))
        if expires:
            lines.append(f"\nValid until: <b>{format_date(expires)}</b>")
            remaining = _vip_time_remaining(user)
            if remaining:
                lines.append(f"Time remaining: <b>{remaining}</b>")
        return "\n".join(lines)

    lines = [
        "📋 <b>My Plan</b>",
        "",
        f"Plan: <b>{plan_label(user)}</b>",
        f"Status: {'🚫 Banned' if user.get('banned') else '✅ Active'}",
        f"Daily usage: <b>{_usage_summary(user, daily_limit=daily_limit)}</b>",
    ]
    registered = user.get("registered_at")
    if registered:
        lines.append(f"Registered: {format_date(registered)}")

    unlocks = user.get("unlocked_episodes", [])
    if unlocks:
        lines.append(f"Active unlocks: <b>{len(unlocks)}</b> episode(s)")

    invites = user.get("referral_count", 0)
    bonus = user.get("referral_watch_credits", 0)
    if invites or bonus:
        lines.append(f"Referrals: <b>{invites}</b> invite(s) · <b>{bonus}</b> bonus watch(es)")

    free_line = (
        "Free users have unlimited daily episodes."
        if is_free_unlimited(daily_limit)
        else f"Free users get {format_free_limit_label(daily_limit)}."
    )
    lines.extend(
        [
            "",
            free_line,
            f"🎁 Invite friends — each join gives <b>5 bonus watches</b> (tap Refer & Watch).",
            "VIP: unlimited access · ₹99/month",
            "Single unlock: ₹10/episode",
        ]
    )
    return "\n".join(lines)


def format_month_year(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B %Y")


async def build_episode_list_text(
    serial: dict,
    page: int,
    user: dict | None = None,
    *,
    year: int,
    month: int,
) -> tuple[str, int]:
    episodes, total = await repo.get_episodes_by_month(
        serial["slug"], year, month, page, EPISODES_PER_PAGE
    )
    if total == 0:
        return (
            f"📺 <b>{serial['name']}</b>\n\n"
            f"📅 <b>{format_month_year(year, month)}</b>\n\n"
            "No episodes for this month.",
            0,
        )

    total_pages = max(1, (total + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    lines = [
        f"📺 <b>{serial['name']}</b>",
        f"📅 <b>{format_month_year(year, month)}</b>",
        f"<b>{total}</b> episode(s) · Page {page + 1}/{total_pages}",
        "",
        "Select an episode to watch:",
    ]
    limit = await get_free_daily_limit()
    if (
        user
        and user.get("plan") != "vip"
        and not is_free_unlimited(limit)
        and not await repo.has_free_watch_allowance(user)
    ):
        lines.extend(
            [
                "",
                "🔒 <b>Daily limit reached</b> — use bonus watches, VIP, or ₹10 unlock.",
            ]
        )
    return "\n".join(lines), total_pages


def build_episode_months_text(serial: dict, months: list[dict[str, int]]) -> str:
    total_eps = sum(m["count"] for m in months)
    lines = [
        f"📺 <b>{serial['name']}</b>",
        f"<b>{total_eps}</b> episode(s) available",
        "",
        "📅 <b>Filter by month</b>",
        "Select a month to view episodes:",
    ]
    return "\n".join(lines)


async def build_date_episodes_text(
    episodes: list[dict],
    query: UserDateQuery,
    page: int,
    *,
    user: dict | None = None,
) -> tuple[str, int]:
    label = format_user_date_label(query)
    if not episodes:
        return (
            f"📅 <b>{label}</b>\n\n"
            "No episodes found for this date.\n"
            "Try another date or use 📺 Request Episode.",
            0,
        )

    total_pages = max(1, (len(episodes) + DATE_EPISODES_PER_PAGE - 1) // DATE_EPISODES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * DATE_EPISODES_PER_PAGE
    page_episodes = episodes[start : start + DATE_EPISODES_PER_PAGE]

    lines = [
        f"📅 <b>Episodes for {label}</b>",
        f"<b>{len(episodes)}</b> serial(s) · Page {page + 1}/{total_pages}",
        "",
        "Tap a serial to watch:",
    ]
    for ep in page_episodes:
        year_hint = f" · {ep['date'].year}" if not query.year else ""
        lines.append(f"• <b>{ep.get('serial_name', 'Serial')}</b>{year_hint}")

    limit = await get_free_daily_limit()
    if (
        user
        and user.get("plan") != "vip"
        and not is_free_unlimited(limit)
        and not await repo.has_free_watch_allowance(user)
    ):
        lines.extend(
            [
                "",
                "🔒 <b>Daily limit reached</b> — use bonus watches, VIP, or ₹10 unlock.",
            ]
        )
    return "\n".join(lines), total_pages


async def build_catalog_text(page: int) -> str:
    serials, total = await repo.list_serials_catalog(page, SERIALS_PER_PAGE)
    total_pages = max(1, (total + SERIALS_PER_PAGE - 1) // SERIALS_PER_PAGE)
    with_eps = sum(1 for s in serials if s.get("episode_count", 0) > 0)

    lines = [
        "📚 <b>Browse Serials</b>",
        f"Page {page + 1}/{total_pages} · <b>{total}</b> serials in catalog",
        "",
        "Tap a serial to view its episodes.",
        f"On this page: <b>{with_eps}</b> with episodes available.",
    ]
    return "\n".join(lines)
