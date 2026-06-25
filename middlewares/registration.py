import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from database import repository as repo
from services.admin_notifications import notify_admins_new_user

logger = logging.getLogger(__name__)


class UserRegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        is_new_user = False
        try:
            if isinstance(event, Message) and event.from_user:
                user, is_new_user = await repo.get_or_create_user(
                    event.from_user.id,
                    event.from_user.username,
                    event.from_user.first_name,
                )
            elif isinstance(event, CallbackQuery) and event.from_user:
                user, is_new_user = await repo.get_or_create_user(
                    event.from_user.id,
                    event.from_user.username,
                    event.from_user.first_name,
                )
        except Exception:
            logger.exception("User registration failed")
            if isinstance(event, Message):
                await event.answer("⚠️ Database error. Please try again in a moment.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Database error.", show_alert=True)
            return None

        if user:
            data["db_user"] = user
            data["is_new_user"] = is_new_user
            if is_new_user and event.from_user:
                try:
                    await notify_admins_new_user(
                        event.bot,
                        event.from_user.id,
                        username=event.from_user.username,
                        first_name=event.from_user.first_name,
                    )
                except Exception:
                    logger.exception("Failed to notify admins about new user")
            if user.get("banned") and not (
                isinstance(event, Message)
                and event.text
                and (event.text.startswith("/admin") or event.text.startswith("/ping"))
            ):
                if isinstance(event, Message):
                    await event.answer("🚫 Your account has been suspended. Contact support.")
                    return None
                if isinstance(event, CallbackQuery):
                    await event.answer("Account suspended.", show_alert=True)
                    return None

        return await handler(event, data)
