import logging
from datetime import datetime

from aiogram import Bot

from database import repository as repo
from services.messages import format_date

logger = logging.getLogger(__name__)


async def get_telegram_file_url(bot: Bot, file_id: str) -> str | None:
    try:
        file = await bot.get_file(file_id)
        if not file.file_path:
            return None
        return f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    except Exception:
        logger.exception("Failed to resolve Telegram file %s", file_id)
        return None


async def notify_user(bot: Bot, user_id: int, text: str, *, parse_mode: str = "HTML") -> bool:
    try:
        await bot.send_message(user_id, text, parse_mode=parse_mode)
        return True
    except Exception:
        logger.exception("Failed to notify user %s", user_id)
        return False


async def approve_payment(bot: Bot, payment_id: str, admin_id: int) -> tuple[bool, str]:
    payment = await repo.review_payment(payment_id, True, admin_id)
    if not payment:
        return False, "Payment not found or already reviewed."

    user_id = payment["user_id"]
    if payment["type"] == "vip":
        expires = await repo.grant_vip(user_id)
        await notify_user(
            bot,
            user_id,
            "⭐ <b>You are now a VIP Member!</b>\n\n"
            f"Unlimited episodes until <b>{format_date(expires)}</b>.",
        )
    elif payment["type"] == "unlock" and payment.get("episode_id"):
        await repo.grant_episode_unlock(user_id, payment["episode_id"])
        await notify_user(
            bot,
            user_id,
            "🔓 <b>Episode unlocked!</b>\n"
            "You can now watch it without using your daily limit.",
        )
    return True, "Payment approved."


async def reject_payment(bot: Bot, payment_id: str, admin_id: int) -> tuple[bool, str]:
    payment = await repo.review_payment(payment_id, False, admin_id)
    if not payment:
        return False, "Payment not found or already reviewed."

    await notify_user(
        bot,
        payment["user_id"],
        "❌ Your payment was not approved.\n"
        "Contact support if you believe this is an error.",
        parse_mode=None,
    )
    return True, "Payment rejected."


async def grant_vip_with_notify(bot: Bot, telegram_id: int, days: int = 30) -> datetime:
    expires = await repo.grant_vip(telegram_id, days)
    await notify_user(
        bot,
        telegram_id,
        "⭐ <b>You are now a VIP Member!</b>\n\n"
        f"Unlimited episodes until <b>{format_date(expires)}</b>.",
    )
    return expires


async def revoke_vip_with_notify(bot: Bot, telegram_id: int) -> bool:
    removed = await repo.revoke_vip(telegram_id)
    if removed:
        await notify_user(
            bot,
            telegram_id,
            "Your VIP membership has been removed.\n"
            "You are now on the free tier. Contact support if you have questions.",
            parse_mode=None,
        )
    return removed


async def broadcast_message(bot: Bot, text: str) -> tuple[int, int]:
    user_ids = await repo.get_all_user_ids()
    sent = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
    return sent, len(user_ids)


async def reply_support_ticket(
    bot: Bot, ticket_id: str, admin_reply: str, admin_id: int
) -> tuple[bool, str]:
    ticket = await repo.reply_support_ticket(ticket_id, admin_reply, admin_id)
    if not ticket:
        return False, "Ticket not found or already closed."

    await notify_user(
        bot,
        ticket["user_id"],
        f"💬 <b>Support reply</b>\n\n{admin_reply}",
    )
    return True, "Reply sent and ticket closed."
