"""
Выбор тарифа и срока подписки
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.config import Config, PLANS, MONTHS_LABELS
from bot.services.discount_service import calculate_discount
from database.engine import async_session
from database.repository import SubscriptionRepo, UserRepo

router = Router()
logger = logging.getLogger(__name__)
config = Config()


class SubscriptionStates(StatesGroup):
    waiting_promo = State()


def plans_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for plan_key, plan in PLANS.items():
        if plan_key == "FREE":
            builder.row(
                InlineKeyboardButton(
                    text=f"{plan['name']} — Бесплатно 3 дня",
                    callback_data=f"select_plan:{plan_key}",
                )
            )
        else:
            from_price = min(plan["prices"].values())
            builder.row(
                InlineKeyboardButton(
                    text=f"{plan['name']} — от {from_price} руб/мес",
                    callback_data=f"select_plan:{plan_key}",
                )
            )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main"))
    return builder


@router.callback_query(F.data == "plans")
async def cb_plans(call: CallbackQuery):
    async with async_session() as session:
        sub_repo = SubscriptionRepo(session)
        active_sub = await sub_repo.get_active(call.from_user.id)

    text = "📦 <b>Выбери тариф</b>\n\n"

    if active_sub:
        expires = active_sub.expires_at.strftime("%d.%m.%Y") if active_sub.expires_at else "?"
        text += f"✅ Текущая подписка: <b>{active_sub.plan.value}</b> до {expires}\n\n"

    for plan_key, plan in PLANS.items():
        if plan_key == "FREE":
            text += f"{plan['name']}\n"
            text += f"   {plan['description']}\n\n"
        else:
            prices_str = " / ".join(
                f"{m}м={p}₽" for m, p in list(plan["prices"].items())[:3]
            )
            text += f"{plan['name']}\n"
            text += f"   {plan['description']}\n"
            text += f"   💰 {prices_str} ...\n\n"

    builder = plans_keyboard()

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("select_plan:"))
async def cb_select_plan(call: CallbackQuery):
    plan_key = call.data.split(":")[1]
    plan = PLANS.get(plan_key)

    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    if plan_key == "FREE":
        # Бесплатный период — сразу к оплате (без оплаты, но к подтверждению)
        text = f"""
🎁 <b>Пробный период — 3 дня бесплатно</b>

✅ 1 устройство
✅ 5 ГБ трафика
✅ Все серверы

<b>Это бесплатно — подтверди и получи ключ прямо сейчас!</b>
"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Получить бесплатно",
                callback_data=f"confirm_plan:{plan_key}:0:0",
            )
        )
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="plans"))
        await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
            if call.message.photo else \
            await call.message.edit_text(text=text, reply_markup=builder.as_markup())
        await call.answer()
        return

    # Платные тарифы — выбор срока
    text = f"💎 <b>{plan['name']}</b>\n\n{plan['description']}\n\n⏱ <b>Выбери срок:</b>\n"

    builder = InlineKeyboardBuilder()
    for months, price in plan["prices"].items():
        label = MONTHS_LABELS.get(months, f"{months} мес.")
        discount = ""
        if months >= 6:
            # Подсветим экономию
            regular = plan["prices"][1] * months
            save = regular - price
            discount = f" (экономия {save}₽)"
        builder.row(
            InlineKeyboardButton(
                text=f"{label} — {price}₽{discount}",
                callback_data=f"select_months:{plan_key}:{months}:{price}",
            )
        )

    builder.row(
        InlineKeyboardButton(text="🏷 Промокод", callback_data=f"promo:{plan_key}"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="plans"),
    )

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("select_months:"))
async def cb_select_months(call: CallbackQuery):
    _, plan_key, months_str, price_str = call.data.split(":")
    months = int(months_str)
    price = int(price_str)
    plan = PLANS.get(plan_key)

    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    label = MONTHS_LABELS.get(months, f"{months} мес.")

    text = f"""
💳 <b>Подтверди покупку</b>

📦 Тариф: <b>{plan['name']}</b>
⏱ Срок: <b>{label}</b>
💰 Сумма: <b>{price} руб.</b>
📱 Устройств: <b>{plan['limit_ip']}</b>

<i>После оплаты VPN ключ будет выдан автоматически</i>
"""

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"💳 Оплатить {price} руб.",
            callback_data=f"confirm_plan:{plan_key}:{months}:{price}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="🏷 Промокод", callback_data=f"promo:{plan_key}:{months}:{price}"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"select_plan:{plan_key}"),
    )

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("promo:"))
async def cb_promo_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    plan_key = parts[1]
    months = parts[2] if len(parts) > 2 else "1"
    price = parts[3] if len(parts) > 3 else "0"

    await state.set_state(SubscriptionStates.waiting_promo)
    await state.update_data(plan_key=plan_key, months=months, price=price)

    text = "🏷 <b>Введи промокод:</b>\n\nОтправь промокод в чат или нажми отмену"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=f"select_months:{plan_key}:{months}:{price}",
        )
    )

    await call.message.edit_caption(caption=text, reply_markup=builder.as_markup()) \
        if call.message.photo else \
        await call.message.edit_text(text=text, reply_markup=builder.as_markup())
    await call.answer()


@router.message(SubscriptionStates.waiting_promo)
async def handle_promo_input(message: Message, state: FSMContext):
    promo_code = message.text.strip().upper()
    data = await state.get_data()
    plan_key = data["plan_key"]
    months = int(data["months"])
    price = int(data["price"])

    async with async_session() as session:
        user_repo = UserRepo(session)
        db_user, is_new_user = await user_repo.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        discount = await calculate_discount(
            session,
            telegram_id=message.from_user.id,
            user_id=db_user.id,
            plan_key=plan_key,
            months=months,
            promo_code=promo_code,
            is_new_user=is_new_user,
        )

    builder = InlineKeyboardBuilder()

    if not discount.ok:
        text = f"❌ {discount.error or 'Промокод недействителен'}\n\n"
        text += "Продолжить без промокода?"
        builder.row(
            InlineKeyboardButton(
                text=f"💳 Оплатить без скидки ({price} руб.)",
                callback_data=f"confirm_plan:{plan_key}:{months}:{price}",
            )
        )
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"select_plan:{plan_key}"))
    else:
        new_price = discount.final_price
        discount_text = discount.discount_label or f"−{discount.discount_total}₽"
        promo_suffix = f":promo_{discount.promo_code}" if discount.promo_code else ""

        text = f"""
✅ Скидка применена!

💰 Цена: ~~{discount.base_price}~~ → <b>{new_price} руб.</b>
🎁 {discount_text}
"""
        builder.row(
            InlineKeyboardButton(
                text=f"💳 Оплатить {new_price} руб.",
                callback_data=f"confirm_plan:{plan_key}:{months}:{new_price}{promo_suffix}",
            )
        )
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"select_plan:{plan_key}"))

    await state.clear()
    await message.answer(text, reply_markup=builder.as_markup())
