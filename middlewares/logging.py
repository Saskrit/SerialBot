import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

logger = logging.getLogger(__name__)


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            uid = event.update_id
            kind = "unknown"
            if event.message:
                kind = f"message:{event.message.chat.type}"
            elif event.callback_query:
                kind = "callback_query"
            elif event.channel_post:
                kind = "channel_post"
            logger.info("Update %s (%s)", uid, kind)
        return await handler(event, data)
