"""
SkyPath VPN Bot — Production Ready
Telegram Bot + Mini App для VPN сервиса
"""

import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Config
from database.engine import init_db
from bot.handlers import (
    start_handler,
    account_handler,
    subscription_handler,
    payment_handler,
    admin_handler,
    miniapp_handler,
    referral_handler,
)
from bot.middlewares.throttle import ThrottlingMiddleware
from bot.middlewares.user import UserMiddleware
from bot.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, config: Config):
    await init_db()
    logger.info("Database initialized")

    await bot.set_webhook(
        url=f"{config.WEBHOOK_BASE_URL}/webhook/{config.BOT_TOKEN}",
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query", "pre_checkout_query", "web_app_data"],
    )
    logger.info("Webhook set: %s", config.WEBHOOK_BASE_URL)


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logger.info("Bot stopped, webhook removed")


def create_app(config: Config) -> web.Application:
    bot = Bot(token=config.BOT_TOKEN, parse_mode="HTML")
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

    async def _startup():
        await on_startup(bot, config)

    async def _shutdown():
        await on_shutdown(bot)

    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    setup_scheduler(bot)

    app = web.Application()
    app["bot"] = bot
    app["config"] = config

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(
        app, path=f"/webhook/{config.BOT_TOKEN}"
    )
    setup_application(app, dp, bot=bot)

    app.router.add_get("/api/config", miniapp_handler.get_config)
    app.router.add_get("/api/user/{telegram_id}", miniapp_handler.get_user_info)
    app.router.add_get("/api/subscription/{telegram_id}", miniapp_handler.get_subscription)
    app.router.add_post("/api/pay", miniapp_handler.create_payment)
    app.router.add_post("/webhook/platega", payment_handler.platega_webhook)
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))

    return app


if __name__ == "__main__":
    cfg = Config()
    application = create_app(cfg)
    web.run_app(application, host="0.0.0.0", port=cfg.PORT)
