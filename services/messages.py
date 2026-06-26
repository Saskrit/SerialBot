from datetime import datetime

from config import EPISODES_PER_PAGE, REFERRAL_BONUS_WATCHES, TZ, SERIALS_PER_PAGE
from database import repository as repo
from database.datetime_utils import ensure_aware
from services.date_query import UserDateQuery, format_user_date_label
from services.membership import (
    MONTHLY_VIP,
    VIP_PRIVILEGES,
    get_plan,
)
from services.payment_contact import payment_contact_label
from services.settings import format_free_limit_label, get_free_daily_limit, is_free_unlimited

DATE_EPISODES_PER_PAGE = 8


def format_date(dt: datetime) -> str:
    return dt.strftime("%d %B %Y")


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d %B %Y, %I:%M %p")


def plan_label(user: dict) -> str:
    if user.get("plan") == "vip":
        tier_id = user.get("membership_tier")
        tier = get_plan(tier_id) if tier_id else None
        if tier:
            return tier.name
        return "VIP Member"
    if repo.has_active_daily_pass(user):
        return "Daily Unlimited Pass"
    return "Free Tier"


def _daily_pass_remaining(user: dict) -> str | None:
    if not repo.has_active_daily_pass(user):
        return None
    expires = ensure_aware(user.get("daily_pass_expires"))
    if not expires:
        return None
    now = datetime.now(TZ)
    if expires <= now:
        return None
    delta = expires - now
    hours = delta.seconds // 3600 + delta.days * 24
    minutes = (delta.seconds % 3600) // 60
    if hours > 0:
        return f"{hours} hour(s) {minutes} min remaining"
    return f"{minutes} minute(s) remaining"


def _usage_summary(user: dict, *, daily_limit: int) -> str:
    watched = user.get("daily_watches", 0)
    bonus = user.get("referral_watch_credits", 0)
    if user.get("plan") == "vip":
        return "Unlimited (VIP)"
    if repo.has_active_daily_pass(user):
        remaining = _daily_pass_remaining(user)
        base = "Unlimited (Daily Pass · 24h)"
        if remaining:
            base += f" · {remaining}"
        return base
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
                f"Contact {payment_contact_label()} for VIP membership.",
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
    lines = [
        "📋 <b>My Membership</b>",
        "",
        f"Plan: <b>{plan_label(user)}</b>",
        f"Status: {'🚫 Banned' if user.get('banned') else '✅ Active'}",
    ]

    registered = user.get("registered_at")
    if registered:
        lines.append(f"Registered: <b>{format_date(registered)}</b>")

    lines.extend(
        [
            "",
            "📊 <b>Today's Usage</b>",
            f"Episodes: <b>{_usage_summary(user, daily_limit=daily_limit)}</b>",
        ]
    )

    bonus = user.get("referral_watch_credits", 0)
    if bonus > 0:
        lines.append(f"Bonus credits: <b>{bonus}</b> watch(es)")

    invites = user.get("referral_count", 0)
    lines.append(f"Total referrals: <b>{invites}</b>")

    unlocks = user.get("unlocked_episodes", [])
    if unlocks:
        lines.append(f"Purchased episodes: <b>{len(unlocks)}</b> permanent unlock(s)")

    if user.get("plan") == "vip":
        lines.extend(["", "⭐ <b>VIP Privileges</b>"])
        for perk in VIP_PRIVILEGES:
            lines.append(f"✅ {perk}")
        expires = ensure_aware(user.get("vip_expires"))
        if expires:
            lines.append(f"\nVIP expires: <b>{format_datetime(expires)}</b>")
            remaining = _vip_time_remaining(user)
            if remaining:
                lines.append(f"Time remaining: <b>{remaining}</b>")
    elif repo.has_active_daily_pass(user):
        expires = ensure_aware(user.get("daily_pass_expires"))
        if expires:
            lines.append(f"\nDaily Pass expires: <b>{format_datetime(expires)}</b>")
            remaining = _daily_pass_remaining(user)
            if remaining:
                lines.append(f"Time remaining: <b>{remaining}</b>")
    else:
        free_line = (
            "Free users currently have unlimited daily episodes."
            if is_free_unlimited(daily_limit)
            else f"Free tier: {format_free_limit_label(daily_limit)}."
        )
        lines.extend(
            [
                "",
                free_line,
                f"🎁 Refer friends — you and your friend each get <b>{REFERRAL_BONUS_WATCHES}</b> bonus watches.",
            ]
        )

    lines.extend(
        [
            "",
            f"Upgrade or renew via <b>{payment_contact_label()}</b>.",
            f"⭐ <b>{MONTHLY_VIP.name}</b> ({MONTHLY_VIP.price_label}) is our recommended plan.",
        ]
    )
    return "\n".join(lines)


def build_membership_catalog_text() -> str:
    lines = [
        "⭐ <b>Membership Plans</b>",
        "",
        "Choose the plan that fits you. Contact payment after selecting a plan.",
        "",
        f"<b>Episode Pass</b> — ₹10",
        "Unlock one episode · permanent access",
        "",
        f"<b>Daily Unlimited Pass</b> — ₹19",
        "Unlimited for 24 hours · binge watching",
        "",
        f"<b>Weekly VIP</b> — ₹39 · 7 days",
        f"<b>Monthly VIP</b> — ₹99 · 30 days ⭐ <b>Recommended</b>",
        f"<b>Quarterly VIP</b> — ₹249 · 90 days 💎 <b>Best Value</b>",
        f"<b>Annual VIP</b> — ₹799 · 12 months 🏆 <b>Maximum Savings</b>",
        "",
        "<b>VIP Privileges</b>",
    ]
    for perk in VIP_PRIVILEGES:
        lines.append(f"• {perk}")
    return "\n".join(lines)


async def build_upgrade_screen_text(user: dict, *, episode_id: str | None = None) -> str:
    daily_limit = await get_free_daily_limit()
    lines = [
        "⏳ <b>Daily limit reached</b>",
        "",
        f"Today's usage: <b>{_usage_summary(user, daily_limit=daily_limit)}</b>",
        "",
        "Upgrade to keep watching — compare plans below:",
        "",
        "⏳ <b>Continue Free Tomorrow</b> — limit resets at midnight",
        "🔓 <b>Episode Pass</b> — ₹10 · unlock this episode permanently",
        "⚡ <b>Daily Unlimited Pass</b> — ₹19 · unlimited for 24 hours",
        "📅 <b>Weekly VIP</b> — ₹39 · 7 days unlimited",
        f"⭐ <b>Monthly VIP</b> — ₹99 · 30 days <b>(Recommended)</b>",
        "💎 <b>Quarterly VIP</b> — ₹249 · 90 days (Best Value)",
        "🏆 <b>Annual VIP</b> — ₹799 · 12 months (Maximum Savings)",
    ]
    if episode_id:
        lines.append(f"\nSelected episode: <code>{episode_id}</code>")
    bonus = user.get("referral_watch_credits", 0)
    if bonus > 0:
        lines.append(f"\nYou still have <b>{bonus}</b> bonus watch credit(s) for other episodes.")
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
                "🔒 <b>Daily limit reached</b> — upgrade or use bonus watches.",
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
                "🔒 <b>Daily limit reached</b> — upgrade or use bonus watches.",
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
