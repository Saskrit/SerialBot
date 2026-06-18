import asyncio
import logging
import os
import signal

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from config import RESTART_DELAY_SEC, TELEGRAM_PROXY, validate_config
from database.connection import close_db, init_db
from handlers import setup_routers
from middlewares.registration import UserRegistrationMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)

IS_RENDER = os.getenv("RENDER") == "true"
RESTART_ON_CRASH = (
    os.getenv("RESTART_ON_CRASH", "false" if IS_RENDER else "true").lower() == "true"
)

_web_runner: web.AppRunner | None = None


def create_bot() -> Bot:
    from config import BOT_TOKEN

    if TELEGRAM_PROXY:
        session = AiohttpSession(proxy=TELEGRAM_PROXY)
        return Bot(token=BOT_TOKEN, session=session)
    return Bot(token=BOT_TOKEN)


async def health_check(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "serial-hub-bot"})


async def start_web_server() -> web.AppRunner:
    global _web_runner
    port = int(os.getenv("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    _web_runner = runner
    logger.info("Health check server listening on 0.0.0.0:%s", port)
    return runner


async def stop_web_server() -> None:
    global _web_runner
    if _web_runner is not None:
        await _web_runner.cleanup()
        _web_runner = None


async def run_bot(dp: Dispatcher) -> None:
    bot = create_bot()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook cleared. Starting polling (single instance required).")
        await dp.start_polling(bot, close_bot_session=True)
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass


async def run_once() -> None:
    validate_config()

    runner = await start_web_server()

    try:
        await init_db()
    except Exception:
        logger.exception("MongoDB connection failed")
        await stop_web_server()
        raise SystemExit(1) from None

    dp = Dispatcher()
    dp.message.middleware(UserRegistrationMiddleware())
    dp.callback_query.middleware(UserRegistrationMiddleware())
    dp.include_router(setup_routers())

    shutdown = asyncio.Event()

    def request_shutdown() -> None:
        logger.info("Shutdown requested.")
        shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_: request_shutdown())

    polling = asyncio.create_task(run_bot(dp))
    stopper = asyncio.create_task(shutdown.wait())

    done, pending = await asyncio.wait(
        {polling, stopper},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    if shutdown.is_set() and not polling.done():
        await dp.stop_polling()
        try:
            await polling
        except Exception:
            pass

    await close_db()
    await stop_web_server()


async def run_forever() -> None:
    while True:
        try:
            await run_once()
            if not RESTART_ON_CRASH:
                break
            logger.warning("Polling stopped unexpectedly.")
        except SystemExit:
            raise
        except KeyboardInterrupt:
            logger.info("Shutdown requested.")
            break
        except Exception:
            if not RESTART_ON_CRASH:
                logger.exception("Fatal error, exiting.")
                raise
            logger.exception("Bot crashed, will restart")

        logger.info("Restarting in %s seconds...", RESTART_DELAY_SEC)
        await asyncio.sleep(RESTART_DELAY_SEC)


if __name__ == "__main__":
    asyncio.run(run_forever())
