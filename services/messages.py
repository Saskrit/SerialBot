from datetime import datetime

from config import EPISODES_PER_PAGE, FREE_DAILY_LIMIT
from database import repository as repo


def format_date(dt: datetime) -> str:
    return dt.strftime("%d %B %Y")


def plan_label(user: dict) -> str:
    if user.get("plan") == "vip":
        return "VIP Monthly"
    return "Free Tier"


def _usage_summary(user: dict) -> str:
    watched = user.get("daily_watches", 0)
    if user.get("plan") == "vip":
        return "Unlimited (VIP)"
    remaining = max(0, FREE_DAILY_LIMIT - watched)
    return f"{watched}/{FREE_DAILY_LIMIT} used · {remaining} left today"


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

    if user.get("plan") == "vip" and user.get("vip_expires"):
        lines.append(f"VIP expires: <b>{format_date(user['vip_expires'])}</b>")

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

    if user.get("plan") == "vip" and user.get("vip_expires"):
        lines.append(f"VIP expires: <b>{format_date(user['vip_expires'])}</b>")

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


async def build_episode_list_text(serial: dict, page: int) -> tuple[str, int]:
    episodes, total = await repo.get_episodes(serial["slug"], page, EPISODES_PER_PAGE)
    if total == 0:
        return f"📺 <b>{serial['name']}</b>\n\nNo episodes uploaded yet.", 0

    total_pages = max(1, (total + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    lines = [
        f"📺 <b>{serial['name']}</b>",
        f"Episodes · Page {page + 1}/{total_pages}",
        "",
        "Select an episode to watch:",
    ]
    return "\n".join(lines), total_pages
