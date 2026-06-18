from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database import repository as repo
from keyboards.inline import support_categories_keyboard
from states import SupportStates

router = Router()

CATEGORY_LABELS = {
    "payment": "Payment Issue",
    "missing": "Missing Episode",
    "vip": "VIP Problem",
    "technical": "Technical Issue",
    "other": "Other",
}


@router.message(F.text == "💬 Support")
async def support_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💬 <b>Support</b>\n\nSelect a category:",
        reply_markup=support_categories_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("support:cat:"))
async def support_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 2)[2]
    await state.set_state(SupportStates.waiting_message)
    await state.update_data(category=category)
    label = CATEGORY_LABELS.get(category, category)
    await callback.message.answer(
        f"📝 <b>{label}</b>\n\nDescribe your issue in detail:"
    )
    await callback.answer()


@router.message(SupportStates.waiting_message)
async def support_message(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("category", "other")
    label = CATEGORY_LABELS.get(category, category)

    ticket_id = await repo.create_support_ticket(
        message.from_user.id, category, message.text
    )

    admin_text = (
        f"💬 <b>Support — {label}</b>\n"
        f"Ticket: <code>{ticket_id}</code>\n"
        f"User: {message.from_user.first_name} "
        f"<code>{message.from_user.id}</code>\n\n"
        f"{message.text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                admin_text + f"\n\nReply: /reply {ticket_id}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await message.answer(
        "✅ Support request sent.\n"
        "An admin will respond soon."
    )
    await state.clear()
