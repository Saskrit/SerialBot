from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from config import ADMIN_IDS
from keyboards.inline import main_menu_keyboard
from services.messages import build_user_info_text

router = Router()


async def _remove_inline_keyboard(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass


@router.callback_query(F.data == "ui:close")
async def close_panel(callback: CallbackQuery):
    await _remove_inline_keyboard(callback)
    await callback.answer("Closed ✓")


@router.callback_query(F.data == "ui:home")
async def home_panel(callback: CallbackQuery, db_user: dict):
    await _remove_inline_keyboard(callback)
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.answer(
        await build_user_info_text(db_user, is_admin=is_admin),
        reply_markup=main_menu_keyboard(db_user),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("close"))
@router.message(F.text == "❌ Close Menu")
async def close_menu(message: Message):
    await message.answer(
        "✅ Menu closed.\n\nSend <b>Hi</b> or /start to open it again.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
