from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import ADMIN_IDS
from handlers.payment import begin_payment_upload
from keyboards.inline import main_menu_keyboard, plan_keyboard
from services.greetings import is_greeting
from services.messages import build_user_info_text

router = Router()


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    db_user: dict,
):
    if command.args and command.args.startswith("pay_"):
        payment_id = command.args[len("pay_") :]
        await begin_payment_upload(message, state, payment_id)
        return

    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        build_user_info_text(db_user, is_admin=is_admin),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(F.text.func(is_greeting))
async def greeting(message: Message, db_user: dict):
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        build_user_info_text(db_user, is_admin=is_admin),
        reply_markup=plan_keyboard(),
        parse_mode="HTML",
    )
