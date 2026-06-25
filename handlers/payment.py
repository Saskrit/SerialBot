from aiogram import F, Router
from aiogram.types import CallbackQuery

from services.payment_contact import send_payment_contact_callback

router = Router()


@router.callback_query(F.data.startswith("pay:unlock:"))
async def pay_unlock(callback: CallbackQuery):
    await send_payment_contact_callback(callback, purpose="unlock")


@router.callback_query(F.data == "pay:vip")
async def pay_vip(callback: CallbackQuery):
    await send_payment_contact_callback(callback, purpose="vip")
