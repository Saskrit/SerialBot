from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from keyboards.inline import main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: dict):
    name = db_user.get("first_name") or "there"
    await message.answer(
        f"Welcome to <b>Serial Hub</b>, {name}! 🎬\n\n"
        "Search any Hindi serial by name — try <b>Anupamaa</b>, "
        "<b>Udne Ki Aasha</b>, <b>YRKKH</b>, or <b>Jagadhatri</b>.\n\n"
        "Free plan: 3 episodes/day · VIP: unlimited · ₹99/month",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
