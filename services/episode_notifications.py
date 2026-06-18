import asyncio
import logging

from aiogram import Bot

from config import NOTIFY_ON_NEW_EPISODE
from database import repository as repo
from keyboards.inline import new_episode_notification_keyboard
from services.messages import format_date

logger = logging.getLogger(__name__)

NOTIFY_DELAY_SEC = 0.05


def schedule_new_episode_notification(
    bot: Bot,
    serial_name: str,
    serial_slug: str,
    episode_date,
    episode_id: str,
) -> None:
    if not NOTIFY_ON_NEW_EPISODE:
        return
    asyncio.create_task(
        notify_users_new_episode(bot, serial_name, serial_slug, episode_date, episode_id)
    )


async def notify_users_new_episode(
    bot: Bot,
    serial_name: str,
    serial_slug: str,
    episode_date,
    episode_id: str,
) -> int:
    text = (
        "🆕 <b>New Episode Added!</b>\n\n"
        f"📺 <b>{serial_name}</b>\n"
        f"📅 {format_date(episode_date)}\n\n"
        "Tap below to watch now."
    )
    keyboard = new_episode_notification_keyboard(serial_slug, episode_id)
    user_ids = await repo.get_all_user_ids()

    from config import ADMIN_IDS

    sent = 0
    for user_id in user_ids:
        if user_id in ADMIN_IDS:
            continue
        try:
            await bot.send_message(
                user_id,
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(NOTIFY_DELAY_SEC)

    logger.info(
        "New episode notification: %s — %s sent to %s/%s users",
        serial_name,
        format_date(episode_date),
        sent,
        len(user_ids),
    )
    return sent
