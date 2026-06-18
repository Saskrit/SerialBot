import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import repository as repo
from keyboards.inline import limit_reached_keyboard
from services.episode_delivery import deliver_episode_to_user
from services.serial_episodes import (
    open_serial_episodes,
    parse_yyyymm,
    show_serial_episodes_for_month,
    show_serial_month_picker,
)
from services.settings import format_free_limit_label, get_free_daily_limit, is_free_unlimited

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data.startswith("epsmonth:"))
async def episode_month_picker(callback: CallbackQuery):
    serial_slug = callback.data.split(":", 1)[1]
    serial = await repo.get_serial_by_slug(serial_slug)
    if not serial:
        await callback.answer("Serial not found.", show_alert=True)
        return

    await show_serial_month_picker(
        callback, serial, show_catalog_back=True
    )


@router.callback_query(F.data.startswith("epsm:"))
async def episode_month_page(callback: CallbackQuery, db_user: dict):
    _, serial_slug, yyyymm, page_str = callback.data.split(":", 3)
    parsed = parse_yyyymm(yyyymm)
    if not parsed:
        await callback.answer("Invalid month.", show_alert=True)
        return

    year, month = parsed
    serial = await repo.get_serial_by_slug(serial_slug)
    if not serial:
        await callback.answer("Serial not found.", show_alert=True)
        return

    months = await repo.get_episode_months(serial_slug)
    show_month_back = len(months) > 1
    await show_serial_episodes_for_month(
        callback,
        serial,
        db_user,
        year,
        month,
        int(page_str),
        show_catalog_back=True,
        show_month_back=show_month_back,
    )


async def _send_daily_limit_message(bot, user_id: int, episode_id: str) -> None:
    limit = await get_free_daily_limit()
    limit_line = (
        "Free users currently have unlimited daily episodes."
        if is_free_unlimited(limit)
        else f"Free users can watch {format_free_limit_label(limit)}."
    )
    await bot.send_message(
        chat_id=user_id,
        text=(
            "⏳ <b>Daily limit reached</b>\n\n"
            f"{limit_line}\n"
            "Unlock this episode for ₹10 or get VIP for unlimited access."
        ),
        reply_markup=limit_reached_keyboard(episode_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("locked:"))
async def locked_episode(callback: CallbackQuery, db_user: dict):
    episode_id = callback.data.split(":", 1)[1]
    allowed, reason = await repo.can_watch_episode(db_user, episode_id)
    if allowed:
        episode = await repo.get_episode(episode_id)
        if episode:
            await callback.answer("Sending episode to your private chat…")
            ok, error = await deliver_episode_to_user(callback.bot, callback.from_user.id, episode)
            if not ok:
                await callback.bot.send_message(chat_id=callback.from_user.id, text=f"❌ {error}")
            return

    await _send_daily_limit_message(callback.bot, callback.from_user.id, episode_id)
    await callback.answer("Daily limit reached — check your private chat.")


@router.callback_query(F.data.startswith("watch:"))
async def watch_episode(callback: CallbackQuery, db_user: dict):
    user_id = callback.from_user.id
    episode_id = callback.data.split(":", 1)[1]
    episode = await repo.get_episode(episode_id)
    if not episode:
        await callback.answer("Episode not found.", show_alert=True)
        return

    allowed, reason = await repo.can_watch_episode(db_user, episode_id)
    if not allowed:
        if reason == "daily_limit":
            await _send_daily_limit_message(callback.bot, user_id, episode_id)
            await callback.answer("Check your private chat with the bot.")
            return
        await callback.answer(reason, show_alert=True)
        return

    await callback.answer("Sending episode to your private chat…")

    ok, error = await deliver_episode_to_user(callback.bot, user_id, episode)
    if not ok:
        await callback.bot.send_message(chat_id=user_id, text=f"❌ {error}")
        return

    counts_toward_limit = (
        db_user.get("plan") != "vip"
        and episode_id not in db_user.get("unlocked_episodes", [])
    )
    if counts_toward_limit:
        await repo.record_watch(user_id, episode_id)
        db_user["daily_watches"] = db_user.get("daily_watches", 0) + 1
