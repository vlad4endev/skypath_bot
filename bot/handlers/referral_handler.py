"""
Реферальная программа: 7 бонусных дней за каждого приведённого друга (первая оплата).
"""
import logging
from aiogram import Router, Bot

from bot.config import Config
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo, PaymentRepo
from database.models import User, SubscriptionStatus

router = Router()
logger = logging.getLogger(__name__)
config = Config()

REFERRAL_BONUS_DAYS = 7


def referral_link(telegram_id: int, bot_username: str | None = None) -> str:
    """Реферальная ссылка для шаринга."""
    username = (bot_username or config.BOT_USERNAME).lstrip("@")
    return f"https://t.me/{username}?start=ref_{telegram_id}"


async def process_referral_bonus(bot: Bot, payer: User, payment_id: str) -> None:
    """
    Начислить 7 дней рефереру, когда приглашённый друг впервые оплатил подписку.
    Идемпотентно: бонус только при первом успешном платеже плательщика.
    """
    if not payer.referrer_id:
        return

    try:
        async with async_session() as session:
            pay_repo = PaymentRepo(session)
            user_repo = UserRepo(session)
            sub_repo = SubscriptionRepo(session)

            paid_count = await pay_repo.count_succeeded_for_user(payer.id)
            if paid_count != 1:
                return

            referrer = await user_repo.get_by_telegram_id(payer.referrer_id)
            if not referrer:
                return

            active_sub = await sub_repo.get_active(referrer.telegram_id)
            if active_sub:
                await sub_repo.extend_days(active_sub, REFERRAL_BONUS_DAYS)
            else:
                logger.info(
                    "Referrer %s has no active sub — bonus days skipped",
                    referrer.telegram_id,
                )
                return

        await bot.send_message(
            referrer.telegram_id,
            f"🎁 <b>Реферальный бонус!</b>\n\n"
            f"Твой друг оплатил подписку — мы добавили <b>{REFERRAL_BONUS_DAYS} дней</b> "
            f"к твоей подписке.\n\n"
            f"Приводи друзей: за каждого — ещё {REFERRAL_BONUS_DAYS} дней!",
        )
        logger.info(
            "Referral bonus +%s days for %s (payment %s)",
            REFERRAL_BONUS_DAYS,
            referrer.telegram_id,
            payment_id,
        )
    except Exception as e:
        logger.error("Referral bonus failed for payment %s: %s", payment_id, e)
