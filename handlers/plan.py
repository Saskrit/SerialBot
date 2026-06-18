from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from database.datetime_utils import ensure_aware
from keyboards.inline import plan_keyboard, vip_keyboard
from services.messages import _vip_time_remaining, build_plan_text, format_date

router = Router()


@router.message(F.text == "📋 My Plan")
async def my_plan_message(message: Message, db_user: dict):
    await message.answer(
        await build_plan_text(db_user),
        reply_markup=plan_keyboard(db_user),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "plan")
async def my_plan_callback(callback: CallbackQuery, db_user: dict):
    await callback.message.answer(
        await build_plan_text(db_user),
        reply_markup=plan_keyboard(db_user),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(F.text.in_({"⭐ Get VIP", "✅ VIP Member"}))
async def get_vip(message: Message, db_user: dict):
    if db_user.get("plan") == "vip":
        expires = ensure_aware(db_user.get("vip_expires"))
        remaining = _vip_time_remaining(db_user)
        text = (
            "⭐ <b>You are a VIP Member</b>\n\n"
            "✅ Unlimited episodes daily\n"
            "✅ Full archive access\n"
            "✅ Episode request priority\n"
            "✅ Priority support"
        )
        if expires:
            text += f"\n\nValid until: <b>{format_date(expires)}</b>"
        if remaining:
            text += f"\nTime remaining: <b>{remaining}</b>"
        await message.answer(
            text,
            reply_markup=vip_keyboard(db_user),
            parse_mode="HTML",
        )
        return

    await message.answer(
        "⭐ <b>VIP Monthly — ₹99</b>\n\n"
        "• Unlimited episodes daily\n"
        "• Full archive access\n"
        "• Episode request priority\n"
        "• Priority support\n\n"
        "Tap below to subscribe:",
        reply_markup=vip_keyboard(db_user),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "vip:status")
async def vip_status_callback(callback: CallbackQuery, db_user: dict):
    if db_user.get("plan") != "vip":
        await callback.answer("VIP subscription required.", show_alert=True)
        return

    expires = ensure_aware(db_user.get("vip_expires"))
    remaining = _vip_time_remaining(db_user)
    text = "⭐ <b>You are a VIP Member</b>\n\nUnlimited episodes · full archive access"
    if expires:
        text += f"\n\nValid until: <b>{format_date(expires)}</b>"
    if remaining:
        text += f"\nTime remaining: <b>{remaining}</b>"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
