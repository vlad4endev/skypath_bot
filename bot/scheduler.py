"""
Планировщик задач — уведомления и деактивация подписок
"""
import logging
from datetime import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import Config
from database.engine import async_session
from database.repository import SubscriptionRepo
from database.models import SubscriptionStatus
from bot.services.xui_client import XUIClient

logger = logging.getLogger(__name__)
config = Config()

xui = XUIClient(
    host=config.XUI_HOST,
    url_prefix=config.XUI_URL_PREFIX,
    username=config.XUI_USERNAME,
    password=config.XUI_PASSWORD,
    api_token=config.XUI_API_TOKEN,
    sub_path=config.XUI_SUB_PATH,
)


async def job_notify_expiring_tomorrow(bot: Bot):
    try:
        async with async_session() as session:
            sub_repo = SubscriptionRepo(session)
            subs = await sub_repo.get_expiring_tomorrow()

        for sub in subs:
            try:
                await bot.send_photo(
                    chat_id=sub.telegram_id,
                    photo="https://disk.yandex.ru/i/u-I6SN_IlTZnZQ",
                    caption=(
                        f"👋 Привет!\n\n"
                        f"Завтра истекает твоя подписка <b>{sub.plan.value}</b>.\n\n"
                        f"📅 Дата истечения: <b>{sub.expires_at.strftime('%d.%m.%Y')}</b>\n\n"
                        f"Не забудь продлить, чтобы не потерять доступ! 🔒"
                    ),
                    reply_markup=_renew_kb(),
                    parse_mode="HTML",
                )
                async with async_session() as session:
                    sub_repo = SubscriptionRepo(session)
                    s = await sub_repo.get_by_id(sub.id)
                    if s:
                        s.notified_1day = True
                        await session.commit()
                logger.info("Notified user %s about expiry tomorrow", sub.telegram_id)
            except Exception as e:
                logger.warning("Failed to notify %s: %s", sub.telegram_id, e)
    except Exception as e:
        logger.error("job_notify_expiring_tomorrow failed: %s", e)


async def job_notify_expiring_today(bot: Bot):
    try:
        async with async_session() as session:
            sub_repo = SubscriptionRepo(session)
            subs = await sub_repo.get_expiring_today()

        for sub in subs:
            try:
                await bot.send_photo(
                    chat_id=sub.telegram_id,
                    photo="https://disk.yandex.ru/i/u-I6SN_IlTZnZQ",
                    caption=(
                        f"⚠️ Сегодня последний день твоей подписки <b>{sub.plan.value}</b>!\n\n"
                        f"Продли сейчас, чтобы не потерять доступ к VPN. 🔒"
                    ),
                    reply_markup=_renew_kb(),
                    parse_mode="HTML",
                )
                async with async_session() as session:
                    sub_repo = SubscriptionRepo(session)
                    s = await sub_repo.get_by_id(sub.id)
                    if s:
                        s.notified_expired = True
                        await session.commit()
            except Exception as e:
                logger.warning("Failed to notify %s: %s", sub.telegram_id, e)
    except Exception as e:
        logger.error("job_notify_expiring_today failed: %s", e)


async def job_expire_subscriptions(bot: Bot):
    try:
        async with async_session() as session:
            from sqlalchemy import select, and_
            from database.models import Subscription
            result = await session.execute(
                select(Subscription).where(
                    and_(
                        Subscription.status == SubscriptionStatus.ACTIVE,
                        Subscription.expires_at < datetime.utcnow(),
                    )
                )
            )
            expired_subs = result.scalars().all()

        for sub in expired_subs:
            try:
                if sub.vpn_uuid and sub.vpn_email and sub.vpn_sub_id and sub.inbound_id:
                    await xui.disable_client(
                        inbound_id=sub.inbound_id,
                        client_uuid=sub.vpn_uuid,
                        email=sub.vpn_email,
                        sub_id=sub.vpn_sub_id,
                        telegram_id=sub.telegram_id,
                        limit_ip=sub.limit_ip,
                    )

                async with async_session() as session:
                    sub_repo = SubscriptionRepo(session)
                    s = await sub_repo.get_by_id(sub.id)
                    if s:
                        await sub_repo.expire(s)

                logger.info("Expired subscription %s for user %s", sub.id, sub.telegram_id)
            except Exception as e:
                logger.error("Error expiring sub %s: %s", sub.id, e)
    except Exception as e:
        logger.error("job_expire_subscriptions failed: %s", e)


def _renew_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Продлить", callback_data="plans"),
        InlineKeyboardButton(text="❓ Поддержка", url=config.SUPPORT_URL),
    )
    return builder.as_markup()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        job_notify_expiring_tomorrow,
        CronTrigger(hour=8, minute=0),
        args=[bot],
        id="notify_tomorrow",
        replace_existing=True,
    )
    scheduler.add_job(
        job_notify_expiring_today,
        CronTrigger(hour=9, minute=0),
        args=[bot],
        id="notify_today",
        replace_existing=True,
    )
    scheduler.add_job(
        job_expire_subscriptions,
        CronTrigger(hour=10, minute=0),
        args=[bot],
        id="expire_subs",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: 3 jobs active")
    return scheduler
