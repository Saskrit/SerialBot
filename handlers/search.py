from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from database import repository as repo
from keyboards.inline import date_episodes_keyboard, episode_list_keyboard
from services.date_query import (
    UserDateQuery,
    decode_date_query,
    encode_date_query,
    parse_user_date_query,
)
from services.greetings import is_greeting, is_status_query
from services.messages import build_date_episodes_text, build_episode_list_text
from services.serial_matcher import match_serial

router = Router()

MENU_BUTTONS = {
    "🔍 Search Serial",
    "📚 Browse Serials",
    "📋 My Plan",
    "⭐ Get VIP",
    "✅ VIP Member",
    "📺 Request Episode",
    "💬 Support",
}


async def _send_date_episodes(
    target: Message | CallbackQuery,
    db_user: dict,
    query: UserDateQuery,
    page: int = 0,
) -> None:
    episodes = await repo.get_episodes_by_date_query(query.day, query.month, query.year)
    text, _ = build_date_episodes_text(episodes, query, page, user=db_user)
    date_key = encode_date_query(query)
    keyboard = date_episodes_keyboard(episodes, date_key, page, user=db_user)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(
    F.text
    & ~F.text.in_(MENU_BUTTONS)
    & ~F.text.startswith("/")
    & ~F.text.func(is_greeting)
    & ~F.text.func(is_status_query),
    StateFilter(None),
)
async def serial_search(message: Message, db_user: dict):
    date_query = parse_user_date_query(message.text)
    if date_query:
        await _send_date_episodes(message, db_user, date_query)
        return

    serial = await match_serial(message.text)
    if not serial:
        serials = await repo.list_serials()
        sample = ", ".join(s["name"] for s in serials[:6])
        await message.answer(
            "❌ Serial not found.\n\n"
            f"Try a name like: {sample}…\n\n"
            "Or search by date:\n"
            "• <code>17 June</code>\n"
            "• <code>17-06-2026</code>",
            parse_mode="HTML",
        )
        return

    text, _ = await build_episode_list_text(serial, 0, db_user)
    keyboard = await episode_list_keyboard(
        serial["slug"], 0, user=db_user, show_catalog_back=False
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("datefind:"))
async def date_find_page(callback: CallbackQuery, db_user: dict):
    _, date_key, page_str = callback.data.split(":", 2)
    try:
        query = decode_date_query(date_key)
    except ValueError:
        await callback.answer("Invalid date.", show_alert=True)
        return
    await _send_date_episodes(callback, db_user, query, int(page_str))


@router.message(F.text == "🔍 Search Serial")
async def search_hint(message: Message):
    await message.answer(
        "🔍 <b>Search a serial or date</b>\n\n"
        "<b>By serial name</b> — abbreviations work too:\n"
        "• Anupamaa · Udne Ki Aasha · YRKKH\n"
        "• Jagadhatri · TMKOC · Naagin 7\n\n"
        "<b>By episode date</b>:\n"
        "• <code>17 June</code>\n"
        "• <code>17 June 2026</code>\n"
        "• <code>17-06-2026</code>",
        parse_mode="HTML",
    )
