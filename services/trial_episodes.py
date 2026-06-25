import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import TZ
from database import repository as repo
from services.settings import format_trial_ttl_label, get_trial_episode_ttl_seconds

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def is_trial_watch(user: dict, episode_id: str) -> bool:
    if user.get("plan") == "vip":
        return False
    if episode_id in user.get("unlocked_episodes", []):
        return False
    ttl = await get_trial_episode_ttl_seconds()
    return ttl > 0


async def apply_trial_delivery(
    bot: Bot,
    user_id: int,
    episode_id: str,
    dm_message_id: int,
    *,
    db_user: dict | None = None,
) -> None:
    ttl = await get_trial_episode_ttl_seconds()
    if ttl <= 0:
        return

    await repo.mark_trial_episode_used(user_id, episode_id)
    if db_user is not None:
        trials = db_user.setdefault("trial_episodes", [])
        if episode_id not in trials:
            trials.append(episode_id)

    delete_at = datetime.now(TZ) + timedelta(seconds=ttl)
    await repo.save_trial_deletion(user_id, episode_id, dm_message_id, delete_at)
    task = asyncio.create_task(
        _delete_trial_message_after(bot, user_id, episode_id, dm_message_id, ttl)
    )
    _track_task(task)

    try:
        await bot.send_message(
            user_id,
            "⏳ <b>Trial episode</b>\n\n"
            f"This video will be removed in <b>{format_trial_ttl_label(ttl)}</b>.\n"
            "Get VIP or unlock the episode to watch again anytime.",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _delete_trial_message_after(
    bot: Bot,
    user_id: int,
    episode_id: str,
    message_id: int,
    delay_seconds: int,
) -> None:
    await asyncio.sleep(max(0, delay_seconds))
    try:
        await bot.delete_message(chat_id=user_id, message_id=message_id)
        logger.info("Trial video removed for user %s episode %s", user_id, episode_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception:
        logger.exception(
            "Failed to delete trial message for user %s episode %s",
            user_id,
            episode_id,
        )
    finally:
        await repo.remove_trial_deletion(user_id, episode_id, message_id)


async def resume_pending_trial_deletions(bot: Bot) -> None:
    pending = await repo.get_pending_trial_deletions()
    now = datetime.now(TZ)
    for item in pending:
        delete_at = item.get("delete_at")
        if not delete_at:
            continue
        if delete_at.tzinfo is None:
            delete_at = delete_at.replace(tzinfo=TZ)
        delay = max(0, int((delete_at - now).total_seconds()))
        task = asyncio.create_task(
            _delete_trial_message_after(
                bot,
                item["telegram_id"],
                item["episode_id"],
                item["message_id"],
                delay,
            )
        )
        _track_task(task)
    if pending:
        logger.info("Resumed %s pending trial episode deletion(s)", len(pending))
