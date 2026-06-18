import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bson import ObjectId

from config import ADMIN_IDS, STORAGE_CHANNEL_ID
from database import repository as repo
from database.connection import get_db
from keyboards.inline import (
    admin_delete_episode_confirm_keyboard,
    admin_episodes_keyboard,
    admin_menu_keyboard,
    admin_user_keyboard,
    admin_users_keyboard,
)
from services.messages import format_date
from services.episode_upload import save_episode_from_addepisode, save_episode_from_message
from services.upload_parser import parse_episode_date
from states import AdminStates

logger = logging.getLogger(__name__)

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def _notify_admins(bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


def _is_storage_chat(message: Message) -> bool:
    return bool(STORAGE_CHANNEL_ID and message.chat.id == STORAGE_CHANNEL_ID)


async def process_storage_upload(message: Message, *, is_caption_edit: bool = False) -> None:
    if not _is_storage_chat(message):
        return

    ok, status = await save_episode_from_message(
        message,
        silent_empty_caption=not is_caption_edit,
        is_caption_edit=is_caption_edit,
        notify=True,
    )
    if not ok and status:
        preview = (message.caption or "")[:300] or "(no caption)"
        await _notify_admins(
            message.bot,
            f"❌ <b>Storage upload failed</b>\n\n"
            f"Caption: <code>{preview}</code>\n\n{status}",
        )


@router.message(Command("storageinfo"))
async def storage_info(message: Message):
    if not is_admin(message.from_user.id):
        return

    lines = [
        "📦 <b>Storage setup</b>",
        f"Configured ID: <code>{STORAGE_CHANNEL_ID or 'not set'}</code>",
    ]
    if message.chat.type in ("channel", "supergroup", "group"):
        lines.append(f"This chat ID: <code>{message.chat.id}</code>")

    lines.extend(
        [
            "",
            "<b>Caption format:</b>",
            "<code>Laughter Chef 3 | 17 June 2026</code>",
            "<code>laughter-chef-3 | 17-06-2026</code>",
            "",
            "In your <b>private storage channel</b>:",
            "1. Post video with caption, or edit caption later",
            "2. Reply to video with <code>/addepisode</code>",
            "",
            "Bot must be <b>admin</b> in the storage channel.",
        ]
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("episodes"))
async def list_episodes_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Usage:\n"
            "<code>/episodes laughter-chef-3</code>\n\n"
            "Delete:\n"
            "<code>/delepisode EPISODE_ID</code>\n"
            "<code>/delepisode laughter-chef-3 17-06-2026</code>",
            parse_mode="HTML",
        )
        return

    slug = args[1].strip().lower().replace(" ", "-")
    await _send_admin_episode_list(message, slug, 0)


async def _send_admin_episode_list(
    target: Message | CallbackQuery, serial_slug: str, page: int
) -> None:
    serial = await repo.get_serial_by_slug(serial_slug)
    if not serial:
        text = f"Serial '{serial_slug}' not found."
        if isinstance(target, CallbackQuery):
            await target.answer(text, show_alert=True)
        else:
            await target.answer(text)
        return

    episodes, total = await repo.get_episodes(serial_slug, page, 8)
    if total == 0:
        text = f"📺 <b>{serial['name']}</b>\n\nNo episodes in database."
        keyboard = admin_menu_keyboard()
    else:
        total_pages = max(1, (total + 8 - 1) // 8)
        page = max(0, min(page, total_pages - 1))
        episodes, total = await repo.get_episodes(serial_slug, page, 8)
        lines = [
            f"🗑 <b>Manage Episodes</b> — {serial['name']}",
            f"Page {page + 1}/{total_pages} · {total} total",
            "",
            "Tap an episode to delete it:",
        ]
        for ep in episodes:
            lines.append(f"• {format_date(ep['date'])} — <code>{ep['_id']}</code>")
        text = "\n".join(lines)
        keyboard = await admin_episodes_keyboard(serial_slug, page)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("delepisode"))
async def delete_episode_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer(
            "Usage:\n"
            "<code>/delepisode EPISODE_ID</code>\n"
            "<code>/delepisode laughter-chef-3 17-06-2026</code>",
            parse_mode="HTML",
        )
        return

    if ObjectId.is_valid(args[1]):
        episode = await repo.delete_episode(args[1])
        if not episode:
            await message.answer("Episode not found.")
            return
        await message.answer(
            f"🗑 Deleted <b>{episode.get('serial_name', '')}</b> — "
            f"{format_date(episode['date'])}",
            parse_mode="HTML",
        )
        return

    if len(args) < 3:
        await message.answer("Provide a date: /delepisode serial_slug 17-06-2026")
        return

    slug = args[1].lower().replace(" ", "-")
    episode_date = parse_episode_date(args[2])
    if not episode_date:
        await message.answer("Could not parse date.")
        return

    episode = await repo.delete_episode_by_serial_date(slug, episode_date)
    if not episode:
        await message.answer("Episode not found for that serial and date.")
        return
    await message.answer(
        f"🗑 Deleted <b>{episode.get('serial_name', '')}</b> — "
        f"{format_date(episode['date'])}",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:deleps")
async def admin_delete_episodes_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await state.set_state(AdminStates.delete_episode_serial)
    await callback.message.answer(
        "🗑 <b>Delete Episode</b>\n\n"
        "Send the serial slug or name:\n"
        "Example: <code>laughter-chef-3</code> or <code>Laughter Chef 3</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.delete_episode_serial)
async def admin_delete_episodes_serial(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    from services.serial_matcher import match_serial

    query = message.text.strip()
    slug = query.lower().replace(" ", "-")
    serial = await repo.get_serial_by_slug(slug)
    if not serial:
        serial = await match_serial(query)
    if not serial:
        await message.answer("Serial not found. Try again or send /admin to cancel.")
        return

    await state.clear()
    await _send_admin_episode_list(message, serial["slug"], 0)


@router.callback_query(F.data.startswith("admin:epslist:"))
async def admin_episodes_list_page(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    _, _, slug, page_str = callback.data.split(":", 3)
    await _send_admin_episode_list(callback, slug, int(page_str))


@router.callback_query(F.data.startswith("admin:delep:"))
async def admin_delete_episode_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    parts = callback.data.split(":")
    episode_id = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0

    episode = await repo.get_episode(episode_id)
    if not episode:
        await callback.answer("Episode not found.", show_alert=True)
        return

    slug = episode["serial_slug"]
    text = (
        f"🗑 <b>Delete this episode?</b>\n\n"
        f"Serial: <b>{episode.get('serial_name', '')}</b>\n"
        f"Date: {format_date(episode['date'])}\n"
        f"ID: <code>{episode_id}</code>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_delete_episode_confirm_keyboard(episode_id, slug, page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delepok:"))
async def admin_delete_episode_execute(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    episode_id = callback.data.split(":", 2)[2]
    episode = await repo.delete_episode(episode_id)
    if not episode:
        await callback.answer("Episode not found.", show_alert=True)
        return

    await callback.message.edit_text(
        f"🗑 Deleted <b>{episode.get('serial_name', '')}</b> — "
        f"{format_date(episode['date'])}",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("Episode deleted ✅")


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🛠 <b>Admin Panel</b>",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


USERS_PER_PAGE = 15


def _format_user_line(index: int, user: dict) -> str:
    name = user.get("first_name") or "Unknown"
    username = user.get("username")
    user_label = f"{name} (@{username})" if username else name
    plan = "VIP" if user.get("plan") == "vip" else "Free"
    status = "🚫" if user.get("banned") else "✅"
    usage = "∞" if user.get("plan") == "vip" else f"{user.get('daily_watches', 0)}/3 today"
    return (
        f"{index}. {status} <b>{user_label}</b>\n"
        f"   ID: <code>{user['telegram_id']}</code> · {plan} · {usage}"
    )


async def _send_users_page(target: Message | CallbackQuery, page: int) -> None:
    users, total = await repo.list_users(page, USERS_PER_PAGE)
    if total == 0:
        text = "👥 <b>All Users</b>\n\nNo users registered yet."
        keyboard = admin_users_keyboard(0, 1)
    else:
        total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
        page = max(0, min(page, total_pages - 1))
        users, _ = await repo.list_users(page, USERS_PER_PAGE)
        start = page * USERS_PER_PAGE + 1
        lines = [
            f"👥 <b>All Users</b> · Page {page + 1}/{total_pages}",
            f"Total: <b>{total}</b>\n",
        ]
        for i, user in enumerate(users, start=start):
            lines.append(_format_user_line(i, user))
        text = "\n".join(lines)
        keyboard = admin_users_keyboard(page, total_pages)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("users"))
async def admin_users_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    await _send_users_page(message, 0)


@router.callback_query(F.data == "admin:menu")
async def admin_menu_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await callback.message.edit_text(
        "🛠 <b>Admin Panel</b>",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:users:"))
async def admin_users_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    page = int(callback.data.split(":", 2)[2])
    await _send_users_page(callback, page)


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    stats = await repo.get_user_stats()
    episode_count = await get_db().episodes.count_documents({})
    pending = await get_db().payments.count_documents(
        {"status": "pending", "screenshot_file_id": {"$ne": None}}
    )

    text = (
        "📊 <b>Statistics</b>\n\n"
        f"Total users: <b>{stats['total']}</b>\n"
        f"VIP users: <b>{stats['vip']}</b>\n"
        f"Active today: <b>{stats['active_today']}</b>\n"
        f"Banned: <b>{stats['banned']}</b>\n"
        f"Episodes: <b>{episode_count}</b>\n"
        f"Pending payments: <b>{pending}</b>"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:payments")
async def admin_payments(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    payments = await repo.get_pending_payments(10)
    if not payments:
        await callback.message.answer("No pending payments.")
        await callback.answer()
        return

    from keyboards.inline import admin_payment_keyboard

    for payment in payments:
        pid = str(payment["_id"])
        text = (
            f"💳 Payment <code>{pid}</code>\n"
            f"User: <code>{payment['user_id']}</code>\n"
            f"Type: {payment['type']} · ₹{payment['amount']}"
        )
        if payment.get("screenshot_file_id"):
            await callback.bot.send_photo(
                callback.from_user.id,
                photo=payment["screenshot_file_id"],
                caption=text,
                reply_markup=admin_payment_keyboard(pid),
                parse_mode="HTML",
            )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:pay:ok:"))
async def approve_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    payment_id = callback.data.split(":", 3)[3]
    payment = await repo.review_payment(payment_id, True, callback.from_user.id)
    if not payment:
        await callback.answer("Payment not found or already reviewed.", show_alert=True)
        return

    user_id = payment["user_id"]
    if payment["type"] == "vip":
        expires = await repo.grant_vip(user_id)
        await callback.bot.send_message(
            user_id,
            f"⭐ <b>VIP activated!</b>\n"
            f"Valid until {format_date(expires)}.",
            parse_mode="HTML",
        )
    elif payment["type"] == "unlock" and payment.get("episode_id"):
        await repo.grant_episode_unlock(user_id, payment["episode_id"])
        await callback.bot.send_message(
            user_id,
            "🔓 <b>Episode unlocked!</b>\n"
            "You can now watch it without using your daily limit.",
            parse_mode="HTML",
        )

    await callback.message.edit_caption(
        callback.message.caption + "\n\n✅ Approved",
        parse_mode="HTML",
    )
    await callback.answer("Approved ✅")


@router.callback_query(F.data.startswith("admin:pay:no:"))
async def reject_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    payment_id = callback.data.split(":", 3)[3]
    payment = await repo.review_payment(payment_id, False, callback.from_user.id)
    if not payment:
        await callback.answer("Payment not found or already reviewed.", show_alert=True)
        return

    await callback.bot.send_message(
        payment["user_id"],
        "❌ Your payment was not approved.\n"
        "Contact support if you believe this is an error.",
    )
    await callback.message.edit_caption(
        (callback.message.caption or "") + "\n\n❌ Rejected",
        parse_mode="HTML",
    )
    await callback.answer("Rejected")


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast_message)
    await callback.message.answer("📢 Send the broadcast message:")
    await callback.answer()


@router.message(AdminStates.broadcast_message)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    user_ids = await repo.get_all_user_ids()
    sent = 0
    for uid in user_ids:
        try:
            await message.copy_to(uid)
            sent += 1
        except Exception:
            pass

    await message.answer(f"📢 Broadcast sent to {sent}/{len(user_ids)} users.")
    await state.clear()


@router.callback_query(F.data == "admin:user")
async def admin_user_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await state.set_state(AdminStates.lookup_user)
    await callback.message.answer("👤 Enter the user's Telegram ID:")
    await callback.answer()


@router.message(AdminStates.lookup_user)
async def admin_user_lookup(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if not message.text.strip().isdigit():
        await message.answer("Please enter a numeric Telegram ID.")
        return

    telegram_id = int(message.text.strip())
    user = await repo.get_user(telegram_id)
    if not user:
        await message.answer("User not found.")
        await state.clear()
        return

    text = (
        f"👤 <b>User {telegram_id}</b>\n"
        f"Plan: {user.get('plan')}\n"
        f"Daily watches: {user.get('daily_watches', 0)}\n"
        f"Banned: {user.get('banned', False)}\n"
        f"Unlocks: {len(user.get('unlocked_episodes', []))}"
    )
    await message.answer(
        text,
        reply_markup=admin_user_keyboard(telegram_id),
        parse_mode="HTML",
    )
    await state.clear()


async def _apply_vip_grant(bot, telegram_id: int, days: int = 30) -> datetime:
    await repo.get_or_create_user(telegram_id)
    expires = await repo.grant_vip(telegram_id, days)
    try:
        await bot.send_message(
            telegram_id,
            f"⭐ <b>VIP activated!</b>\nValid until {format_date(expires)}.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    return expires


@router.message(Command("makevip"))
async def makevip_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Usage:\n"
            "<code>/makevip USER_ID</code>\n"
            "<code>/makevip USER_ID 30</code> (days, optional)",
            parse_mode="HTML",
        )
        return

    telegram_id = int(parts[1])
    days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 30
    expires = await _apply_vip_grant(message.bot, telegram_id, days)
    await message.answer(
        f"✅ User <code>{telegram_id}</code> is now VIP until "
        f"<b>{format_date(expires)}</b> ({days} days).",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:grantvip")
async def admin_grant_vip_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await state.set_state(AdminStates.grant_vip_user)
    await callback.message.answer(
        "⭐ <b>Grant VIP</b>\n\n"
        "Send the user's Telegram ID:\n"
        "Example: <code>6831347256</code>\n\n"
        "Or use: <code>/makevip USER_ID</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.grant_vip_user)
async def admin_grant_vip_by_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text = message.text.strip()
    parts = text.split()
    if not parts[0].isdigit():
        await message.answer("Please send a numeric Telegram ID.")
        return

    telegram_id = int(parts[0])
    days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
    expires = await _apply_vip_grant(message.bot, telegram_id, days)
    await message.answer(
        f"✅ User <code>{telegram_id}</code> is now VIP until "
        f"<b>{format_date(expires)}</b> ({days} days).",
        parse_mode="HTML",
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin:vip:"))
async def admin_grant_vip(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 2)[2])
    expires = await _apply_vip_grant(callback.bot, telegram_id)
    await callback.answer(f"VIP granted until {format_date(expires)} ✅")


@router.callback_query(F.data.startswith("admin:ban:"))
async def admin_ban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 2)[2])
    await repo.set_banned(telegram_id, True)
    await callback.answer("User banned")


@router.callback_query(F.data.startswith("admin:unban:"))
async def admin_unban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 2)[2])
    await repo.set_banned(telegram_id, False)
    await callback.answer("User unbanned")


@router.callback_query(F.data.startswith("admin:del:"))
async def admin_delete(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 2)[2])
    await repo.delete_user(telegram_id)
    await callback.answer("User deleted")


@router.callback_query(F.data == "admin:requests")
async def admin_requests(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    cursor = (
        get_db()
        .episode_requests.find({"status": "open"})
        .sort("created_at", -1)
        .limit(10)
    )
    requests = await cursor.to_list(length=10)
    if not requests:
        await callback.message.answer("No open episode requests.")
    else:
        lines = ["📺 <b>Open Episode Requests</b>\n"]
        for req in requests:
            lines.append(
                f"• {req['serial_name']} — {req['episode_date']} "
                f"(user {req['user_id']})"
            )
        await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:support")
async def admin_support(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    cursor = (
        get_db()
        .support_tickets.find({"status": "open"})
        .sort("created_at", -1)
        .limit(10)
    )
    tickets = await cursor.to_list(length=10)
    if not tickets:
        await callback.message.answer("No open support tickets.")
    else:
        lines = ["💬 <b>Open Support Tickets</b>\n"]
        for ticket in tickets:
            lines.append(
                f"• [{ticket['category']}] user {ticket['user_id']}: "
                f"{ticket['message'][:80]}…"
            )
        await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.channel_post(F.video | F.document)
async def storage_channel_upload(message: Message):
    await process_storage_upload(message)


@router.edited_channel_post(F.video | F.document)
async def storage_channel_upload_edited(message: Message):
    await process_storage_upload(message, is_caption_edit=True)


if STORAGE_CHANNEL_ID:

    @router.message(F.chat.id == STORAGE_CHANNEL_ID, F.video | F.document)
    async def storage_group_upload(message: Message):
        await process_storage_upload(message)

    @router.edited_message(F.chat.id == STORAGE_CHANNEL_ID, F.video | F.document)
    async def storage_group_upload_edited(message: Message):
        await process_storage_upload(message, is_caption_edit=True)


def _can_run_addepisode(message: Message) -> bool:
    if message.from_user and is_admin(message.from_user.id):
        return True
    return _is_storage_chat(message)


async def _reply_addepisode_result(message: Message, status: str) -> None:
    """Send /addepisode result — channels cannot use message.answer()."""
    if message.chat.type == "channel":
        await _notify_admins(message.bot, status)
        return
    try:
        await message.answer(status, parse_mode="HTML")
    except Exception:
        await _notify_admins(message.bot, status)


async def _handle_addepisode(message: Message) -> None:
    if not _can_run_addepisode(message):
        return

    ok, status = await save_episode_from_addepisode(message)
    if status:
        await _reply_addepisode_result(message, status)


@router.channel_post(Command("addepisode"))
async def storage_channel_addepisode(message: Message):
    if _is_storage_chat(message):
        await _handle_addepisode(message)


@router.message(Command("addepisode"))
async def admin_add_episode_cmd(message: Message):
    await _handle_addepisode(message)
