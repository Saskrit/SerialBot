from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import ADMIN_IDS
from database import repository as repo
from states import EpisodeRequestStates

router = Router()


@router.message(F.text == "📺 Request Episode")
async def request_start(message: Message, state: FSMContext):
    await state.set_state(EpisodeRequestStates.waiting_serial)
    await message.answer(
        "📺 <b>Episode Request</b>\n\n"
        "Which serial do you need an episode for?\n"
        "Type the serial name:",
        parse_mode="HTML",
    )


@router.message(EpisodeRequestStates.waiting_serial)
async def request_serial(message: Message, state: FSMContext):
    await state.update_data(serial_name=message.text.strip())
    await state.set_state(EpisodeRequestStates.waiting_date)
    await message.answer(
        "📅 What date is the episode from?\n"
        "Example: <code>17 June 2026</code>",
        parse_mode="HTML",
    )


@router.message(EpisodeRequestStates.waiting_date)
async def request_date(message: Message, state: FSMContext):
    data = await state.get_data()
    serial_name = data.get("serial_name", "")
    episode_date = message.text.strip()

    request_id = await repo.create_episode_request(
        message.from_user.id, serial_name, episode_date
    )

    admin_text = (
        f"📺 <b>Episode Request</b>\n"
        f"ID: <code>{request_id}</code>\n"
        f"User: {message.from_user.first_name} "
        f"<code>{message.from_user.id}</code>\n"
        f"Serial: <b>{serial_name}</b>\n"
        f"Date: <b>{episode_date}</b>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception:
            pass

    await message.answer(
        "✅ Request submitted!\n"
        "We'll notify you if the episode becomes available."
    )
    await state.clear()
