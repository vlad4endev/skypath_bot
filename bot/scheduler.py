"""
Планировщик задач — уведомления, grace period, деактивация и очистка VPN
"""
import logging
from datetime import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import Config, PLANS
from bot.i18n import get_user_locale, t
from bot.i18n.plans import plan_display_name
from database.engine import async_session
from database.repository import SubscriptionRepo, PaymentRepo, UserRepo, ACTIVE_SUBSCRIPTION_STATUSES
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


GRACE_PERIOD_DAYS = 7
# Дни после отключения VPN → очередное напоминание (последний = удаление из 3X-UI)
GRACE_REMINDER_DAYS = (1, 3, 5, 7)


def _is_trial_sub(sub: Subscription) -> bool:
    return sub.plan == PlanType.FREE or sub.status == SubscriptionStatus.FREE_TRIAL


def _plan_label(sub: Subscription, locale: str) -> str:
    key = sub.plan.value if sub.plan else "BASIC"
    return plan_display_name(key, locale)


def _expiry_date(sub: Subscription) -> str:
    return sub.expires_at.strftime("%d.%m.%Y") if sub.expires_at else "—"


async def _locale_for_user(telegram_id: int) -> str:
    async with async_session() as session:
        user_repo = UserRepo(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
    return get_user_locale(user)


def _msg_expiring_tomorrow_trial(sub: Subscription, locale: str) -> str:
    return t(
        locale,
        "scheduler.expiring_tomorrow_trial",
        date=_expiry_date(sub),
        brand=config.BRAND_NAME,
        grace_days=GRACE_PERIOD_DAYS,
    )


def _msg_expiring_tomorrow_paid(sub: Subscription, locale: str) -> str:
    return t(
        locale,
        "scheduler.expiring_tomorrow_paid",
        plan=_plan_label(sub, locale),
        date=_expiry_date(sub),
    )


def _msg_expiring_today_trial(sub: Subscription, locale: str) -> str:
    return t(locale, "scheduler.expiring_today_trial")


def _msg_expiring_today_paid(sub: Subscription, locale: str) -> str:
    return t(locale, "scheduler.expiring_today_paid", plan=_plan_label(sub, locale))


def _msg_subscription_expired(sub: Subscription, locale: str) -> str:
    is_trial = _is_trial_sub(sub)
    label = t(locale, "scheduler.expired_trial_label") if is_trial else _plan_label(sub, locale)
    return t(
        locale,
        "scheduler.expired",
        label=label,
        grace_days=GRACE_PERIOD_DAYS,
    )


def _msg_grace_reminder(sub: Subscription, reminder_index: int, locale: str) -> str:
    days_left = _grace_days_left(sub)
    is_trial = _is_trial_sub(sub)
    label = t(locale, "scheduler.trial_label") if is_trial else _plan_label(sub, locale)
    key = f"scheduler.grace_{reminder_index}"
    return t(locale, key, label=label, days_left=days_left, brand=config.BRAND_NAME)


def _msg_grace_purged(locale: str) -> str:
    return t(locale, "scheduler.grace_purged")


def _renew_kb(is_trial: bool = False, locale: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from bot.keyboards.webapp import cabinet_button, is_miniapp_available

    builder = InlineKeyboardBuilder()
    if is_miniapp_available():
        label = t(locale, "menu.subscribe") if is_trial else t(locale, "menu.renew")
        builder.row(cabinet_button(label, locale=locale))
    builder.row(
        InlineKeyboardButton(text=t(locale, "menu.support"), url=config.SUPPORT_URL),
    )
    return builder.as_markup()


def _days_since_disabled(sub: Subscription) -> int:
    if not sub.vpn_disabled_at:
        return 0
    return (datetime.utcnow() - sub.vpn_disabled_at).days


def _grace_days_left(sub: Subscription) -> int:
    if not sub.vpn_disabled_at:
        return GRACE_PERIOD_DAYS
    elapsed = _days_since_disabled(sub)
    return max(0, GRACE_PERIOD_DAYS - elapsed)


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
                locale = await _locale_for_user(sub.telegram_id)
                is_trial = _is_trial_sub(sub)
                text = (
                    _msg_expiring_tomorrow_trial(sub, locale)
                    if is_trial
                    else _msg_expiring_tomorrow_paid(sub, locale)
                )

                await bot.send_message(
                    chat_id=sub.telegram_id,
                    text=text,
                    reply_markup=_renew_kb(is_trial=is_trial, locale=locale),
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
                locale = await _locale_for_user(sub.telegram_id)
                is_trial = _is_trial_sub(sub)
                text = (
                    _msg_expiring_today_trial(sub, locale)
                    if is_trial
                    else _msg_expiring_today_paid(sub, locale)
                )

                await bot.send_message(
                    chat_id=sub.telegram_id,
                    text=text,
                    reply_markup=_renew_kb(is_trial=is_trial, locale=locale),
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

                is_trial = _is_trial_sub(sub)
                locale = await _locale_for_user(sub.telegram_id)
                try:
                    await bot.send_message(
                        sub.telegram_id,
                        _msg_subscription_expired(sub, locale),
                        reply_markup=_renew_kb(is_trial=is_trial, locale=locale),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning("Expired notify failed %s: %s", sub.telegram_id, e)

                logger.info("Expired subscription %s for user %s", sub.id, sub.telegram_id)
            except Exception as e:
                logger.error("Error expiring sub %s: %s", sub.id, e)
    except Exception as e:
        logger.error("job_expire_subscriptions failed: %s", e)


async def job_grace_period(bot: Bot):
    """Напоминания в течение недели после истечения + удаление из 3X-UI."""
    try:
        async with async_session() as session:
            sub_repo = SubscriptionRepo(session)
            subs = await sub_repo.get_expired_pending_grace_actions()

        for sub in subs:
            try:
                days_since = _days_since_disabled(sub)
                sent = sub.grace_reminders_sent or 0

                if days_since > GRACE_PERIOD_DAYS:
                    await _purge_vpn_client(bot, sub)
                    continue

                if sent >= len(GRACE_REMINDER_DAYS):
                    continue

                threshold = GRACE_REMINDER_DAYS[sent]
                if days_since < threshold:
                    continue

                is_trial = _is_trial_sub(sub)
                locale = await _locale_for_user(sub.telegram_id)
                text = _msg_grace_reminder(sub, sent, locale)
                if sent == len(GRACE_REMINDER_DAYS) - 1:
                    await _purge_vpn_client(bot, sub, farewell_text=text, locale=locale)
                else:
                    await bot.send_message(
                        sub.telegram_id,
                        text,
                        reply_markup=_renew_kb(is_trial=is_trial, locale=locale),
                        parse_mode="HTML",
                    )
                    async with async_session() as session:
                        sub_repo = SubscriptionRepo(session)
                        s = await sub_repo.get_by_id(sub.id)
                        if s:
                            await sub_repo.increment_grace_reminder(s)
                    logger.info(
                        "Grace reminder %s for user %s (day %s)",
                        sent + 1, sub.telegram_id, days_since,
                    )
            except Exception as e:
                logger.error("Grace period error sub %s: %s", sub.id, e)
    except Exception as e:
        logger.error("job_grace_period failed: %s", e)


async def _purge_vpn_client(
    bot: Bot,
    sub: Subscription,
    *,
    farewell_text: str | None = None,
    locale: str | None = None,
) -> None:
    """Удалить клиента из 3X-UI, очистить VPN-поля, оставить user для рассылок."""
    if sub.vpn_uuid and sub.inbound_id:
        try:
            await xui.delete_client(
                inbound_id=sub.inbound_id,
                client_uuid=sub.vpn_uuid,
                email=sub.vpn_email or "",
            )
        except Exception as e:
            logger.warning("XUI delete failed sub %s: %s", sub.id, e)

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        user_repo = UserRepo(session)
        s = await sub_repo.get_by_id(sub.id)
        if not s or s.vpn_purged_at:
            return
        await sub_repo.clear_vpn_client(s)
        await sub_repo.mark_vpn_purged(s)
        await user_repo.set_marketing_lead(s.user_id, value=True)

    is_trial = _is_trial_sub(sub)
    loc = locale or await _locale_for_user(sub.telegram_id)
    try:
        await bot.send_message(
            sub.telegram_id,
            farewell_text or _msg_grace_purged(loc),
            reply_markup=_renew_kb(is_trial=is_trial, locale=loc),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Grace purge notify failed %s: %s", sub.telegram_id, e)

    logger.info("Purged VPN for sub %s user %s (marketing lead)", sub.id, sub.telegram_id)


async def job_process_broadcasts(bot: Bot):
    """Отправка запланированных рассылок из web-админки."""
    try:
        from bot.services.broadcast_service import process_due_broadcasts
        count = await process_due_broadcasts(bot)
        if count:
            logger.info("Processed %s scheduled broadcast(s)", count)
    except Exception as e:
        logger.error("job_process_broadcasts failed: %s", e)


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
        job_grace_period,
        CronTrigger(hour=12, minute=0),
        args=[bot],
        id="grace_period",
        replace_existing=True,
    )
    scheduler.add_job(
        job_process_broadcasts,
        CronTrigger(minute="*"),
        args=[bot],
        id="process_broadcasts",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: 5 jobs active")
    return scheduler
