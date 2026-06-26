"""Decide whether a group message should reach bot handlers."""

from __future__ import annotations

from services.date_query import parse_user_date_query
from services.greetings import is_greeting, is_status_query
from services.serial_matcher import match_serial

BOT_MENU_BUTTONS = frozenset(
    {
        "🔍 Search Serial",
        "📚 Browse Serials",
        "📋 My Plan",
        "📋 My Membership",
        "⭐ Get VIP",
        "✅ VIP Member",
        "📺 Request Episode",
        "💬 Support",
        "🎁 Refer & Watch",
        "❌ Close Menu",
    }
)


def is_obvious_bot_text(text: str) -> bool:
    """Fast checks that do not need the database."""
    if text.startswith("/"):
        return True
    if text in BOT_MENU_BUTTONS:
        return True
    if is_greeting(text) or is_status_query(text):
        return True
    if parse_user_date_query(text):
        return True
    return False


async def is_relevant_group_message_text(text: str) -> bool:
    """True when group chat text is a serial name, date, greeting, status, etc."""
    if is_obvious_bot_text(text):
        return True
    return await match_serial(text) is not None
