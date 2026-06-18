import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS, STORAGE_CHANNEL_ID, TZ
from database import repository as repo
from database.connection import get_db
from keyboards.inline import admin_menu_keyboard, admin_user_keyboard, admin_users_keyboard
from services.messages import format_date
from states import AdminStates

logger = logging.getLogger(__name__)

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


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


@router.callback_query(F.data.startswith("admin:vip:"))
async def admin_grant_vip(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    telegram_id = int(callback.data.split(":", 2)[2])
    expires = await repo.grant_vip(telegram_id)
    await callback.bot.send_message(
        telegram_id,
        f"⭐ Admin granted VIP until {format_date(expires)}.",
        parse_mode="HTML",
    )
    await callback.answer("VIP granted ✅")


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


def parse_episode_date(text: str) -> datetime | None:
    patterns = [
        r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})",
        r"(\d{1,2})\s+(\w+)\s+(\d{4})",
    ]
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    text = text.strip()

    m = re.match(patterns[0], text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(year, month, day, tzinfo=TZ)
        except ValueError:
            return None

    m = re.match(patterns[1], text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = months.get(month_name)
        if month:
            try:
                return datetime(year, month, day, tzinfo=TZ)
            except ValueError:
                return None
    return None


@router.channel_post(F.video | F.document)
async def storage_channel_upload(message: Message):
    if not STORAGE_CHANNEL_ID or message.chat.id != STORAGE_CHANNEL_ID:
        return

    caption = message.caption or ""
    if not caption.strip():
        return

    parts = caption.strip().split("|")
    if len(parts) < 2:
        parts = caption.strip().split()
        if len(parts) < 2:
            return
        serial_query = parts[0]
        date_str = " ".join(parts[1:])
    else:
        serial_query = parts[0].strip()
        date_str = parts[1].strip()

    from services.serial_matcher import match_serial

    serial = await match_serial(serial_query)
    if not serial:
        logger.warning("Unknown serial in channel upload: %s", serial_query)
        return

    episode_date = parse_episode_date(date_str)
    if not episode_date:
        logger.warning("Could not parse date: %s", date_str)
        return

    file_id = message.video.file_id if message.video else message.document.file_id
    unique_id = (
        message.video.file_unique_id if message.video else message.document.file_unique_id
    )

    await repo.add_episode(
        serial_slug=serial["slug"],
        serial_name=serial["name"],
        episode_date=episode_date,
        file_id=file_id,
        file_unique_id=unique_id,
        message_id=message.message_id,
    )
    logger.info("Episode saved: %s — %s", serial["name"], date_str)


@router.message(Command("addepisode"))
async def admin_add_episode_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    if not message.reply_to_message or not (
        message.reply_to_message.video or message.reply_to_message.document
    ):
        await message.answer(
            "Reply to a video with:\n"
            "<code>/addepisode serial_slug 17-06-2026</code>",
            parse_mode="HTML",
        )
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Usage: /addepisode serial_slug 17-06-2026")
        return

    slug = args[1].lower()
    serial = await repo.get_serial_by_slug(slug)
    if not serial:
        await message.answer(f"Serial slug '{slug}' not found.")
        return

    episode_date = parse_episode_date(args[2])
    if not episode_date:
        await message.answer("Could not parse date.")
        return

    src = message.reply_to_message
    file_id = src.video.file_id if src.video else src.document.file_id
    unique_id = src.video.file_unique_id if src.video else src.document.file_unique_id

    ep_id = await repo.add_episode(
        serial_slug=serial["slug"],
        serial_name=serial["name"],
        episode_date=episode_date,
        file_id=file_id,
        file_unique_id=unique_id,
    )
    await message.answer(f"✅ Episode saved: {serial['name']} — {args[2]} ({ep_id})")
