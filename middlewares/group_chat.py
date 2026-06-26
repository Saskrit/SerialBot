import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import STORAGE_CHANNEL_IDS
from services.chat_scope import is_relevant_group_message_text

logger = logging.getLogger(__name__)


def _chat_from_event(event: TelegramObject):
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat
    return None


class GroupChatMiddleware(BaseMiddleware):
    """Private chats: full bot. Groups: only serial/date/greeting/status/commands.

    Random group conversation is ignored so members can chat normally.
    Inline button taps in groups are always allowed (user already engaged the bot).
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

        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        if isinstance(event, Message):
            text = event.text
            if text and await is_relevant_group_message_text(text):
                return await handler(event, data)
            return None

        return None
