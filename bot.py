import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN environment variable is not set.")

# Optional: set TELEGRAM_PROXY=socks5://host:port if api.telegram.org is unreachable
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY")

RESTART_DELAY_SEC = 10

dp = Dispatcher()


def create_bot() -> Bot:
    if TELEGRAM_PROXY:
        session = AiohttpSession(proxy=TELEGRAM_PROXY)
        return Bot(token=BOT_TOKEN, session=session)
    return Bot(token=BOT_TOKEN)


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Welcome!\n\n"
        "Send a serial name:\n"
        "• Anupamaa\n"
        "• Udne Ki Aasha\n"
        "• YRKKH"
    )


@dp.message(F.text)
async def serial_search(message: Message):
    text = message.text.lower()

    if "anup" in text:

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="17 June 2026",
                        callback_data="anup_17"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="16 June 2026",
                        callback_data="anup_16"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="15 June 2026",
                        callback_data="anup_15"
                    )
                ]
            ]
        )

        await message.answer(
            "Anupamaa Episodes",
            reply_markup=keyboard
        )

    elif "udne" in text:

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="17 June 2026",
                        callback_data="udne_17"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="16 June 2026",
                        callback_data="udne_16"
                    )
                ]
            ]
        )

        await message.answer(
            "Udne Ki Aasha Episodes",
            reply_markup=keyboard
        )

    elif "yrkkh" in text or "rishta" in text:

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="17 June 2026",
                        callback_data="yrkkh_17"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="16 June 2026",
                        callback_data="yrkkh_16"
                    )
                ]
            ]
        )

        await message.answer(
            "Yeh Rishta Kya Kehlata Hai Episodes",
            reply_markup=keyboard
        )

    else:
        await message.answer(
            "Serial not found.\n\n"
            "Try:\n"
            "Anupamaa\n"
            "Udne Ki Aasha\n"
            "YRKKH"
        )


@dp.callback_query()
async def episode_clicked(callback: CallbackQuery):

    if callback.data == "anup_17":
        await callback.message.answer(
            "Anupamaa - 17 June 2026\n\n"
            "Video will be sent here later."
        )

    elif callback.data == "anup_16":
        await callback.message.answer(
            "Anupamaa - 16 June 2026\n\n"
            "Video will be sent here later."
        )

    elif callback.data == "anup_15":
        await callback.message.answer(
            "Anupamaa - 15 June 2026\n\n"
            "Video will be sent here later."
        )

    elif callback.data == "udne_17":
        await callback.message.answer(
            "Udne Ki Aasha - 17 June 2026"
        )

    elif callback.data == "udne_16":
        await callback.message.answer(
            "Udne Ki Aasha - 16 June 2026"
        )

    elif callback.data == "yrkkh_17":
        await callback.message.answer(
            "YRKKH - 17 June 2026"
        )

    elif callback.data == "yrkkh_16":
        await callback.message.answer(
            "YRKKH - 16 June 2026"
        )

    await callback.answer()


async def health_check(_request: web.Request) -> web.Response:
    return web.Response(text="Serial bot is running")


async def start_web_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.info("Health check server listening on port %s", port)


async def run_forever():
    await start_web_server()

    while True:
        bot = create_bot()
        try:
            logging.info("Bot starting...")
            await dp.start_polling(bot, close_bot_session=True)
            logging.warning("Polling stopped unexpectedly, restarting...")
        except KeyboardInterrupt:
            logging.info("Shutdown requested.")
            break
        except Exception:
            logging.exception("Bot crashed, will restart")
        finally:
            try:
                await bot.session.close()
            except Exception:
                pass

        logging.info("Restarting in %s seconds...", RESTART_DELAY_SEC)
        await asyncio.sleep(RESTART_DELAY_SEC)


if __name__ == "__main__":
    asyncio.run(run_forever())