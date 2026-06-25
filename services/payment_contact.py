from aiogram.types import CallbackQuery, Message

from config import PAYMENT_CONTACT_USERNAME


def payment_contact_url() -> str:
    return f"https://t.me/{PAYMENT_CONTACT_USERNAME}"


def payment_contact_label() -> str:
    return f"@{PAYMENT_CONTACT_USERNAME}"


def build_payment_contact_text(
    *,
    purpose: str = "membership",
    telegram_id: int | None = None,
) -> str:
    if purpose == "unlock":
        lead = "To unlock an episode"
    else:
        lead = "For payment and VIP membership"

    lines = [
        "💳 <b>Payment & Membership</b>",
        "",
        f"{lead}, contact <b>{payment_contact_label()}</b> on Telegram.",
        "",
        "They will help you with VIP subscription or episode unlocks.",
    ]
    if telegram_id is not None:
        lines.extend(
            [
                "",
                f"Your Telegram ID: <code>{telegram_id}</code>",
                "<i>Share this ID when you message them.</i>",
            ]
        )
    return "\n".join(lines)


async def send_payment_contact_message(
    message: Message, *, purpose: str = "membership"
) -> None:
    from keyboards.inline import payment_contact_keyboard

    await message.answer(
        build_payment_contact_text(
            purpose=purpose,
            telegram_id=message.from_user.id if message.from_user else None,
        ),
        reply_markup=payment_contact_keyboard(),
        parse_mode="HTML",
    )


async def send_payment_contact_callback(
    callback: CallbackQuery, *, purpose: str = "membership"
) -> None:
    from keyboards.inline import payment_contact_keyboard

    await callback.message.answer(
        build_payment_contact_text(
            purpose=purpose,
            telegram_id=callback.from_user.id,
        ),
        reply_markup=payment_contact_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
