from datetime import datetime

from config import EPISODES_PER_PAGE, FREE_DAILY_LIMIT, TZ, SERIALS_PER_PAGE
from database import repository as repo
from database.datetime_utils import ensure_aware


def format_date(dt: datetime) -> str:
    return dt.strftime("%d %B %Y")


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d %B %Y, %I:%M %p")


def plan_label(user: dict) -> str:
    if user.get("plan") == "vip":
        return "VIP Member"
    return "Free Tier"


def _usage_summary(user: dict) -> str:
    watched = user.get("daily_watches", 0)
    if user.get("plan") == "vip":
        return "Unlimited (VIP)"
    remaining = max(0, FREE_DAILY_LIMIT - watched)
    return f"{watched}/{FREE_DAILY_LIMIT} used · {remaining} left today"


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


def build_status_text(user: dict, *, is_admin: bool = False) -> str:
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
        f"Episodes: <b>{_usage_summary(user)}</b>",
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
        lines.append("\n🛠 <b>Admin:</b> send /admin")

    return "\n".join(lines)

def build_user_info_text(user: dict, *, is_admin: bool = False) -> str:
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
        f"Episodes: <b>{_usage_summary(user)}</b>",
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
        lines.append("\n🛠 <b>Admin:</b> send /admin to open the panel.")

    return "\n".join(lines)


def build_plan_text(user: dict) -> str:
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
        f"Daily usage: <b>{_usage_summary(user)}</b>",
    ]
    registered = user.get("registered_at")
    if registered:
        lines.append(f"Registered: {format_date(registered)}")

    unlocks = user.get("unlocked_episodes", [])
    if unlocks:
        lines.append(f"Active unlocks: <b>{len(unlocks)}</b> episode(s)")

    lines.extend(
        [
            "",
            "Free users get 3 episodes/day.",
            "VIP: unlimited access · ₹99/month",
            "Single unlock: ₹10/episode",
        ]
    )
    return "\n".join(lines)


async def build_episode_list_text(
    serial: dict, page: int, user: dict | None = None
) -> tuple[str, int]:
    episodes, total = await repo.get_episodes(serial["slug"], page, EPISODES_PER_PAGE)
    if total == 0:
        return (
            f"📺 <b>{serial['name']}</b>\n\n"
            "No episodes uploaded yet.\n"
            "Use 📺 Request Episode to ask for one.",
            0,
        )

    total_pages = max(1, (total + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    lines = [
        f"📺 <b>{serial['name']}</b>",
        f"<b>{total}</b> episode(s) available · Page {page + 1}/{total_pages}",
        "",
        "Select an episode to watch:",
    ]
    if (
        user
        and user.get("plan") != "vip"
        and user.get("daily_watches", 0) >= FREE_DAILY_LIMIT
    ):
        lines.extend(
            [
                "",
                "🔒 <b>Daily limit reached</b> — locked episodes need VIP or ₹10 unlock.",
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
