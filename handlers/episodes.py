import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import repository as repo
from keyboards.inline import episode_list_keyboard, limit_reached_keyboard
from services.messages import build_episode_list_text, format_date

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data.startswith("eps:"))
async def episode_page(callback: CallbackQuery):
    _, serial_slug, page_str = callback.data.split(":", 2)
    page = int(page_str)

    serial = await repo.get_serial_by_slug(serial_slug)
    if not serial:
        await callback.answer("Serial not found.", show_alert=True)
        return

    text, _ = await build_episode_list_text(serial, page)
    keyboard = await episode_list_keyboard(serial_slug, page)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("watch:"))
async def watch_episode(callback: CallbackQuery, db_user: dict):
    episode_id = callback.data.split(":", 1)[1]
    episode = await repo.get_episode(episode_id)
    if not episode:
        await callback.answer("Episode not found.", show_alert=True)
        return

    allowed, reason = await repo.can_watch_episode(db_user, episode_id)
    if not allowed:
        if reason == "daily_limit":
            await callback.message.answer(
                "⏳ <b>Daily limit reached</b>\n\n"
                "Free users can watch 3 episodes per day.\n"
                "Unlock this episode for ₹10 or get VIP for unlimited access.",
                reply_markup=limit_reached_keyboard(episode_id),
                parse_mode="HTML",
            )
            await callback.answer()
            return
        await callback.answer(reason, show_alert=True)
        return

    try:
        await callback.bot.send_video(
            chat_id=callback.from_user.id,
            video=episode["file_id"],
            caption=(
                f"📺 <b>{episode.get('serial_name', '')}</b>\n"
                f"📅 {format_date(episode['date'])}"
            ),
            protect_content=True,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to send episode %s", episode_id)
        await callback.answer("Failed to deliver video. Contact support.", show_alert=True)
        return

    counts_toward_limit = (
        db_user.get("plan") != "vip"
        and episode_id not in db_user.get("unlocked_episodes", [])
    )
    if counts_toward_limit:
        await repo.record_watch(callback.from_user.id, episode_id)
        db_user["daily_watches"] = db_user.get("daily_watches", 0) + 1

    await callback.answer("Episode sent to your chat ✅")
