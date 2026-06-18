import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import STORAGE_CHANNEL_ID
from services.messages import format_date

logger = logging.getLogger(__name__)


async def deliver_episode_to_user(bot: Bot, user_id: int, episode: dict) -> tuple[bool, str]:
    """Send episode video directly to the user's private chat."""
    caption = (
        f"📺 <b>{episode.get('serial_name', '')}</b>\n"
        f"📅 {format_date(episode['date'])}"
    )

    message_id = episode.get("message_id")
    if STORAGE_CHANNEL_ID and message_id:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=STORAGE_CHANNEL_ID,
                message_id=message_id,
                caption=caption,
                protect_content=True,
                parse_mode="HTML",
            )
            return True, ""
        except TelegramForbiddenError:
            return False, "Please open the bot and send /start first, then try again."
        except TelegramBadRequest as exc:
            logger.warning(
                "copy_message failed for episode %s, trying file_id: %s",
                episode.get("_id"),
                exc,
            )

    file_id = episode.get("file_id")
    if not file_id:
        return False, "Episode video is not available. Contact support."

    try:
        await bot.send_video(
            chat_id=user_id,
            video=file_id,
            caption=caption,
            protect_content=True,
            parse_mode="HTML",
        )
        return True, ""
    except TelegramBadRequest:
        try:
            await bot.send_document(
                chat_id=user_id,
                document=file_id,
                caption=caption,
                protect_content=True,
                parse_mode="HTML",
            )
            return True, ""
        except TelegramForbiddenError:
            return False, "Please open the bot and send /start first, then try again."
        except TelegramBadRequest as exc:
            logger.exception("Failed to deliver episode %s", episode.get("_id"))
            return False, f"Failed to deliver video: {exc.message}"
    except TelegramForbiddenError:
        return False, "Please open the bot and send /start first, then try again."
    except Exception:
        logger.exception("Failed to deliver episode %s", episode.get("_id"))
        return False, "Failed to deliver video. Contact support."

    return False, "Failed to deliver video. Contact support."
