"""
SkyPath VPN Bot — Production Ready
Telegram Bot + Mini App для VPN сервиса
"""

import asyncio
import logging
import sys
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Config
from database.engine import init_db
from database.migrate import upgrade_head
from bot.handlers import (
    start_handler,
    account_handler,
    payment_handler,
    subscription_handler,
    admin_handler,
    miniapp_handler,
    referral_handler,
)
from bot.middlewares.throttle import ThrottlingMiddleware
from bot.middlewares.user import UserMiddleware
from bot.scheduler import setup_scheduler
from bot.admin.api import setup_admin_routes
from bot.cabinet.api import setup_cabinet_routes

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s: %(message)s"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
)
logger = logging.getLogger(__name__)

ALLOWED_UPDATES = ["message", "callback_query", "pre_checkout_query", "web_app_data"]


def _restore_logging() -> None:
    """Alembic fileConfig может понизить root до WARN — восстанавливаем INFO."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, force=True)


async def on_startup(bot: Bot, config: Config):
    try:
        await upgrade_head()
    except Exception:
        logger.exception("Alembic migration failed — run: docker compose exec bot alembic upgrade head")
        raise
    _restore_logging()
    await init_db()
    logger.info("Database initialized")

    if config.use_polling:
        try:
            await asyncio.wait_for(
                bot.delete_webhook(drop_pending_updates=True),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.warning("delete_webhook timed out — starting polling anyway")
        except Exception:
            logger.exception("delete_webhook failed — starting polling anyway")
        logger.warning("BOT_MODE=polling: Telegram long polling enabled")
        return

    webhook_url = f"{config.WEBHOOK_BASE_URL.rstrip('/')}/webhook"
    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=config.WEBHOOK_SECRET,
            drop_pending_updates=True,
            allowed_updates=ALLOWED_UPDATES,
        )
        logger.info("Webhook set: %s", webhook_url)
    except Exception:
        logger.exception("Failed to set Telegram webhook at %s", webhook_url)
        raise


async def on_shutdown(bot: Bot, config: Config):
    if not config.use_polling:
        await bot.delete_webhook()
        logger.info("Bot stopped, webhook removed")


def create_app(config: Config) -> web.Application:
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage.from_url(config.REDIS_URL)
    dp = Dispatcher(storage=storage)

    dp.update.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_router(start_handler.router)
    dp.include_router(account_handler.router)
    dp.include_router(subscription_handler.router)
    dp.include_router(payment_handler.router)
    dp.include_router(referral_handler.router)
    dp.include_router(admin_handler.router)
    dp.include_router(miniapp_handler.router)

    _lifecycle_started = False
    polling_task: asyncio.Task[None] | None = None
    scheduler = None

    async def _startup(**_kwargs):
        nonlocal _lifecycle_started, polling_task, scheduler
        if _lifecycle_started:
            return
        _lifecycle_started = True

        await on_startup(bot, config)
        try:
            me = await asyncio.wait_for(bot.get_me(), timeout=15)
            logger.warning("Telegram bot ready: @%s (id=%s)", me.username, me.id)
        except Exception:
            logger.exception("Telegram getMe failed — проверьте BOT_TOKEN и доступ к api.telegram.org")
        scheduler = setup_scheduler(bot)
        if config.use_polling:
            polling_task = asyncio.create_task(
                dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES, handle_signals=False),
                name="telegram-polling",
            )
            logger.warning("Telegram polling task started")

            def _log_polling_crash(task: asyncio.Task[None]) -> None:
                if task.cancelled():
                    return
                exc = task.exception()
                if exc is not None:
                    logger.error("Telegram polling crashed: %s", exc, exc_info=exc)

            polling_task.add_done_callback(_log_polling_crash)

    async def _shutdown(**_kwargs):
        nonlocal polling_task, scheduler
        if scheduler is not None:
            scheduler.shutdown(wait=False)
            scheduler = None
        if polling_task is not None:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
            polling_task = None
        await on_shutdown(bot, config)

    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    app = web.Application()
    app["bot"] = bot
    app["config"] = config

    # Platega на отдельном пути (без токена в URL — иначе NPM/Telegram могут ломать ':')
    app.router.add_post("/webhook/platega", payment_handler.platega_webhook)

    if not config.use_polling:
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=config.WEBHOOK_SECRET,
            handle_in_background=True,
        ).register(app, path="/webhook")
        logger.info("Telegram webhook route: POST /webhook (secret_token)")
    else:
        logger.info("Telegram webhook route: disabled (polling mode)")

    setup_application(app, dp, bot=bot)

    app.router.add_get("/api/config", miniapp_handler.get_config)
    app.router.add_get("/api/plans", miniapp_handler.get_plans)
    app.router.add_get("/api/user/{telegram_id}", miniapp_handler.get_user_info)
    app.router.add_get("/api/subscription/{telegram_id}", miniapp_handler.get_subscription)
    app.router.add_get("/api/dashboard/{telegram_id}", miniapp_handler.get_dashboard)
    app.router.add_post("/api/pay", miniapp_handler.create_payment)
    app.router.add_get("/api/discount/preview/{telegram_id}", miniapp_handler.preview_discount)
    app.router.add_post("/api/promo/validate", miniapp_handler.validate_promo)
    app.router.add_get("/api/payment/{order_id}/status", miniapp_handler.get_payment_status)
    app.router.add_post("/api/register", miniapp_handler.register_web_account)
    app.router.add_post("/api/provision", miniapp_handler.provision_vpn)
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))

    setup_admin_routes(app, config)
    setup_cabinet_routes(app, config)

    # Mini App (при NPM вместо compose-nginx статика отдаётся ботом)
    webapp_dir = Path(__file__).resolve().parent.parent / "webapp"
    webapp_index = webapp_dir / "index.html"
    webapp_install = webapp_dir / "install.html"
    if webapp_index.is_file():
        async def _redirect_app(_request: web.Request) -> web.Response:
            raise web.HTTPFound("/app/")

        async def _serve_webapp(_request: web.Request) -> web.Response:
            return web.FileResponse(webapp_index)

        async def _serve_webapp_install(_request: web.Request) -> web.Response:
            return web.FileResponse(webapp_install)

        app.router.add_get("/app", _redirect_app)
        app.router.add_get("/app/", _serve_webapp)
        app.router.add_get("/app/index.html", _serve_webapp)
        if webapp_install.is_file():
            app.router.add_get("/app/install.html", _serve_webapp_install)

        for static_name in ("favicon.svg", "apple-touch-icon.png", "site.webmanifest"):
            static_path = webapp_dir / static_name
            if static_path.is_file():

                async def _serve_webapp_static(
                    _request: web.Request, path: Path = static_path
                ) -> web.Response:
                    return web.FileResponse(path)

                app.router.add_get(f"/app/{static_name}", _serve_webapp_static)

        logger.info("Webapp: %s", webapp_index)

    return app


if __name__ == "__main__":
    cfg = Config()
    if "--polling" in sys.argv:
        cfg.BOT_MODE = "polling"
    application = create_app(cfg)
    web.run_app(application, host="0.0.0.0", port=cfg.PORT)
