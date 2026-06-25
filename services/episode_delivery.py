import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import STORAGE_CHANNEL_IDS
from services.messages import format_date

logger = logging.getLogger(__name__)


def _delivery_channel_candidates(episode: dict) -> list[int]:
    candidates: list[int] = []
    stored = episode.get("storage_channel_id")
    if stored is not None:
        candidates.append(int(stored))
    for channel_id in STORAGE_CHANNEL_IDS:
        if channel_id not in candidates:
            candidates.append(channel_id)
    return candidates


async def deliver_episode_to_user(
    bot: Bot, user_id: int, episode: dict
) -> tuple[bool, str, int | None]:
    """Send episode video to the user's private chat. Returns (ok, error, message_id)."""
    caption = (
        f"📺 <b>{episode.get('serial_name', '')}</b>\n"
        f"📅 {format_date(episode['date'])}"
    )

    message_id = episode.get("message_id")
    if message_id:
        for from_chat_id in _delivery_channel_candidates(episode):
            try:
                sent = await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                    caption=caption,
                    protect_content=True,
                    parse_mode="HTML",
                )
                return True, "", sent.message_id
            except TelegramForbiddenError:
                return False, "Please open the bot and send /start first, then try again.", None
            except TelegramBadRequest as exc:
                logger.warning(
                    "copy_message failed for episode %s from channel %s: %s",
                    episode.get("_id"),
                    from_chat_id,
                    exc,
                )

    file_id = episode.get("file_id")
    if not file_id:
        return False, "Episode video is not available. Contact support.", None

    try:
        sent = await bot.send_video(
            chat_id=user_id,
            video=file_id,
            caption=caption,
            protect_content=True,
            parse_mode="HTML",
        )
        return True, "", sent.message_id
    except TelegramBadRequest:
        try:
            sent = await bot.send_document(
                chat_id=user_id,
                document=file_id,
                caption=caption,
                protect_content=True,
                parse_mode="HTML",
            )
            return True, "", sent.message_id
        except TelegramForbiddenError:
            return False, "Please open the bot and send /start first, then try again.", None
        except TelegramBadRequest as exc:
            logger.exception("Failed to deliver episode %s", episode.get("_id"))
            return False, f"Failed to deliver video: {exc.message}", None
    except TelegramForbiddenError:
        return False, "Please open the bot and send /start first, then try again.", None
    except Exception:
        logger.exception("Failed to deliver episode %s", episode.get("_id"))
        return False, "Failed to deliver video. Contact support.", None

    return False, "Failed to deliver video. Contact support.", None
