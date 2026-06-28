import logging
from datetime import datetime

from aiogram import Bot

from database import repository as repo
from services.messages import format_date

logger = logging.getLogger(__name__)


async def notify_user(bot: Bot, user_id: int, text: str, *, parse_mode: str = "HTML") -> bool:
    try:
        await bot.send_message(user_id, text, parse_mode=parse_mode)
        return True
    except Exception:
        logger.exception("Failed to notify user %s", user_id)
        return False


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


async def grant_notify_with_notify(
    bot: Bot, telegram_id: int, plan_id: str, *, days: int = 30
) -> datetime:
    from services.notify_membership import get_notify_plan

    expires = await repo.grant_notify_membership(telegram_id, plan_id, days=days)
    plan = get_notify_plan(plan_id)
    name = plan.name if plan else "Episode Alerts"
    await notify_user(
        bot,
        telegram_id,
        f"🔔 <b>{name} activated!</b>\n\n"
        f"Valid until <b>{format_date(expires)}</b>.\n"
        "Open <b>🔔 Episode Alerts</b> in the menu to pick your serials.",
    )
    return expires


async def revoke_notify_with_notify(bot: Bot, telegram_id: int) -> bool:
    removed = await repo.revoke_notify_membership(telegram_id)
    if removed:
        await notify_user(
            bot,
            telegram_id,
            "Your Episode Alert membership has been removed.",
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
