from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from database import repository as repo
from keyboards.inline import notify_membership_keyboard, notify_serial_picker_keyboard
from services.notify_membership import (
    build_notify_status_text,
    get_notify_plan,
)
from services.payment_contact import payment_contact_label, send_payment_contact_callback

router = Router()


@router.message(F.text == "🔔 Episode Alerts")
async def notify_menu_message(message: Message, db_user: dict):
    await message.answer(
        build_notify_status_text(db_user),
        reply_markup=notify_membership_keyboard(db_user),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "notify:menu")
async def notify_menu_callback(callback: CallbackQuery, db_user: dict):
    refreshed = await repo.get_user(callback.from_user.id) or db_user
    await callback.message.answer(
        build_notify_status_text(refreshed),
        reply_markup=notify_membership_keyboard(refreshed),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notify:plan:"))
async def notify_plan_info(callback: CallbackQuery):
    plan_id = callback.data.split(":", 2)[2]
    plan = get_notify_plan(plan_id)
    if not plan:
        await callback.answer("Plan not found.", show_alert=True)
        return
    limit_line = (
        "All serials in the catalog"
        if plan.serial_limit is None
        else f"Pick up to <b>{plan.serial_limit}</b> serials"
    )
    await callback.message.answer(
        f"🔔 <b>{plan.name}</b>\n\n"
        f"Price: <b>{plan.price_label}</b>\n"
        f"Validity: {plan.validity}\n"
        f"Coverage: {limit_line}\n\n"
        f"Contact <b>{payment_contact_label()}</b> on Telegram to subscribe.\n"
        "Share your Telegram ID when you message them.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notify:pay:"))
async def notify_plan_pay(callback: CallbackQuery):
    plan_id = callback.data.split(":", 2)[2]
    await send_payment_contact_callback(callback, plan_id=plan_id)


@router.callback_query(F.data.startswith("notify:pick:"))
async def notify_pick_serials(callback: CallbackQuery, db_user: dict):
    parts = callback.data.split(":")
    page = int(parts[-1]) if parts[-1].isdigit() else 0
    refreshed = await repo.get_user(callback.from_user.id) or db_user
    if not repo.has_active_notify_membership(refreshed):
        await callback.answer("Subscribe first to pick serials.", show_alert=True)
        return
    plan = get_notify_plan(refreshed.get("notify_plan"))
    if not plan or plan.serial_limit is None:
        await callback.answer("Your plan covers all serials.", show_alert=True)
        return
    keyboard = await notify_serial_picker_keyboard(refreshed, page)
    selected = refreshed.get("notify_serials") or []
    await callback.message.edit_text(
        f"🔔 <b>Select serials</b> ({len(selected)}/{plan.serial_limit})\n\n"
        "Tap to add or remove. ✅ = selected.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notify:toggle:"))
async def notify_toggle_serial(callback: CallbackQuery, db_user: dict):
    _, _, serial_slug, page_str = callback.data.split(":", 3)
    page = int(page_str)
    ok, reason = await repo.toggle_notify_serial(callback.from_user.id, serial_slug)
    if not ok:
        alerts = {
            "no_membership": "Subscribe to Episode Alerts first.",
            "all_serials": "Your plan already covers all serials.",
            "limit_reached": "Serial limit reached — remove one to add another.",
            "invalid_serial": "Serial not found.",
        }
        await callback.answer(alerts.get(reason, reason), show_alert=True)
        return
    refreshed = await repo.get_user(callback.from_user.id) or db_user
    plan = get_notify_plan(refreshed.get("notify_plan"))
    keyboard = await notify_serial_picker_keyboard(refreshed, page)
    selected = refreshed.get("notify_serials") or []
    limit = plan.serial_limit if plan else 0
    await callback.message.edit_text(
        f"🔔 <b>Select serials</b> ({len(selected)}/{limit})\n\n"
        "Tap to add or remove. ✅ = selected.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer("Updated.")
