import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

logger = logging.getLogger(__name__)

_bot_username: str | None = None


async def get_bot_username(bot: Bot) -> str:
    global _bot_username
    if _bot_username is None:
        me = await bot.get_me()
        _bot_username = me.username or ""
    return _bot_username


def payment_deep_link(bot_username: str, payment_id: str) -> str:
    return f"https://t.me/{bot_username}?start=pay_{payment_id}"


async def send_private_message(bot: Bot, user_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id=user_id, text=text, **kwargs)
        return True
    except TelegramForbiddenError:
        logger.warning("Cannot DM user %s — bot not started", user_id)
        return False
