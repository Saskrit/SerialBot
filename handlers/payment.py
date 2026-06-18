from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS, EPISODE_UNLOCK_PRICE, PAYMENT_NAME, UPI_ID, VIP_MONTHLY_PRICE
from database import repository as repo
from keyboards.inline import payment_instructions_keyboard
from states import PaymentStates

router = Router()


def payment_instructions(amount: int, payment_type: str) -> str:
    label = "Episode Unlock" if payment_type == "unlock" else "VIP Monthly"
    return (
        f"💳 <b>{label} — ₹{amount}</b>\n\n"
        f"Pay via UPI to:\n"
        f"<code>{UPI_ID}</code>\n"
        f"Name: <b>{PAYMENT_NAME}</b>\n\n"
        "After payment, tap the button below and send your "
        "transaction screenshot."
    )


@router.callback_query(F.data.startswith("pay:unlock:"))
async def pay_unlock(callback: CallbackQuery, state: FSMContext):
    episode_id = callback.data.split(":", 2)[2]
    episode = await repo.get_episode(episode_id)
    if not episode:
        await callback.answer("Episode not found.", show_alert=True)
        return

    payment_id = await repo.create_payment(
        callback.from_user.id, "unlock", EPISODE_UNLOCK_PRICE, episode_id
    )
    await state.set_state(PaymentStates.waiting_screenshot)
    await state.update_data(payment_id=payment_id)

    await callback.message.answer(
        payment_instructions(EPISODE_UNLOCK_PRICE, "unlock"),
        reply_markup=payment_instructions_keyboard(payment_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "pay:vip")
async def pay_vip(callback: CallbackQuery, state: FSMContext):
    payment_id = await repo.create_payment(
        callback.from_user.id, "vip", VIP_MONTHLY_PRICE
    )
    await state.set_state(PaymentStates.waiting_screenshot)
    await state.update_data(payment_id=payment_id)

    await callback.message.answer(
        payment_instructions(VIP_MONTHLY_PRICE, "vip"),
        reply_markup=payment_instructions_keyboard(payment_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay:screenshot:"))
async def pay_screenshot_prompt(callback: CallbackQuery, state: FSMContext):
    payment_id = callback.data.split(":", 2)[2]
    await state.set_state(PaymentStates.waiting_screenshot)
    await state.update_data(payment_id=payment_id)
    await callback.message.answer("📸 Send your payment screenshot as a photo.")
    await callback.answer()


@router.callback_query(F.data == "pay:cancel")
async def pay_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Payment cancelled.")
    await callback.answer()


@router.message(PaymentStates.waiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get("payment_id")
    if not payment_id:
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    attached = await repo.attach_payment_screenshot(payment_id, file_id)
    if not attached:
        await message.answer("Payment not found or already submitted.")
        await state.clear()
        return

    payment = await repo.get_payment(payment_id)
    user = message.from_user
    admin_text = (
        f"💳 <b>New Payment</b>\n"
        f"ID: <code>{payment_id}</code>\n"
        f"User: {user.first_name} (@{user.username or '—'}) "
        f"<code>{user.id}</code>\n"
        f"Type: <b>{payment['type']}</b> · ₹{payment['amount']}"
    )

    from keyboards.inline import admin_payment_keyboard

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_photo(
                admin_id,
                photo=file_id,
                caption=admin_text,
                reply_markup=admin_payment_keyboard(payment_id),
                parse_mode="HTML",
            )
        except Exception:
            pass

    await message.answer(
        "✅ Screenshot received!\n"
        "An admin will review your payment shortly."
    )
    await state.clear()


@router.message(PaymentStates.waiting_screenshot)
async def screenshot_expected(message: Message):
    await message.answer("Please send a photo screenshot of your payment.")
