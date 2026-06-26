from aiogram import F, Router
from aiogram.types import CallbackQuery

from services.payment_contact import send_payment_contact_callback

router = Router()


@router.callback_query(F.data.startswith("pay:plan:"))
async def pay_plan(callback: CallbackQuery):
    parts = callback.data.split(":")
    # pay:plan:<plan_id> or pay:plan:episode_pass:<episode_id>
    plan_id = parts[2] if len(parts) > 2 else ""
    episode_id = parts[3] if len(parts) > 3 else None
    await send_payment_contact_callback(
        callback,
        plan_id=plan_id,
        episode_id=episode_id,
    )


@router.callback_query(F.data.startswith("pay:unlock:"))
async def pay_unlock(callback: CallbackQuery):
    episode_id = callback.data.split(":", 2)[2]
    await send_payment_contact_callback(
        callback,
        plan_id="episode_pass",
        episode_id=episode_id,
    )


@router.callback_query(F.data == "pay:vip")
async def pay_vip(callback: CallbackQuery):
    await send_payment_contact_callback(callback, plan_id="monthly_vip")
