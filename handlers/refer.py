from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from keyboards.inline import append_ui_actions
from services.private_dm import referral_deep_link
from services.referrals import build_referral_text

router = Router()


async def _referral_keyboard(bot, user: dict) -> InlineKeyboardMarkup:
    me = await bot.get_me()
    link = referral_deep_link(me.username or "", user["telegram_id"])
    rows = [
        [InlineKeyboardButton(text="📤 Share invite link", url=link)],
    ]
    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_referral_info(message: Message, db_user: dict) -> None:
    text = await build_referral_text(message.bot, db_user)
    await message.answer(
        text,
        reply_markup=await _referral_keyboard(message.bot, db_user),
        parse_mode="HTML",
    )


@router.message(Command("refer"))
@router.message(F.text == "🎁 Refer & Watch")
async def refer_command(message: Message, db_user: dict):
    await _send_referral_info(message, db_user)


@router.callback_query(F.data == "refer")
async def refer_callback(callback: CallbackQuery, db_user: dict):
    text = await build_referral_text(callback.bot, db_user)
    await callback.message.answer(
        text,
        reply_markup=await _referral_keyboard(callback.bot, db_user),
        parse_mode="HTML",
    )
    await callback.answer()
