from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from database import repository as repo
from services.greetings import is_greeting, is_status_query
from keyboards.inline import episode_list_keyboard
from services.messages import build_episode_list_text
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


@router.message(
    F.text
    & ~F.text.in_(MENU_BUTTONS)
    & ~F.text.startswith("/")
    & ~F.text.func(is_greeting)
    & ~F.text.func(is_status_query),
    StateFilter(None),
)
async def serial_search(message: Message, db_user: dict):
    serial = await match_serial(message.text)
    if not serial:
        serials = await repo.list_serials()
        sample = ", ".join(s["name"] for s in serials[:6])
        await message.answer(
            "❌ Serial not found.\n\n"
            f"Try a name like: {sample}…",
            parse_mode="HTML",
        )
        return

    text, _ = await build_episode_list_text(serial, 0, db_user)
    keyboard = await episode_list_keyboard(
        serial["slug"], 0, user=db_user, show_catalog_back=False
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(F.text == "🔍 Search Serial")
async def search_hint(message: Message):
    await message.answer(
        "🔍 <b>Search a serial</b>\n\n"
        "Just type the serial name — abbreviations work too:\n"
        "• Anupamaa · Udne Ki Aasha · YRKKH\n"
        "• Jagadhatri · TMKOC · Naagin 7",
        parse_mode="HTML",
    )
