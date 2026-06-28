"""Scheduled and manual promo messages for episode alert membership."""

import asyncio
import logging

from aiogram import Bot

from config import ADMIN_IDS, NOTIFY_PROMO_INTERVAL_HOURS
from database import repository as repo
from keyboards.inline import notify_promo_keyboard
from services.notify_membership import build_notify_promo_text

logger = logging.getLogger(__name__)

PROMO_DELAY_SEC = 0.05


async def send_notify_membership_promo(bot: Bot, *, user_ids: list[int] | None = None) -> tuple[int, int]:
    """Send alert-membership promo. Default: users without active alert subscription."""
    if user_ids is None:
        user_ids = await repo.get_users_without_notify_membership()

    text = build_notify_promo_text()
    keyboard = notify_promo_keyboard()
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
            await repo.mark_notify_promo_sent(user_id)
        except Exception:
            pass
        await asyncio.sleep(PROMO_DELAY_SEC)

    total = len(user_ids)
    logger.info("Notify membership promo sent to %s/%s users", sent, total)
    return sent, total


async def notify_promo_scheduler(create_bot, shutdown: asyncio.Event) -> None:
    """Every NOTIFY_PROMO_INTERVAL_HOURS, remind non-subscribers about alert plans."""
    interval = max(1, NOTIFY_PROMO_INTERVAL_HOURS) * 3600
    logger.info("Notify promo scheduler started (every %s hour(s))", NOTIFY_PROMO_INTERVAL_HOURS)

    while not shutdown.is_set():
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass

        if shutdown.is_set():
            break

        bot = create_bot()
        try:
            await send_notify_membership_promo(bot)
        except Exception:
            logger.exception("Notify promo scheduler run failed")
        finally:
            try:
                await bot.session.close()
            except Exception:
                pass
