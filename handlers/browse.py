from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database import repository as repo
from keyboards.inline import serial_catalog_keyboard
from services.messages import build_catalog_text
from services.serial_episodes import open_serial_episodes

router = Router()


async def _send_catalog(message: Message, page: int) -> None:
    text = await build_catalog_text(page)
    keyboard = await serial_catalog_keyboard(page)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def _edit_catalog(callback: CallbackQuery, page: int) -> None:
    text = await build_catalog_text(page)
    keyboard = await serial_catalog_keyboard(page)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("browse"))
@router.message(F.text == "📚 Browse Serials")
async def browse_serials(message: Message):
    await _send_catalog(message, 0)


@router.callback_query(F.data.startswith("cat:"))
async def browse_catalog_page(callback: CallbackQuery):
    page = int(callback.data.split(":", 1)[1])
    await _edit_catalog(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("pick:"))
async def pick_serial(callback: CallbackQuery, db_user: dict):
    serial_slug = callback.data.split(":", 1)[1]
    serial = await repo.get_serial_by_slug(serial_slug)
    if not serial:
        await callback.answer("Serial not found.", show_alert=True)
        return

    await open_serial_episodes(
        callback, serial, db_user, show_catalog_back=True
    )
