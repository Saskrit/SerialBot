from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from keyboards.inline import plan_keyboard, vip_keyboard
from services.messages import build_plan_text

router = Router()


@router.message(F.text == "📋 My Plan")
async def my_plan_message(message: Message, db_user: dict):
    await message.answer(
        build_plan_text(db_user),
        reply_markup=plan_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "plan")
async def my_plan_callback(callback: CallbackQuery, db_user: dict):
    await callback.message.answer(
        build_plan_text(db_user),
        reply_markup=plan_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.text == "⭐ Get VIP")
async def get_vip(message: Message):
    await message.answer(
        "⭐ <b>VIP Monthly — ₹99</b>\n\n"
        "• Unlimited episodes daily\n"
        "• Full archive access\n"
        "• Episode request priority\n"
        "• Priority support\n\n"
        "Tap below to subscribe:",
        reply_markup=vip_keyboard(),
        parse_mode="HTML",
    )
