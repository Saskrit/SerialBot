from datetime import datetime

from config import EPISODES_PER_PAGE
from database import repository as repo


def format_date(dt: datetime) -> str:
    return dt.strftime("%d %B %Y")


def plan_label(user: dict) -> str:
    if user.get("plan") == "vip":
        return "VIP Monthly"
    return "Free Tier"


def build_plan_text(user: dict) -> str:
    from config import FREE_DAILY_LIMIT

    lines = [
        "📋 <b>My Plan</b>",
        "",
        f"Plan: <b>{plan_label(user)}</b>",
        f"Status: {'🚫 Banned' if user.get('banned') else '✅ Active'}",
        f"Daily usage: <b>{user.get('daily_watches', 0)}/{FREE_DAILY_LIMIT}</b> episodes",
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
