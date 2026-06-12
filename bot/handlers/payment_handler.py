"""
Обработка платежей — создание, webhook, выдача VPN ключа
Это самый важный файл — вся логика оплаты здесь
"""
import logging
import json
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from aiohttp.web_request import Request

from bot.config import Config, PLANS, MONTHS_LABELS
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo, PaymentRepo, PromoRepo
from database.models import PlanType, SubscriptionStatus, PaymentStatus
from bot.services.payment import YooKassaClient, parse_webhook_event
from bot.services.xui_client import XUIClient
from bot.handlers.referral_handler import process_referral_bonus

router = Router()
logger = logging.getLogger(__name__)
config = Config()

# Клиенты сервисов
yookassa = YooKassaClient(config)
xui = XUIClient(
    host=config.XUI_HOST,
    url_prefix=config.XUI_URL_PREFIX,
    username=config.XUI_USERNAME,
    password=config.XUI_PASSWORD,
)


@router.callback_query(F.data.startswith("confirm_plan:"))
async def cb_confirm_plan(call: CallbackQuery):
    """
    Создать платёж и отправить ссылку пользователю
    confirm_plan:{plan_key}:{months}:{price}[:promo_CODE]
    """
    parts = call.data.split(":")
    plan_key = parts[1]
    months = int(parts[2])
    price = int(parts[3])
    promo_code = None

    if len(parts) > 4 and parts[4].startswith("promo_"):
        promo_code = parts[4].replace("promo_", "")

    plan = PLANS.get(plan_key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    user = call.from_user

    # Бесплатный период — выдаём сразу без оплаты
    if plan_key == "FREE" or price == 0:
        await call.answer("⏳ Создаём твой VPN...")
        await _issue_free_trial(call, user)
        return

    # Создаём запись подписки в БД
    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)
        pay_repo = PaymentRepo(session)
        promo_repo = PromoRepo(session)

        db_user, _ = await user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

        # Применяем промокод
        if promo_code:
            promo = await promo_repo.get_by_code(promo_code)
            if promo and promo.is_valid:
                await promo_repo.use(promo)

        plan_enum = PlanType[plan_key]
        sub = await sub_repo.create_pending(
            telegram_id=user.id,
            user_id=db_user.id,
            plan=plan_enum,
            limit_ip=plan["limit_ip"],
        )

        # Создаём платёж в YooKassa
        try:
            payment_data = await yookassa.create_payment(
                amount=price,
                description=f"{config.BRAND_NAME} — {plan['name']} на {months} мес.",
                metadata={
                    "telegram_id": str(user.id),
                    "plan": plan_key,
                    "months": str(months),
                    "subscription_id": str(sub.id),
                    "promo_code": promo_code or "",
                },
                return_url=config.YOOKASSA_RETURN_URL,
            )
        except Exception as e:
            logger.error(f"YooKassa create payment error: {e}")
            await call.answer("❌ Ошибка создания платежа. Попробуй ещё раз.", show_alert=True)
            return

        # Сохраняем платёж
        await pay_repo.create(
            user_id=db_user.id,
            subscription_id=sub.id,
            amount=price,
            plan=plan_key,
            months=months,
            yookassa_id=payment_data["payment_id"],
            order_id=payment_data["order_id"],
            payment_url=payment_data["payment_url"],
        )

    text = f"""
💳 <b>Оплата</b>

📦 Тариф: <b>{plan['name']}</b>
⏱ Срок: <b>{months} мес.</b>
💰 Сумма: <b>{price} руб.</b>

Нажми кнопку ниже для оплаты.
После оплаты VPN ключ придёт автоматически в этот чат! 🔑

<i>⏱ Ссылка действительна 15 минут</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"💳 Оплатить {price} руб.",
            url=payment_data["payment_url"],
        )
    )
    builder.row(
        InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment:{payment_data['payment_id']}"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="plans"))

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def cb_check_payment(call: CallbackQuery):
    """Пользователь нажал 'Я оплатил' — проверяем статус"""
    payment_id = call.data.split(":")[1]

    try:
        status = await yookassa.check_payment_status(payment_id)
    except Exception as e:
        logger.error(f"Check payment error: {e}")
        await call.answer("❌ Ошибка проверки. Попробуй позже.", show_alert=True)
        return

    if status == "succeeded":
        await call.answer("✅ Оплата прошла! Выдаём ключ...")
        # Обработаем как webhook
        async with async_session() as session:
            pay_repo = PaymentRepo(session)
            payment = await pay_repo.get_by_yookassa_id(payment_id)
            if payment:
                await _process_successful_payment(
                    bot=call.bot,
                    payment_id=payment_id,
                    telegram_id=call.from_user.id,
                    plan=payment.plan,
                    months=payment.months,
                    amount=payment.amount,
                    subscription_id=payment.subscription_id,
                )
    elif status == "pending":
        await call.answer("⏳ Оплата ещё не прошла. Подожди или попробуй снова.", show_alert=True)
    else:
        await call.answer("❌ Оплата отменена или истекла.", show_alert=True)


async def _issue_free_trial(call: CallbackQuery, user):
    """Выдача бесплатного пробного периода"""
    async with async_session() as session:
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)

        db_user, _ = await user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

        # Проверяем — не использовал ли уже пробный
        existing = await sub_repo.get_all_for_user(user.id)
        has_trial = any(s.plan == PlanType.FREE for s in existing)

        if has_trial:
            await call.message.answer("❌ Пробный период уже был использован. Выбери платный тариф.")
            return

        sub = await sub_repo.create_pending(
            telegram_id=user.id,
            user_id=db_user.id,
            plan=PlanType.FREE,
            limit_ip=1,
        )

    await _create_vpn_and_notify(
        bot=call.bot,
        telegram_id=user.id,
        first_name=user.first_name or "User",
        last_name=user.last_name or "",
        sub_id_db=sub.id,
        months=0,
        days=3,
        plan_name="🆓 Пробный",
        amount=0,
    )


async def _process_successful_payment(
    bot: Bot, payment_id: str, telegram_id: int,
    plan: str, months: int, amount: float, subscription_id: int
):
    """Обработать успешный платёж: создать VPN + уведомить (идемпотентно)."""
    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)

        payment = await pay_repo.claim_payment(payment_id)
        if not payment:
            logger.info("Payment %s already processed or not found", payment_id)
            return

        if not subscription_id and payment.subscription_id:
            subscription_id = payment.subscription_id
        if not plan and payment.plan:
            plan = payment.plan
        if payment.months:
            months = payment.months

        user = await user_repo.get_by_telegram_id(telegram_id)
        sub = await sub_repo.get_by_id(subscription_id) if subscription_id else None
        if sub and sub.status == SubscriptionStatus.ACTIVE and sub.vpn_key:
            logger.info("Subscription %s already active with key", subscription_id)
            return

    plan_config = PLANS.get(plan, PLANS["BASIC"])
    await _create_vpn_and_notify(
        bot=bot,
        telegram_id=telegram_id,
        first_name=user.first_name or "User" if user else "User",
        last_name=user.last_name or "" if user else "",
        sub_id_db=subscription_id,
        months=months,
        days=0,
        plan_name=plan_config["name"],
        amount=amount,
    )

    if user and user.referrer_id:
        await process_referral_bonus(bot, user, payment_id=payment_id)

    try:
        user_name = user.full_name if user else f"User {telegram_id}"
        await bot.send_message(
            config.ADMIN_NOTIFY_ID,
            f"💰 <b>Новая оплата!</b>\n\n"
            f"👤 {user_name} (<code>{telegram_id}</code>)\n"
            f"📦 Тариф: {plan} / {months} мес.\n"
            f"💵 Сумма: {amount} руб.",
        )
    except Exception as e:
        logger.warning("Admin notify failed: %s", e)


async def _create_vpn_and_notify(
    bot: Bot, telegram_id: int, first_name: str, last_name: str,
    sub_id_db: int, months: int, days: int,
    plan_name: str, amount: float
):
    """Создать VPN клиента и отправить ключ пользователю"""
    plan_config = None
    inbound_id = list(config.XUI_INBOUND_IDS.values())[0]  # По умолчанию первый сервер

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        sub = await sub_repo.get_by_id(sub_id_db)
        if sub:
            plan_key = sub.plan.value if sub.plan else "BASIC"
            plan_config = PLANS.get(plan_key, PLANS["BASIC"])

    limit_ip = plan_config["limit_ip"] if plan_config else 3
    trial_days = PLANS.get("FREE", {}).get("days", 3) if days > 0 else 0
    xui_months = max(months, 1) if not trial_days else 1

    try:
        vpn_data = await xui.add_client(
            inbound_id=inbound_id,
            first_name=first_name,
            last_name=last_name,
            telegram_id=telegram_id,
            months=xui_months,
            limit_ip=limit_ip,
            traffic_gb=plan_config.get("traffic_gb", 0) if plan_config else 0,
        )

        # Строим ключ (vless sub-link)
        sub_url = xui.build_sub_url(vpn_data["sub_id"])

        # Сохраняем в БД
        async with async_session() as session:
            sub_repo = SubscriptionRepo(session)
            sub = await sub_repo.get_by_id(sub_id_db)
            if sub:
                await sub_repo.activate(
                    sub=sub,
                    months=months if months > 0 else 1,
                    vpn_uuid=vpn_data["uuid"],
                    vpn_email=vpn_data["email"],
                    vpn_sub_id=vpn_data["sub_id"],
                    vpn_key=sub_url,
                    inbound_id=inbound_id,
                    days=trial_days or days,
                )

        if trial_days or days > 0:
            period_text = f"{trial_days or days} дней"
        else:
            period_text = MONTHS_LABELS.get(months, f"{months} мес.")

        text = f"""
🎉 <b>VPN готов к работе!</b>

📦 Тариф: <b>{plan_name}</b>
⏱ Период: <b>{period_text}</b>
📱 Устройств: <b>{limit_ip}</b>

🔗 <b>Ссылка для подключения:</b>
<code>{sub_url}</code>

<b>Добавь ссылку в приложение:</b>
• 📱 Android: v2rayNG
• 🍎 iPhone: Happ или V2Box
• 💻 ПК: Nekoray

<i>Нажми на ссылку, чтобы скопировать 👆</i>
"""

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📖 Инструкции", callback_data="instructions"),
            InlineKeyboardButton(text="👤 Аккаунт", callback_data="account"),
        )
        builder.row(
            InlineKeyboardButton(text="❓ Поддержка", url=config.SUPPORT_URL)
        )

        await bot.send_message(telegram_id, text, reply_markup=builder.as_markup())
        logger.info(f"✅ VPN issued to {telegram_id}: {vpn_data['email']}")

    except Exception as e:
        logger.error(f"VPN creation error for {telegram_id}: {e}")
        await bot.send_message(
            telegram_id,
            "⚠️ <b>Ошибка создания VPN ключа.</b>\n\n"
            "Не переживай — мы уже знаем об этом и исправим в ближайшее время.\n"
            f"Напиши в поддержку: {config.SUPPORT_URL}",
        )


@router.message(F.web_app_data)
async def on_web_app_data(message: Message):
    """Fallback: покупка через tg.sendData из Mini App"""
    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        return

    if data.get("action") != "buy":
        return

    user = message.from_user
    if not user:
        return

    from bot.services.miniapp_purchase import process_miniapp_purchase

    try:
        result = await process_miniapp_purchase(
            telegram_id=user.id,
            plan=data.get("plan", "BASIC"),
            months=int(data.get("months", 1)),
            price=int(data.get("price", 0)),
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            bot=message.bot,
        )
    except Exception as e:
        logger.error("web_app_data purchase error: %s", e)
        await message.answer("❌ Не удалось оформить заказ. Попробуй ещё раз.")
        return

    if result.get("error"):
        await message.answer(f"❌ {result.get('message', 'Ошибка оформления')}")
        return

    if result.get("free_trial"):
        return

    payment_url = result.get("payment_url")
    if not payment_url:
        await message.answer("❌ Не удалось создать ссылку на оплату.")
        return

    price = int(data.get("price", 0))
    plan_key = data.get("plan", "BASIC")
    months = int(data.get("months", 1))
    plan = PLANS.get(plan_key, PLANS["BASIC"])

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"💳 Оплатить {price} руб.", url=payment_url))
    builder.row(
        InlineKeyboardButton(
            text="✅ Я оплатил",
            callback_data=f"check_payment:{result.get('payment_id')}",
        )
    )

    await message.answer(
        f"💳 <b>Оплата</b>\n\n"
        f"📦 Тариф: <b>{plan['name']}</b>\n"
        f"⏱ Срок: <b>{months} мес.</b>\n"
        f"💰 Сумма: <b>{price} руб.</b>\n\n"
        "После оплаты VPN ключ придёт автоматически в этот чат.",
        reply_markup=builder.as_markup(),
    )


# === Webhook от YooKassa ===

async def yookassa_webhook(request: Request) -> web.Response:
    """Webhook обработчик YooKassa платежей"""
    try:
        body = await request.json()
        logger.info("YooKassa webhook event: %s", body.get("event", "unknown"))

        event = parse_webhook_event(body)
        if not event:
            return web.Response(status=200)

        # Получаем бота из app
        bot: Bot = request.app["bot"]

        if not event.get("telegram_id"):
            logger.warning("Webhook without telegram_id in metadata")
            return web.Response(status=200)

        await _process_successful_payment(
            bot=bot,
            payment_id=event["payment_id"],
            telegram_id=int(event["telegram_id"]),
            plan=event.get("plan") or "BASIC",
            months=event.get("months", 1),
            amount=event.get("amount", 0),
            subscription_id=event.get("subscription_id", 0),
        )

        return web.Response(status=200)

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=200)  # Всегда 200, иначе YooKassa будет повторять
