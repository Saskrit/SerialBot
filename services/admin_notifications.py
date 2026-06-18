from aiogram import Bot

from config import ADMIN_IDS


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def notify_admins_new_user(
    bot: Bot,
    telegram_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    if telegram_id in ADMIN_IDS:
        return

    name = first_name or "Unknown"
    username_line = f"@{username}" if username else "Not set"
    text = (
        "👤 <b>New User Registered</b>\n\n"
        f"Name: <b>{name}</b>\n"
        f"Username: {username_line}\n"
        f"Telegram ID: <code>{telegram_id}</code>"
    )
    await notify_admins(bot, text)
