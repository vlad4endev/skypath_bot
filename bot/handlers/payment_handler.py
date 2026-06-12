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
from database.repository import UserRepo, SubscriptionRepo, PaymentRepo
from database.models import PlanType, SubscriptionStatus
from bot.services.payment_processor import create_paid_order, process_manual_check, process_webhook
from bot.services.xui_client import XUIClient
from bot.handlers.referral_handler import process_referral_bonus

router = Router()
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


@router.callback_query(F.data.startswith("confirm_plan:"))
async def cb_confirm_plan(call: CallbackQuery):
    """Подтверждение тарифа из inline-меню бота."""
    parts = call.data.split(":")
    plan_key = parts[1]
    months = int(parts[2])
    price = int(parts[3])
    promo_code = None
    if len(parts) > 4 and parts[4].startswith("promo_"):
        promo_code = parts[4][6:]

    user = call.from_user
    if not user:
        await call.answer("Ошибка", show_alert=True)
        return

    if plan_key == "FREE" or price == 0:
        await _issue_free_trial(call, user)
        await call.answer()
        return

    plan = PLANS.get(plan_key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    try:
        order = await create_paid_order(
            telegram_id=user.id,
            plan_key=plan_key,
            months=months,
            price=price,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            promo_code=promo_code,
        )
    except Exception as e:
        logger.error("confirm_plan payment error: %s", e)
        await call.answer("Не удалось создать платёж", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"💳 Оплатить {price} руб.", url=order.payment_url),
    )
    builder.row(
        InlineKeyboardButton(
            text="✅ Я оплатил",
            callback_data=f"check_payment:{order.payment_id}",
        )
    )

    label = MONTHS_LABELS.get(months, f"{months} мес.")
    text = (
        f"💳 <b>Оплата</b>\n\n"
        f"📦 Тариф: <b>{plan['name']}</b>\n"
        f"⏱ Срок: <b>{label}</b>\n"
        f"💰 Сумма: <b>{price} руб.</b>\n\n"
        "После оплаты VPN ключ придёт автоматически в этот чат."
    )

    if call.message.photo:
        await call.message.edit_caption(caption=text, reply_markup=builder.as_markup())
    else:
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def cb_check_payment(call: CallbackQuery):
    """Пользователь нажал 'Я оплатил' — проверяем статус"""
    payment_ref = call.data.split(":")[1]

    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        payment = await pay_repo.get_by_payment_ref(payment_ref)

    if not payment:
        await call.answer("❌ Платёж не найден", show_alert=True)
        return

    try:
        status = await process_manual_check(call.bot, payment_ref, call.from_user.id)
    except Exception as e:
        logger.error("Check payment error: %s", e)
        await call.answer("❌ Ошибка проверки. Попробуй позже.", show_alert=True)
        return

    if status == "succeeded":
        await call.answer("✅ Оплата прошла! Выдаём ключ...")
    elif status == "pending":
        await call.answer("⏳ Оплата ещё не прошла. Подожди или попробуй снова.", show_alert=True)
    elif status == "cancelled":
        await call.answer("❌ Оплата отменена или истекла.", show_alert=True)
    else:
        await call.answer("❌ Платёж не найден", show_alert=True)


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
            limit_ip=PLANS["FREE"]["limit_ip"],
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


async def _disable_trial_vpn_for_user(telegram_id: int, exclude_sub_id: int | None = None) -> None:
    """Отключить пробные VPN-клиенты после оплаты платного тарифа."""
    from database.models import PlanType

    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        subs = await sub_repo.get_all_for_user(telegram_id)

    for sub in subs:
        if sub.id == exclude_sub_id or sub.plan != PlanType.FREE:
            continue
        if sub.status not in (SubscriptionStatus.FREE_TRIAL, SubscriptionStatus.ACTIVE):
            continue
        if not (sub.vpn_uuid and sub.vpn_email and sub.vpn_sub_id and sub.inbound_id):
            continue
        try:
            await xui.disable_client(
                inbound_id=sub.inbound_id,
                client_uuid=sub.vpn_uuid,
                email=sub.vpn_email,
                sub_id=sub.vpn_sub_id,
                telegram_id=sub.telegram_id,
                limit_ip=sub.limit_ip,
            )
        except Exception as e:
            logger.warning("Failed to disable trial VPN %s: %s", sub.id, e)

        async with async_session() as session:
            sub_repo = SubscriptionRepo(session)
            s = await sub_repo.get_by_id(sub.id)
            if s:
                await sub_repo.expire(s)
                await sub_repo.mark_vpn_disabled(s)


async def _process_successful_payment(
    bot: Bot, payment_id: str, telegram_id: int,
    plan: str, months: int, amount: float, subscription_id: int,
    payment_db_id: int | None = None,
):
    """Обработать успешный платёж: создать VPN + уведомить (идемпотентно)."""
    await _disable_trial_vpn_for_user(telegram_id, exclude_sub_id=subscription_id)

    async with async_session() as session:
        pay_repo = PaymentRepo(session)
        user_repo = UserRepo(session)
        sub_repo = SubscriptionRepo(session)

        payment = None
        if payment_db_id:
            payment = await pay_repo.get_by_id(payment_db_id)
        if not payment:
            payment = await pay_repo.get_by_payment_ref(payment_id)

        if not payment:
            logger.info("Payment %s not found for fulfillment", payment_id)
            return

        if payment.fulfilled_at:
            logger.info("Payment %s already fulfilled", payment.id)
            return

        if not subscription_id and payment.subscription_id:
            subscription_id = payment.subscription_id
        if not plan and payment.plan:
            plan = payment.plan
        if payment.months:
            months = payment.months
        if not amount and payment.paid_amount:
            amount = payment.paid_amount
        elif not amount:
            amount = payment.amount

        user = await user_repo.get_by_telegram_id(telegram_id)
        sub = await sub_repo.get_by_id(subscription_id) if subscription_id else None
        if (
            sub
            and sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.FREE_TRIAL)
            and sub.vpn_key
            and sub.plan != PlanType.FREE
        ):
            await pay_repo.mark_fulfilled(payment)
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
        order_id=payment.order_id if payment else None,
        payment_db_id=payment.id if payment else None,
    )

    if user and user.referrer_id:
        await process_referral_bonus(bot, user, payment_id=payment_id)

    try:
        user_name = user.full_name if user else f"User {telegram_id}"
        paid_str = f"{payment.paid_amount or amount:.0f}" if payment else f"{amount:.0f}"
        admin_text = (
            f"💰 <b>Новая оплата!</b>\n\n"
            f"👤 {user_name} (<code>{telegram_id}</code>)\n"
            f"🧾 Заказ: <code>{payment.order_id if payment else payment_id}</code>\n"
            f"📦 Тариф: {plan} / {months} мес.\n"
            f"💵 Сумма: {paid_str} руб."
        )
        if payment and payment.provider_status:
            admin_text += f"\n📡 Platega: {payment.provider_status}"
        await bot.send_message(config.ADMIN_NOTIFY_ID, admin_text)
    except Exception as e:
        logger.warning("Admin notify failed: %s", e)


async def _create_vpn_and_notify(
    bot: Bot, telegram_id: int, first_name: str, last_name: str,
    sub_id_db: int, months: int, days: int,
    plan_name: str, amount: float,
    order_id: str | None = None,
    payment_db_id: int | None = None,
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

    sub = None
    is_trial = days > 0
    if is_trial:
        free_cfg = PLANS["FREE"]
        limit_ip = free_cfg["limit_ip"]
        traffic_gb = free_cfg["traffic_gb"]
        trial_days = free_cfg["days"]
        xui_months = 0
    else:
        limit_ip = plan_config["limit_ip"] if plan_config else 3
        traffic_gb = plan_config.get("traffic_gb", 0) if plan_config else 0
        trial_days = 0
        xui_months = max(months, 1)

    try:
        vpn_data = await xui.add_client(
            inbound_id=inbound_id,
            first_name=first_name,
            last_name=last_name,
            telegram_id=telegram_id,
            months=xui_months,
            limit_ip=limit_ip,
            traffic_gb=traffic_gb,
            days=trial_days,
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
                    traffic_gb=traffic_gb if is_trial else 0,
                )

        if trial_days or days > 0:
            period_text = f"{trial_days or days} дней"
        else:
            period_text = MONTHS_LABELS.get(months, f"{months} мес.")

        trial_notice = ""
        if is_trial:
            trial_notice = (
                f"\n\n💡 <b>Пробный период — {trial_days or days} дня.</b>\n"
                "После окончания доступ закроется, если не оформить подписку.\n"
                "Нажми «Купить подписку» — от 250 ₽/мес."
            )

        receipt_block = ""
        expires_str = ""
        if sub and sub.expires_at:
            expires_str = sub.expires_at.strftime("%d.%m.%Y")
        if not is_trial and amount > 0:
            receipt_block = (
                f"\n━━━━━━━━━━━━━━━━━\n"
                f"🧾 <b>Чек оплаты</b>\n"
                f"Заказ: <code>{order_id or '—'}</code>\n"
                f"Сумма: <b>{amount:.0f} ₽</b>\n"
                f"Период: <b>{period_text}</b>\n"
                f"Действует до: <b>{expires_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━\n"
            )

        text = f"""
🎉 <b>VPN готов к работе!</b>

📦 Тариф: <b>{plan_name}</b>
⏱ Период: <b>{period_text}</b>
📱 Устройств: <b>{limit_ip}</b>
{"📊 Трафик: <b>" + str(traffic_gb) + " ГБ</b>" if is_trial and traffic_gb else ""}
{receipt_block}
🔗 <b>Ссылка для подключения:</b>
<code>{sub_url}</code>

<b>Добавь ссылку в приложение:</b>
• 📱 Android: v2rayNG
• 🍎 iPhone: Happ или V2Box
• 💻 ПК: Nekoray

<i>Нажми на ссылку, чтобы скопировать 👆</i>{trial_notice}
"""

        from bot.keyboards.webapp import cabinet_button, is_miniapp_available

        builder = InlineKeyboardBuilder()
        if is_trial and is_miniapp_available():
            builder.row(cabinet_button("💳 Купить подписку"))
        builder.row(
            InlineKeyboardButton(text="📖 Инструкции", callback_data="instructions"),
            InlineKeyboardButton(text="👤 Аккаунт", callback_data="account"),
        )
        builder.row(
            InlineKeyboardButton(text="❓ Поддержка", url=config.SUPPORT_URL)
        )

        await bot.send_message(telegram_id, text, reply_markup=builder.as_markup())
        logger.info("VPN issued to %s: %s", telegram_id, vpn_data["email"])

        if payment_db_id:
            async with async_session() as session:
                pay_repo = PaymentRepo(session)
                payment = await pay_repo.get_by_id(payment_db_id)
                if payment:
                    await pay_repo.mark_fulfilled(payment)

    except Exception as e:
        logger.exception("VPN creation error for %s (inbound=%s): %s", telegram_id, inbound_id, e)
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


# === Webhook от Platega ===

async def platega_webhook(request: Request) -> web.Response:
    """Webhook обработчик Platega платежей"""
    try:
        body = await request.json()
        bot: Bot = request.app["bot"]
        result = await process_webhook(body, bot)
        return web.json_response(result)
    except Exception as e:
        logger.error("Platega webhook error: %s", e)
        return web.json_response({"error": "processing failed"}, status=500)
