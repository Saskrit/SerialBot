import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import STORAGE_CHANNEL_IDS

logger = logging.getLogger(__name__)


def _chat_from_event(event: TelegramObject):
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat
    return None


class PrivateChatOnlyMiddleware(BaseMiddleware):
    """Drop user-facing updates from normal group chats.

    The bot should only interact in private DMs (and configured storage
    channels). This keeps group conversations between members uninterrupted.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = _chat_from_event(event)
        if chat is None:
            return await handler(event, data)

        if chat.type == ChatType.PRIVATE:
            return await handler(event, data)

        if chat.id in STORAGE_CHANNEL_IDS:
            return await handler(event, data)

        return None
