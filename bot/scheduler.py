"""
Планировщик задач — уведомления, деактивация и удаление пробных VPN
"""
import logging
from datetime import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import Config
from database.engine import async_session
from database.repository import SubscriptionRepo, PaymentRepo, ACTIVE_SUBSCRIPTION_STATUSES
from database.models import Subscription, SubscriptionStatus, PlanType
from bot.services.xui_client import XUIClient
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)
config = Config()

xui = XUIClient(
    host=config.XUI_HOST,
    url_prefix=config.XUI_URL_PREFIX,
    username=config.XUI_USERNAME,
    password=config.XUI_PASSWORD,
    api_token=config.XUI_API_TOKEN,
    sub_path=config.XUI_SUB_PATH,
    sub_base_url=config.XUI_SUB_BASE_URL,
)


def _is_trial_sub(sub: Subscription) -> bool:
    return sub.plan == PlanType.FREE or sub.status == SubscriptionStatus.FREE_TRIAL


def _renew_kb(is_trial: bool = False):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from bot.keyboards.webapp import cabinet_button, is_miniapp_available

    builder = InlineKeyboardBuilder()
    if is_miniapp_available():
        label = "💳 Оформить подписку" if is_trial else "🔄 Продлить"
        builder.row(cabinet_button(label))
    builder.row(
        InlineKeyboardButton(text="❓ Поддержка", url=config.SUPPORT_URL),
    )
    return builder.as_markup()


async def _user_has_paid_subscription(session, user_id: int, after: datetime | None = None) -> bool:
    pay_repo = PaymentRepo(session)
    count = await pay_repo.count_succeeded_for_user(user_id)
    if count > 0:
        return True
    result = await session.execute(
        select(Subscription).where(
            and_(
                Subscription.user_id == user_id,
                Subscription.plan != PlanType.FREE,
                Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            )
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def job_notify_expiring_tomorrow(bot: Bot):
    try:
        async with async_session() as session:
            sub_repo = SubscriptionRepo(session)
            subs = await sub_repo.get_expiring_tomorrow()

        for sub in subs:
            try:
                is_trial = _is_trial_sub(sub)
                if is_trial:
                    caption = (
                        f"👋 Привет!\n\n"
                        f"Завтра заканчивается <b>пробный период</b>.\n\n"
                        f"📅 Дата окончания: <b>{sub.expires_at.strftime('%d.%m.%Y')}</b>\n\n"
                        f"Оформи подписку от <b>250 ₽/мес</b>, чтобы VPN продолжил работать.\n"
                        f"Если не оплатить — доступ будет закрыт, ключ удалён через 3 дня."
                    )
                else:
                    caption = (
                        f"👋 Привет!\n\n"
                        f"Завтра истекает твоя подписка <b>{sub.plan.value}</b>.\n\n"
                        f"📅 Дата истечения: <b>{sub.expires_at.strftime('%d.%m.%Y')}</b>\n\n"
                        f"Не забудь продлить, чтобы не потерять доступ! 🔒"
                    )

                await bot.send_photo(
                    chat_id=sub.telegram_id,
                    photo="https://disk.yandex.ru/i/u-I6SN_IlTZnZQ",
                    caption=caption,
                    reply_markup=_renew_kb(is_trial=is_trial),
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
                is_trial = _is_trial_sub(sub)
                if is_trial:
                    caption = (
                        f"⚠️ <b>Последний день пробного периода!</b>\n\n"
                        f"Сегодня доступ к VPN будет закрыт, если не оформить подписку.\n"
                        f"Нажми «Оформить подписку» — от 250 ₽/мес."
                    )
                else:
                    caption = (
                        f"⚠️ Сегодня последний день твоей подписки <b>{sub.plan.value}</b>!\n\n"
                        f"Продли сейчас, чтобы не потерять доступ к VPN. 🔒"
                    )

                await bot.send_photo(
                    chat_id=sub.telegram_id,
                    photo="https://disk.yandex.ru/i/u-I6SN_IlTZnZQ",
                    caption=caption,
                    reply_markup=_renew_kb(is_trial=is_trial),
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
    """Закрыть истёкшие подписки: отключить клиента в 3X-UI."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(
                    and_(
                        Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
                        Subscription.expires_at < datetime.utcnow(),
                    )
                )
            )
            expired_subs = result.scalars().all()

        for sub in expired_subs:
            try:
                async with async_session() as session:
                    has_paid = await _user_has_paid_subscription(session, sub.user_id)

                if _is_trial_sub(sub) and has_paid:
                    async with async_session() as session:
                        sub_repo = SubscriptionRepo(session)
                        s = await sub_repo.get_by_id(sub.id)
                        if s:
                            await sub_repo.expire(s)
                    logger.info("Trial sub %s expired (user has paid plan)", sub.id)
                    continue

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
                        await sub_repo.mark_vpn_disabled(s)

                if _is_trial_sub(sub):
                    try:
                        await bot.send_message(
                            sub.telegram_id,
                            "🔒 <b>Пробный период завершён.</b>\n\n"
                            "VPN отключён. Оформи подписку, чтобы снова подключиться.\n"
                            "Ключ будет удалён с сервера через 3 дня.",
                            reply_markup=_renew_kb(is_trial=True),
                        )
                    except Exception as e:
                        logger.warning("Trial expired notify failed %s: %s", sub.telegram_id, e)

                logger.info("Expired subscription %s for user %s", sub.id, sub.telegram_id)
            except Exception as e:
                logger.error("Error expiring sub %s: %s", sub.id, e)
    except Exception as e:
        logger.error("job_expire_subscriptions failed: %s", e)


async def job_delete_expired_trial_clients(bot: Bot):
    """Удалить из 3X-UI клиентов пробного периода через 3 дня после отключения."""
    try:
        async with async_session() as session:
            sub_repo = SubscriptionRepo(session)
            subs = await sub_repo.get_free_trials_pending_vpn_deletion()

        for sub in subs:
            try:
                if sub.vpn_uuid and sub.inbound_id:
                    await xui.delete_client(
                        inbound_id=sub.inbound_id,
                        client_uuid=sub.vpn_uuid,
                        email=sub.vpn_email or "",
                    )

                async with async_session() as session:
                    sub_repo = SubscriptionRepo(session)
                    s = await sub_repo.get_by_id(sub.id)
                    if s:
                        await sub_repo.clear_vpn_client(s)

                logger.info("Deleted trial VPN client for sub %s user %s", sub.id, sub.telegram_id)
            except Exception as e:
                logger.error("Error deleting trial VPN sub %s: %s", sub.id, e)
    except Exception as e:
        logger.error("job_delete_expired_trial_clients failed: %s", e)


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
    scheduler.add_job(
        job_delete_expired_trial_clients,
        CronTrigger(hour=11, minute=0),
        args=[bot],
        id="delete_trial_vpn",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: 4 jobs active")
    return scheduler
