import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import repository as repo
from keyboards.inline import episode_list_keyboard, limit_reached_keyboard
from services.episode_delivery import deliver_episode_to_user
from services.messages import build_episode_list_text

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
    user_id = callback.from_user.id
    episode_id = callback.data.split(":", 1)[1]
    episode = await repo.get_episode(episode_id)
    if not episode:
        await callback.answer("Episode not found.", show_alert=True)
        return

    allowed, reason = await repo.can_watch_episode(db_user, episode_id)
    if not allowed:
        if reason == "daily_limit":
            await callback.bot.send_message(
                chat_id=user_id,
                text=(
                    "⏳ <b>Daily limit reached</b>\n\n"
                    "Free users can watch 3 episodes per day.\n"
                    "Unlock this episode for ₹10 or get VIP for unlimited access."
                ),
                reply_markup=limit_reached_keyboard(episode_id),
                parse_mode="HTML",
            )
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
