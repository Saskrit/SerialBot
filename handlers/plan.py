from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from keyboards.inline import membership_catalog_keyboard, plan_keyboard, vip_keyboard
from services.messages import (
    _vip_time_remaining,
    build_membership_catalog_text,
    build_plan_text,
    format_date,
)
from services.payment_contact import payment_contact_label

router = Router()


@router.message(F.text.in_({"📋 My Plan", "📋 My Membership"}))
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


@router.callback_query(F.data == "membership:catalog")
async def membership_catalog_callback(callback: CallbackQuery, db_user: dict):
    await callback.message.answer(
        build_membership_catalog_text(),
        reply_markup=membership_catalog_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "upgrade:free_tomorrow")
async def upgrade_free_tomorrow(callback: CallbackQuery):
    await callback.message.answer(
        "⏳ <b>See you tomorrow!</b>\n\n"
        "Your daily watch limit resets at midnight UTC.\n"
        "You can also upgrade anytime from 📋 <b>My Plan</b>.",
        parse_mode="HTML",
    )
    await callback.answer("Limit resets tomorrow.")


@router.message(F.text.in_({"⭐ Get VIP", "✅ VIP Member"}))
async def get_vip(message: Message, db_user: dict):
    if db_user.get("plan") == "vip":
        from database.datetime_utils import ensure_aware

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
        text += f"\n\nRenew via {payment_contact_label()}."
        await message.answer(
            text,
            reply_markup=vip_keyboard(db_user),
            parse_mode="HTML",
        )
        return

    await message.answer(
        build_membership_catalog_text(),
        reply_markup=membership_catalog_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "vip:status")
async def vip_status_callback(callback: CallbackQuery, db_user: dict):
    if db_user.get("plan") != "vip":
        await callback.answer("VIP subscription required.", show_alert=True)
        return

    from database.datetime_utils import ensure_aware

    expires = ensure_aware(db_user.get("vip_expires"))
    remaining = _vip_time_remaining(db_user)
    text = "⭐ <b>You are a VIP Member</b>\n\nUnlimited episodes · full archive access"
    if expires:
        text += f"\n\nValid until: <b>{format_date(expires)}</b>"
    if remaining:
        text += f"\nTime remaining: <b>{remaining}</b>"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
