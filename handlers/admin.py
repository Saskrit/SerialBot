import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bson import ObjectId

from config import ADMIN_IDS, SERIALS_PER_PAGE, STORAGE_CHANNEL_ID
from database import repository as repo
from database.connection import get_db
from keyboards.inline import (
    admin_delete_episode_confirm_keyboard,
    admin_delete_serial_confirm_keyboard,
    admin_episode_stats_keyboard,
    admin_episodes_keyboard,
    admin_free_limit_keyboard,
    admin_menu_keyboard,
    admin_serials_delete_keyboard,
    admin_trial_ttl_keyboard,
    admin_user_keyboard,
    admin_users_keyboard,
)
from services.messages import format_date, format_datetime
from services.episode_upload import save_episode_from_addepisode, save_episode_from_message
from services.serial_utils import parse_add_serial_input
from services import admin_actions
from services.settings import (
    format_free_limit_label,
    format_trial_ttl_label,
    get_free_daily_limit,
    get_trial_episode_ttl_seconds,
    parse_trial_ttl_setting,
    set_free_daily_limit,
    set_trial_episode_ttl_seconds,
)
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
            "<b>New serial?</b> Use <code>/addserial Serial Name</code> first.",
            "",
            "In your <b>private storage channel</b>:",
            "1. Post video with caption, or edit caption later",
            "2. Reply to video with <code>/addepisode</code>",
            "",
            "Bot must be <b>admin</b> in the storage channel.",
        ]
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


def _add_serial_usage() -> str:
    return (
        "➕ <b>Add Serial</b>\n\n"
        "Usage:\n"
        "<code>/addserial Seher Hone Ko Hai</code>\n"
        "<code>/addserial Seher Hone Ko Hai | seher, shk</code>\n\n"
        "Aliases are optional (comma-separated after <code>|</code>).\n"
        "Then upload episodes with caption:\n"
        "<code>Seher Hone Ko Hai | 18 June 2026</code>"
    )


async def _add_serial_from_text(
    message: Message, raw: str, state: FSMContext | None = None
) -> None:
    name, aliases = parse_add_serial_input(raw)
    if not name:
        await message.answer("Please send a serial name.", parse_mode="HTML")
        return

    serial, error = await repo.create_serial(name, aliases)
    if error:
        await message.answer(f"❌ {error}", parse_mode="HTML")
        return

    if state:
        await state.clear()

    alias_line = ""
    if serial.get("aliases"):
        alias_line = f"\nAliases: <code>{', '.join(serial['aliases'])}</code>"

    await message.answer(
        "✅ <b>Serial created</b>\n\n"
        f"Name: <b>{serial['name']}</b>\n"
        f"Slug: <code>{serial['slug']}</code>{alias_line}\n\n"
        "Upload episodes in the storage channel with caption:\n"
        f"<code>{serial['name']} | 18 June 2026</code>",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("addserial"))
async def add_serial_cmd(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await state.set_state(AdminStates.add_serial_name)
        await message.answer(_add_serial_usage(), parse_mode="HTML")
        return

    await _add_serial_from_text(message, parts[1], state)


@router.callback_query(F.data == "admin:addserial")
async def admin_add_serial_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await state.set_state(AdminStates.add_serial_name)
    await callback.message.answer(_add_serial_usage(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.add_serial_name)
async def admin_add_serial_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await _add_serial_from_text(message, message.text.strip(), state)


async def _send_admin_serial_delete_list(
    target: Message | CallbackQuery, page: int
) -> None:
    serials, total = await repo.list_serials_admin(page, SERIALS_PER_PAGE)
    if total == 0:
        text = "🗑 <b>Delete Serial</b>\n\nNo active serials in catalog."
        keyboard = admin_menu_keyboard()
    else:
        total_pages = max(1, (total + SERIALS_PER_PAGE - 1) // SERIALS_PER_PAGE)
        page = max(0, min(page, total_pages - 1))
        text = (
            f"🗑 <b>Delete Serial</b>\n\n"
            f"Page {page + 1}/{total_pages} · {total} serial(s)\n\n"
            "Tap a serial to remove it from the bot.\n"
            "<i>All its episodes will also be deleted.</i>"
        )
        keyboard = await admin_serials_delete_keyboard(page)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("delserial"))
async def delserial_cmd(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await _send_admin_serial_delete_list(message, 0)
        return

    from services.serial_matcher import match_serial

    confirm = len(parts) >= 3 and parts[-1].lower() == "confirm"
    query = " ".join(parts[1:-1] if confirm else parts[1:])

    slug = query.lower().replace(" ", "-")
    serial = await repo.get_serial_by_slug(slug)
    if not serial or not serial.get("active", True):
        serial = await match_serial(query)
    if not serial or not serial.get("active", True):
        await message.answer("Serial not found.")
        return

    if confirm:
        deleted, ep_deleted = await repo.delete_serial(serial["slug"])
        if not deleted:
            await message.answer("Serial not found or already deleted.")
            return
        await message.answer(
            f"🗑 Deleted <b>{deleted['name']}</b> "
            f"and <b>{ep_deleted}</b> episode(s).",
            parse_mode="HTML",
        )
        await state.clear()
        return

    ep_count = await get_db().episodes.count_documents({"serial_slug": serial["slug"]})
    await message.answer(
        f"🗑 <b>Delete this serial?</b>\n\n"
        f"Serial: <b>{serial['name']}</b>\n"
        f"Slug: <code>{serial['slug']}</code>\n"
        f"Episodes: <b>{ep_count}</b>\n\n"
        f"Confirm: <code>/delserial {serial['slug']} confirm</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:delserial:"))
async def admin_delete_serial_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    page = int(callback.data.split(":", 2)[2])
    await _send_admin_serial_delete_list(callback, page)


@router.callback_query(F.data == "admin:delserial")
async def admin_delete_serial_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await state.clear()
    await _send_admin_serial_delete_list(callback, 0)


@router.callback_query(F.data.startswith("admin:delser:"))
async def admin_delete_serial_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    slug = callback.data.split(":", 2)[2]
    if slug.startswith("ok:"):
        return

    serial = await repo.get_serial_by_slug(slug)
    if not serial or not serial.get("active", True):
        await callback.answer("Serial not found.", show_alert=True)
        return

    ep_count = await get_db().episodes.count_documents({"serial_slug": slug})
    text = (
        f"🗑 <b>Delete this serial?</b>\n\n"
        f"Serial: <b>{serial['name']}</b>\n"
        f"Slug: <code>{slug}</code>\n"
        f"Episodes to remove: <b>{ep_count}</b>\n\n"
        "This cannot be undone."
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_delete_serial_confirm_keyboard(slug),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delserok:"))
async def admin_delete_serial_execute(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    slug = callback.data.split(":", 2)[2]
    serial, ep_deleted = await repo.delete_serial(slug)
    if not serial:
        await callback.answer("Serial not found.", show_alert=True)
        return

    await callback.message.edit_text(
        f"🗑 Deleted <b>{serial['name']}</b> "
        f"and <b>{ep_deleted}</b> episode(s).",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("Serial deleted ✅")


@router.message(AdminStates.delete_serial_lookup)
async def admin_delete_serial_by_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    from services.serial_matcher import match_serial

    query = message.text.strip()
    slug = query.lower().replace(" ", "-")
    serial = await repo.get_serial_by_slug(slug)
    if not serial or not serial.get("active", True):
        serial = await match_serial(query)
    if not serial or not serial.get("active", True):
        await message.answer("Serial not found. Try again or send /admin to cancel.")
        return

    await state.clear()
    ep_count = await get_db().episodes.count_documents({"serial_slug": serial["slug"]})
    await message.answer(
        f"🗑 <b>Delete this serial?</b>\n\n"
        f"Serial: <b>{serial['name']}</b>\n"
        f"Episodes: <b>{ep_count}</b>",
        reply_markup=admin_delete_serial_confirm_keyboard(serial["slug"]),
        parse_mode="HTML",
    )


@router.message(Command("episodes"))
async def list_episodes_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Usage:\n"
            "<code>/episodes laughter-chef-3</code>\n\n"
            "Views:\n"
            "<code>/epstats laughter-chef-3</code>\n\n"
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
            views = ep.get("view_count", 0)
            lines.append(
                f"• {format_date(ep['date'])} — 👁 <b>{views}</b> — <code>{ep['_id']}</code>"
            )
        text = "\n".join(lines)
        keyboard = await admin_episodes_keyboard(serial_slug, page)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def _send_admin_episode_stats_list(
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
        page_views = sum(ep.get("view_count", 0) for ep in episodes)
        lines = [
            f"📈 <b>Episode Views</b> — {serial['name']}",
            f"Page {page + 1}/{total_pages} · {total} episode(s)",
            f"Views on this page: <b>{page_views}</b>",
            "",
            "Tap an episode for watcher details:",
        ]
        for ep in episodes:
            views = ep.get("view_count", 0)
            lines.append(f"• {format_date(ep['date'])} — 👁 <b>{views}</b> views")
        text = "\n".join(lines)
        keyboard = await admin_episode_stats_keyboard(serial_slug, page)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("epstats"))
async def episode_stats_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Usage: <code>/epstats laughter-chef-3</code>",
            parse_mode="HTML",
        )
        return

    slug = args[1].strip().lower().replace(" ", "-")
    await _send_admin_episode_stats_list(message, slug, 0)


@router.callback_query(F.data == "admin:epstats")
async def admin_episode_stats_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    await state.set_state(AdminStates.epstats_serial)
    await callback.message.answer(
        "📈 <b>Episode Views</b>\n\n"
        "Send the serial slug or name:\n"
        "Example: <code>laughter-chef-3</code> or <code>Laughter Chef 3</code>\n\n"
        "Or use: <code>/epstats laughter-chef-3</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.epstats_serial)
async def admin_episode_stats_serial(message: Message, state: FSMContext):
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
    await _send_admin_episode_stats_list(message, serial["slug"], 0)


@router.callback_query(F.data.startswith("admin:epstatslist:"))
async def admin_episode_stats_page(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return
    _, _, slug, page_str = callback.data.split(":", 3)
    await _send_admin_episode_stats_list(callback, slug, int(page_str))


@router.callback_query(F.data.startswith("admin:epstat:"))
async def admin_episode_stats_detail(callback: CallbackQuery):
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

    watchers = await repo.get_episode_watchers(episode_id)
    views = episode.get("view_count", 0)
    lines = [
        "📈 <b>Episode Stats</b>",
        "",
        f"Serial: <b>{episode.get('serial_name', '')}</b>",
        f"Date: {format_date(episode['date'])}",
        f"Total views: <b>{views}</b>",
        f"Unique watchers: <b>{len(watchers)}</b>",
        f"ID: <code>{episode_id}</code>",
    ]

    if watchers:
        lines.extend(["", "<b>Recent watchers</b>"])
        for index, watcher in enumerate(watchers[:15], start=1):
            name = watcher.get("first_name") or "Unknown"
            username = watcher.get("username")
            user_label = f"{name} (@{username})" if username else name
            count = watcher.get("watch_count", 1)
            watched_at = watcher.get("watched_at")
            when = format_datetime(watched_at) if watched_at else "—"
            repeat = f" · {count}x" if count > 1 else ""
            lines.append(
                f"{index}. {user_label} — <code>{watcher['telegram_id']}</code>{repeat}\n"
                f"   Last: {when}"
            )
        if len(watchers) > 15:
            lines.append(f"\n… and {len(watchers) - 15} more")
    else:
        lines.extend(["", "No watchers recorded yet."])

    slug = episode["serial_slug"]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀ Back to list",
                    callback_data=f"admin:epstatslist:{slug}:{page}",
                )
            ],
            [InlineKeyboardButton(text="🛠 Admin Menu", callback_data="admin:menu")],
        ]
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


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
        "🛠 <b>Admin Panel</b>\n\n"
        "Web dashboard: open <code>/admin</code> on your Railway app URL.",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


USERS_PER_PAGE = 15


def _format_user_line(index: int, user: dict, *, daily_limit: int) -> str:
    name = user.get("first_name") or user.get("username") or "Unknown"
    username = user.get("username")
    user_label = f"{name} (@{username})" if username else name
    plan = "VIP" if user.get("plan") == "vip" else "Free"
    status = "🚫" if user.get("banned") else "✅"
    if user.get("plan") == "vip":
        usage = "∞"
    elif daily_limit <= 0:
        usage = f"{user.get('daily_watches', 0)} today · ∞"
    else:
        usage = f"{user.get('daily_watches', 0)}/{daily_limit} today"
    return (
        f"{index}. {status} <b>{user_label}</b>\n"
        f"   ID: <code>{user['telegram_id']}</code> · {plan} · {usage}"
    )


async def _send_users_page(target: Message | CallbackQuery, page: int) -> None:
    daily_limit = await get_free_daily_limit()
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
            lines.append(_format_user_line(i, user, daily_limit=daily_limit))
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
    total_views = await repo.get_total_episode_views()
    pending = await get_db().payments.count_documents(
        {"status": "pending", "screenshot_file_id": {"$ne": None}}
    )
    free_limit = await get_free_daily_limit()
    trial_ttl = await get_trial_episode_ttl_seconds()

    text = (
        "📊 <b>Statistics</b>\n\n"
        f"Total users: <b>{stats['total']}</b>\n"
        f"VIP users: <b>{stats['vip']}</b>\n"
        f"Active today: <b>{stats['active_today']}</b>\n"
        f"Banned: <b>{stats['banned']}</b>\n"
        f"Episodes: <b>{episode_count}</b>\n"
        f"Total episode views: <b>{total_views}</b>\n"
        f"Pending payments: <b>{pending}</b>\n"
        f"Free tier limit: <b>{format_free_limit_label(free_limit)}</b>\n"
        f"Trial episode timer: <b>{format_trial_ttl_label(trial_ttl)}</b>"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


def _free_limit_menu_text(limit: int) -> str:
    return (
        "⚙️ <b>Free Tier Daily Limit</b>\n\n"
        f"Current: <b>{format_free_limit_label(limit)}</b>\n\n"
        "Tap a value below, or use:\n"
        "<code>/setfreelimit 0</code> — free for all\n"
        "<code>/setfreelimit 5</code> — 5 episodes/day"
    )


@router.callback_query(F.data == "admin:freelimit")
async def admin_free_limit_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    limit = await get_free_daily_limit()
    await callback.message.answer(
        _free_limit_menu_text(limit),
        reply_markup=admin_free_limit_keyboard(limit),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:freelimit:"))
async def admin_free_limit_set(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    value = int(callback.data.rsplit(":", 1)[1])
    await set_free_daily_limit(value)
    limit = await get_free_daily_limit()
    await callback.message.edit_text(
        _free_limit_menu_text(limit) + "\n\n✅ Saved.",
        reply_markup=admin_free_limit_keyboard(limit),
        parse_mode="HTML",
    )
    await callback.answer("Updated ✅")


@router.message(Command("freelimit"))
async def free_limit_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    limit = await get_free_daily_limit()
    await message.answer(
        _free_limit_menu_text(limit),
        reply_markup=admin_free_limit_keyboard(limit),
        parse_mode="HTML",
    )


@router.message(Command("setfreelimit"))
async def set_free_limit_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "Usage:\n"
            "<code>/setfreelimit 0</code> — free for all\n"
            "<code>/setfreelimit 3</code> — 3 episodes/day\n"
            "<code>/setfreelimit 6</code> — 6 episodes/day",
            parse_mode="HTML",
        )
        return

    value = int(parts[1].strip())
    await set_free_daily_limit(value)
    limit = await get_free_daily_limit()
    await message.answer(
        f"✅ Free tier limit set to <b>{format_free_limit_label(limit)}</b>.",
        parse_mode="HTML",
    )


def _trial_ttl_menu_text(seconds: int) -> str:
    return (
        "⏳ <b>Trial Episode Timer</b>\n\n"
        f"Current: <b>{format_trial_ttl_label(seconds)}</b>\n\n"
        "Free users get a trial watch. After the timer, the video is "
        "removed from their chat and they cannot watch that episode again "
        "unless they unlock it or get VIP.\n\n"
        "Tap a preset below, or use:\n"
        "<code>/settrial off</code>\n"
        "<code>/settrial 10s</code>\n"
        "<code>/settrial 1min</code>\n"
        "<code>/settrial 2hr</code>"
    )


@router.callback_query(F.data == "admin:trial")
async def admin_trial_ttl_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    seconds = await get_trial_episode_ttl_seconds()
    await callback.message.answer(
        _trial_ttl_menu_text(seconds),
        reply_markup=admin_trial_ttl_keyboard(seconds),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:trial:"))
async def admin_trial_ttl_set(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    seconds = int(callback.data.rsplit(":", 1)[1])
    await set_trial_episode_ttl_seconds(seconds)
    seconds = await get_trial_episode_ttl_seconds()
    await callback.message.edit_text(
        _trial_ttl_menu_text(seconds) + "\n\n✅ Saved.",
        reply_markup=admin_trial_ttl_keyboard(seconds),
        parse_mode="HTML",
    )
    await callback.answer("Updated ✅")


@router.message(Command("trial"))
async def trial_ttl_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    seconds = await get_trial_episode_ttl_seconds()
    await message.answer(
        _trial_ttl_menu_text(seconds),
        reply_markup=admin_trial_ttl_keyboard(seconds),
        parse_mode="HTML",
    )


@router.message(Command("settrial"))
async def set_trial_ttl_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage:\n"
            "<code>/settrial off</code>\n"
            "<code>/settrial 10s</code>\n"
            "<code>/settrial 1min</code>\n"
            "<code>/settrial 2hr</code>",
            parse_mode="HTML",
        )
        return

    seconds = parse_trial_ttl_setting(parts[1].strip())
    if seconds is None:
        await message.answer("Could not parse duration. Examples: 10s, 1min, 2hr, off")
        return

    await set_trial_episode_ttl_seconds(seconds)
    seconds = await get_trial_episode_ttl_seconds()
    await message.answer(
        f"✅ Trial timer set to <b>{format_trial_ttl_label(seconds)}</b>.",
        parse_mode="HTML",
    )


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
    ok, msg = await admin_actions.approve_payment(
        callback.bot, payment_id, callback.from_user.id
    )
    if not ok:
        await callback.answer(msg, show_alert=True)
        return

    await callback.message.edit_caption(
        (callback.message.caption or "") + "\n\n✅ Approved",
        parse_mode="HTML",
    )
    await callback.answer("Approved ✅")


@router.callback_query(F.data.startswith("admin:pay:no:"))
async def reject_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized.", show_alert=True)
        return

    payment_id = callback.data.split(":", 3)[3]
    ok, msg = await admin_actions.reject_payment(
        callback.bot, payment_id, callback.from_user.id
    )
    if not ok:
        await callback.answer(msg, show_alert=True)
        return

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
    return await admin_actions.grant_vip_with_notify(bot, telegram_id, days)


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
