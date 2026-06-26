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
from middlewares.logging import UpdateLoggingMiddleware
from middlewares.registration import UserRegistrationMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)

RESTART_ON_CRASH = os.getenv("RESTART_ON_CRASH", "true").lower() == "true"
POLLING_RETRY_SEC = int(os.getenv("POLLING_RETRY_SEC", "15"))

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
    app.router.add_get("/health", health_check)

    from web.routes import setup_admin_routes
    from web.user_routes import setup_user_routes

    setup_user_routes(app, create_bot)
    setup_admin_routes(app, create_bot)

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


async def polling_loop(dp: Dispatcher, shutdown: asyncio.Event) -> None:
    """Keep polling until shutdown. Restart automatically if polling drops."""
    while not shutdown.is_set():
        bot = create_bot()
        try:
            me = await bot.get_me()
            logger.info(
                "Telegram bot verified: @%s (id=%s)",
                me.username,
                me.id,
            )
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook cleared. Starting polling (only ONE instance allowed).")
            from services.trial_episodes import resume_pending_trial_deletions

            await resume_pending_trial_deletions(bot)
            await dp.start_polling(
                bot,
                close_bot_session=False,
                handle_signals=False,
            )
            logger.warning("Polling stopped.")
        except Exception:
            logger.exception("Polling error")
        finally:
            try:
                await bot.session.close()
            except Exception:
                pass

        if shutdown.is_set():
            break

        logger.info("Restarting polling in %s seconds...", POLLING_RETRY_SEC)
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=POLLING_RETRY_SEC)
            break
        except asyncio.TimeoutError:
            continue


async def run_once() -> None:
    validate_config()

    await start_web_server()

    try:
        await init_db()
    except Exception:
        logger.exception("MongoDB connection failed")
        await stop_web_server()
        raise SystemExit(1) from None

    dp = Dispatcher()
    dp.update.middleware(UpdateLoggingMiddleware())
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

    polling = asyncio.create_task(polling_loop(dp, shutdown))
    await shutdown.wait()

    if not polling.done():
        await dp.stop_polling()
        polling.cancel()
        try:
            await polling
        except asyncio.CancelledError:
            pass

    await close_db()
    await stop_web_server()


async def run_forever() -> None:
    while True:
        try:
            await run_once()
            break
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
