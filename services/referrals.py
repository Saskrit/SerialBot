import logging

from aiogram import Bot

from config import REFERRAL_BONUS_WATCHES
from database import repository as repo
from services.private_dm import referral_deep_link, send_private_message

logger = logging.getLogger(__name__)

REFERRAL_START_PREFIX = "ref_"


def parse_referral_start_arg(args: str | None) -> int | None:
    if not args or not args.startswith(REFERRAL_START_PREFIX):
        return None
    raw = args[len(REFERRAL_START_PREFIX) :].strip()
    if raw.isdigit():
        return int(raw)
    return None


async def process_new_user_referral(
    bot: Bot, new_user_id: int, referrer_id: int
) -> bool:
    ok, reason, credits = await repo.apply_referral(
        new_user_id,
        referrer_id,
        bonus_watches=REFERRAL_BONUS_WATCHES,
    )
    if not ok:
        logger.info(
            "Referral skipped for user %s via %s: %s",
            new_user_id,
            referrer_id,
            reason,
        )
        return False

    await send_private_message(
        bot,
        referrer_id,
        (
            "🎁 <b>New invite!</b>\n\n"
            "Someone joined Serial Hub using your link.\n"
            f"You earned <b>{REFERRAL_BONUS_WATCHES}</b> bonus watches.\n"
            f"Bonus watches available: <b>{credits}</b>"
        ),
        parse_mode="HTML",
    )
    return True


async def build_referral_text(bot: Bot, user: dict) -> str:
    username = await bot.get_me()
    bot_username = username.username or ""
    link = referral_deep_link(bot_username, user["telegram_id"])
    invites = user.get("referral_count", 0)
    bonus = user.get("referral_watch_credits", 0)

    lines = [
        "🎁 <b>Refer & Watch</b>",
        "",
        "Invite friends to Serial Hub. When someone joins using your link, "
        f"you get <b>{REFERRAL_BONUS_WATCHES} bonus watches</b> per invite.",
        "",
        "Each person can only join through one referrer.",
        "",
        f"Your invites: <b>{invites}</b>",
        f"Bonus watches left: <b>{bonus}</b>",
        "",
        "Share this link:",
        f"<code>{link}</code>",
        "",
        "Or forward this message — your link is inside the button below.",
    ]
    return "\n".join(lines)
