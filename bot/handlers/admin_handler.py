"""
Админ панель — статистика, рассылки, управление
"""
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, and_

from bot.config import Config
from database.engine import async_session
from database.repository import UserRepo, SubscriptionRepo
from database.models import User, Subscription, Payment, SubscriptionStatus, PaymentStatus

router = Router()
logger = logging.getLogger(__name__)
config = Config()


def admin_only(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class BroadcastStates(StatesGroup):
    waiting_text = State()
    confirm = State()


async def _build_stats_text() -> str:
    async with async_session() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar()
        active_subs = (await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.ACTIVE
            )
        )).scalar()
        yesterday = datetime.utcnow() - timedelta(days=1)
        new_users = (await session.execute(
            select(func.count(User.id)).where(User.created_at >= yesterday)
        )).scalar()
        month_ago = datetime.utcnow() - timedelta(days=30)
        revenue = (await session.execute(
            select(func.sum(Payment.amount)).where(
                and_(Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= month_ago)
            )
        )).scalar() or 0
        tomorrow = datetime.utcnow() + timedelta(days=1)
        day_after = datetime.utcnow() + timedelta(days=2)
        expiring = (await session.execute(
            select(func.count(Subscription.id)).where(
                and_(
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.expires_at >= tomorrow,
                    Subscription.expires_at < day_after,
                )
            )
        )).scalar()

    return f"""
📊 <b>Статистика SkyPath VPN</b>

👥 Всего пользователей: <b>{total_users}</b>
🆕 Новых за 24ч: <b>{new_users}</b>
✅ Активных подписок: <b>{active_subs}</b>
⚠️ Истекают завтра: <b>{expiring}</b>

💰 <b>Выручка за 30 дней:</b> {revenue:.0f} руб.

📅 <i>Обновлено: {datetime.now().strftime("%d.%m.%Y %H:%M")}</i>
"""


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not admin_only(message.from_user.id):
        return
    await message.answer(await _build_stats_text())


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not admin_only(message.from_user.id):
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="💰 Платежи", callback_data="admin_payments"),
    )
    builder.row(
        InlineKeyboardButton(text="🔑 Промокоды", callback_data="admin_promos"),
    )

    await message.answer(
        "👨‍💼 <b>Панель администратора</b>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    text = await _build_stats_text()

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main"),
    )

    await call.message.edit_text(text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    async with async_session() as session:
        total = (await session.execute(select(func.count(User.id)))).scalar()
    await call.message.edit_text(
        f"👥 <b>Пользователи</b>\n\nВсего в базе: <b>{total}</b>\n\n"
        f"<i>Детальный список — в PostgreSQL / админ-инструментах.</i>",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
        ).as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "admin_payments")
async def cb_admin_payments(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    async with async_session() as session:
        month_ago = datetime.utcnow() - timedelta(days=30)
        count = (await session.execute(
            select(func.count(Payment.id)).where(
                and_(Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= month_ago)
            )
        )).scalar()
        revenue = (await session.execute(
            select(func.sum(Payment.amount)).where(
                and_(Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= month_ago)
            )
        )).scalar() or 0
    await call.message.edit_text(
        f"💰 <b>Платежи за 30 дней</b>\n\n"
        f"Транзакций: <b>{count}</b>\n"
        f"Сумма: <b>{revenue:.0f} руб.</b>",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
        ).as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "admin_promos")
async def cb_admin_promos(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        "🔑 <b>Промокоды</b>\n\n"
        "Создавай коды в таблице <code>promo_codes</code> (PostgreSQL) "
        "или через SQL:\n"
        "<code>INSERT INTO promo_codes (code, discount_pct, max_uses) "
        "VALUES ('SKY10', 10, 100);</code>",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")
        ).as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not admin_only(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    await state.set_state(BroadcastStates.waiting_text)
    await call.message.edit_text(
        "📢 <b>Рассылка</b>\n\nОтправь текст сообщения.\nПоддерживается HTML-разметка."
    )
    await call.answer()


@router.message(BroadcastStates.waiting_text)
async def handle_broadcast_text(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    await state.update_data(broadcast_text=message.text or message.caption or "")
    await state.set_state(BroadcastStates.confirm)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast_confirm:all"),
        InlineKeyboardButton(text="✅ Только активным", callback_data="broadcast_confirm:active"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")
    )

    await message.answer(
        f"<b>Превью:</b>\n\n{message.text}\n\n<b>Кому отправить?</b>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("broadcast_confirm:"))
async def cb_broadcast_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not admin_only(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    target = call.data.split(":")[1]
    data = await state.get_data()
    text = data.get("broadcast_text", "")

    await state.clear()
    await call.message.edit_text("📤 Рассылка запущена...")

    async with async_session() as session:
        if target == "active":
            result = await session.execute(
                select(Subscription.telegram_id).where(
                    Subscription.status == SubscriptionStatus.ACTIVE
                ).distinct()
            )
            ids = [r[0] for r in result.all()]
        else:
            user_repo = UserRepo(session)
            ids = await user_repo.get_all_ids()

    sent = 0
    failed = 0
    for uid in ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await call.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )


@router.callback_query(F.data == "broadcast_cancel")
async def cb_broadcast_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Рассылка отменена")
    await call.answer()


@router.callback_query(F.data == "admin_main")
async def cb_admin_main(call: CallbackQuery):
    if not admin_only(call.from_user.id):
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="💰 Платежи", callback_data="admin_payments"),
    )

    await call.message.edit_text(
        "👨‍💼 <b>Панель администратора</b>",
        reply_markup=builder.as_markup(),
    )
    await call.answer()
