from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import ADMIN_IDS
from database import repository as repo
from keyboards.inline import main_menu_keyboard, plan_keyboard
from services.greetings import is_greeting, is_status_query
from services.messages import build_status_text, build_user_info_text
from services.payment_contact import send_payment_contact_message
from services.referrals import parse_referral_start_arg, process_new_user_referral

router = Router()


async def _reply_status(message: Message, db_user: dict) -> None:
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        await build_status_text(db_user, is_admin=is_admin),
        reply_markup=plan_keyboard(db_user),
        parse_mode="HTML",
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    db_user: dict,
    is_new_user: bool = False,
):
    if command.args and command.args.startswith("pay_"):
        await send_payment_contact_message(message)
        return

    referrer_id = parse_referral_start_arg(command.args)
    if is_new_user and referrer_id:
        await process_new_user_referral(message.bot, message.from_user.id, referrer_id)
        refreshed = await repo.get_user(message.from_user.id)
        if refreshed:
            db_user = refreshed

    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        await build_user_info_text(db_user, is_admin=is_admin),
        reply_markup=main_menu_keyboard(db_user),
        parse_mode="HTML",
    )


@router.message(F.text.func(is_greeting))
async def greeting(message: Message, db_user: dict):
    is_admin = message.from_user.id in ADMIN_IDS
    await message.answer(
        await build_user_info_text(db_user, is_admin=is_admin),
        reply_markup=plan_keyboard(db_user),
        parse_mode="HTML",
    )


@router.message(Command("status"))
@router.message(F.text.func(is_status_query))
async def user_status(message: Message, db_user: dict):
    await _reply_status(message, db_user)
