import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.enums import ChatType
from aiogram.types import ErrorEvent, Message

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("ping"))
async def ping(message: Message):
    if message.chat.type != ChatType.PRIVATE:
        return
    await message.answer("✅ Bot is online and receiving your messages.")


@router.errors()
async def on_error(event: ErrorEvent):
    logger.exception(
        "Handler error (update=%s): %s",
        event.update.update_id if event.update else "?",
        event.exception,
    )
    update = event.update
    if update and update.message and update.message.chat.type == ChatType.PRIVATE:
        try:
            await update.message.answer(
                "⚠️ Something went wrong. Please try again or send /start."
            )
        except Exception:
            pass
