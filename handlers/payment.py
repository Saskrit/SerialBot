import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS, EPISODE_UNLOCK_PRICE, PAYMENT_NAME, UPI_ID, VIP_MONTHLY_PRICE
from database import repository as repo
from keyboards.inline import admin_payment_keyboard, payment_instructions_keyboard
from services.private_dm import get_bot_username, payment_deep_link, send_private_message
from states import PaymentStates

logger = logging.getLogger(__name__)

router = Router()


def payment_instructions(amount: int, payment_type: str) -> str:
    label = "Episode Unlock" if payment_type == "unlock" else "VIP Monthly"
    return (
        f"💳 <b>{label} — ₹{amount}</b>\n\n"
        f"Pay via UPI to:\n"
        f"<code>{UPI_ID}</code>\n"
        f"Name: <b>{PAYMENT_NAME}</b>\n\n"
        "After payment, tap <b>Upload Screenshot in Bot</b> below.\n"
        "Your screenshot will be sent privately — never in a group."
    )


async def begin_payment_upload(message: Message, state: FSMContext, payment_id: str) -> None:
    payment = await repo.get_payment(payment_id)
    if not payment:
        await message.answer("❌ Payment not found or expired.")
        return
    if payment["user_id"] != message.from_user.id:
        await message.answer("❌ This payment link belongs to another user.")
        return
    if payment["status"] != "pending":
        await message.answer("ℹ️ This payment was already submitted or reviewed.")
        return

    await state.set_state(PaymentStates.waiting_screenshot)
    await state.update_data(payment_id=payment_id)

    label = "Episode Unlock" if payment["type"] == "unlock" else "VIP Monthly"
    await message.answer(
        f"📸 <b>Upload Payment Screenshot</b>\n\n"
        f"Type: <b>{label}</b> · ₹{payment['amount']}\n\n"
        "Send your UPI transaction screenshot as a <b>photo</b> in this private chat.",
        parse_mode="HTML",
    )


async def _deliver_payment_flow(
    callback: CallbackQuery,
    state: FSMContext,
    payment_id: str,
    amount: int,
    payment_type: str,
) -> None:
    user_id = callback.from_user.id
    bot: Bot = callback.bot
    username = await get_bot_username(bot)
    text = payment_instructions(amount, payment_type)
    keyboard = payment_instructions_keyboard(payment_id, username)
    in_private = callback.message.chat.type == ChatType.PRIVATE

    if in_private:
        await state.set_state(PaymentStates.waiting_screenshot)
        await state.update_data(payment_id=payment_id)

    sent = await send_private_message(
        bot,
        user_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    if in_private:
        if sent:
            await callback.answer("Check the message above to upload your screenshot.")
        else:
            await callback.answer("Could not send payment details.", show_alert=True)
        return

    if sent:
        await callback.answer(
            "💬 Payment details sent to your private chat with the bot.",
            show_alert=True,
        )
    else:
        link = payment_deep_link(username, payment_id)
        await callback.answer(
            f"Start the bot first, then pay: {link}",
            show_alert=True,
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
    await _deliver_payment_flow(
        callback, state, payment_id, EPISODE_UNLOCK_PRICE, "unlock"
    )


@router.callback_query(F.data == "pay:vip")
async def pay_vip(callback: CallbackQuery, state: FSMContext):
    payment_id = await repo.create_payment(
        callback.from_user.id, "vip", VIP_MONTHLY_PRICE
    )
    await _deliver_payment_flow(
        callback, state, payment_id, VIP_MONTHLY_PRICE, "vip"
    )


@router.callback_query(F.data.startswith("pay:cancel"))
async def pay_cancel(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2)
    payment_id = parts[2] if len(parts) > 2 else None

    if payment_id:
        payment = await repo.get_payment(payment_id)
        if payment and payment["user_id"] != callback.from_user.id:
            await callback.answer("Unauthorized.", show_alert=True)
            return

    await state.clear()
    await send_private_message(
        callback.bot,
        callback.from_user.id,
        "❌ Payment cancelled.",
    )
    await callback.answer("Payment cancelled.")


def _extract_screenshot_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and message.document.mime_type and message.document.mime_type.startswith(
        "image/"
    ):
        return message.document.file_id
    return None


@router.message(
    PaymentStates.waiting_screenshot,
    F.chat.type == ChatType.PRIVATE,
    F.photo | F.document,
)
async def receive_screenshot(message: Message, state: FSMContext):
    file_id = _extract_screenshot_file_id(message)
    if not file_id:
        await message.answer("Please send your payment screenshot as a photo.")
        return

    data = await state.get_data()
    payment_id = data.get("payment_id")
    if not payment_id:
        await state.clear()
        await message.answer("No active payment. Use Get VIP or unlock an episode first.")
        return

    payment = await repo.get_payment(payment_id)
    if not payment or payment["user_id"] != message.from_user.id:
        await state.clear()
        await message.answer("Invalid payment session.")
        return

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
        "✅ Screenshot received privately!\n"
        "An admin will review your payment shortly."
    )
    await state.clear()


@router.message(PaymentStates.waiting_screenshot, F.chat.type == ChatType.PRIVATE)
async def screenshot_expected(message: Message):
    await message.answer(
        "📸 Please send your payment screenshot as a <b>photo</b> in this chat.\n"
        "Do not upload it in a group — only here in private with the bot.",
        parse_mode="HTML",
    )
