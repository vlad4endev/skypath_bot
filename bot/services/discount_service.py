"""
Расчёт скидок: акции (авто) + промокоды (ввод пользователя).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot.config import PLANS
from database.models import PromoCode, Promotion

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DiscountResult:
    base_price: int
    final_price: int
    discount_total: int
    promotion_id: int | None = None
    promotion_name: str | None = None
    promo_code: str | None = None
    promo_code_id: int | None = None
    discount_label: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _apply_discount(base: int, pct: int, amount: int) -> int:
    price = base
    if pct:
        price = int(price * (1 - pct / 100))
    if amount:
        price = max(1, price - amount)
    return max(1, price)


def _discount_savings(base: int, pct: int, amount: int) -> int:
    return base - _apply_discount(base, pct, amount)


def _matches_list(restrictions: list | None, value: str | int) -> bool:
    if not restrictions:
        return True
    normalized = [str(v) for v in restrictions]
    return str(value) in normalized


def _promotion_matches(promo: Promotion, *, plan_key: str, months: int, base_price: int) -> bool:
    if not promo.is_valid:
        return False
    if not _matches_list(promo.plans, plan_key):
        return False
    if not _matches_list(promo.months, months):
        return False
    if promo.min_amount and base_price < promo.min_amount:
        return False
    return True


def _is_personal_promo(promo: PromoCode, telegram_id: int) -> bool:
    if promo.assigned_telegram_id is None:
        return False
    return int(promo.assigned_telegram_id) == int(telegram_id)


def _promo_code_error(
    promo: PromoCode,
    *,
    plan_key: str,
    months: int,
    base_price: int,
) -> str | None:
    """Код ошибки или None, если промокод подходит к заказу."""
    from datetime import datetime

    if not promo.is_active:
        return "promo_invalid"
    if promo.max_uses and promo.uses_count >= promo.max_uses:
        return "promo_already_used"
    if promo.expires_at and promo.expires_at < datetime.utcnow():
        return "promo_expired"
    if not _matches_list(promo.plans, plan_key):
        return "promo_plan_mismatch"
    if not _matches_list(promo.months, months):
        return "promo_plan_mismatch"
    if promo.min_amount and base_price < promo.min_amount:
        return "promo_plan_mismatch"
    return None


def _format_discount(pct: int, amount: int) -> str:
    if pct and amount:
        return f"{pct}% + {amount}₽"
    if pct:
        return f"{pct}%"
    if amount:
        return f"{amount}₽"
    return "0%"


async def calculate_discount(
    session: AsyncSession,
    *,
    telegram_id: int,
    user_id: int,
    plan_key: str,
    months: int,
    promo_code: str | None = None,
    is_new_user: bool = False,
    locale: str | None = None,
) -> DiscountResult:
    """Рассчитать итоговую цену с учётом акций и промокода."""
    from bot.i18n.api_messages import api_msg
    from database.repository import PromotionRepo, PromoRepo

    def _label(key: str, **kwargs: str) -> str:
        return api_msg(locale or "ru", key, **kwargs)

    plan = PLANS.get(plan_key)
    if not plan or plan_key == "FREE":
        return DiscountResult(base_price=0, final_price=0, discount_total=0, error="invalid_plan")

    prices = plan.get("prices", {})
    if months not in prices:
        return DiscountResult(
            base_price=0,
            final_price=0,
            discount_total=0,
            error="invalid_months",
        )

    base_price = int(prices[months])
    promo_repo = PromoRepo(session)
    promotion_repo = PromotionRepo(session)

    promotions = await promotion_repo.list_active()
    best_promotion: Promotion | None = None
    best_promo_savings = 0

    for promotion in promotions:
        if promotion.new_users_only and not is_new_user:
            continue
        if not _promotion_matches(promotion, plan_key=plan_key, months=months, base_price=base_price):
            continue
        savings = _discount_savings(
            base_price, promotion.discount_pct, promotion.discount_amount
        )
        if best_promotion is None or savings > best_promo_savings or (
            savings == best_promo_savings and promotion.priority > best_promotion.priority
        ):
            best_promo_savings = savings
            best_promotion = promotion

    promo_price = base_price
    promo_obj: PromoCode | None = None
    promo_error: str | None = None

    if promo_code:
        promo_obj = await promo_repo.get_by_code(promo_code.strip())
        if not promo_obj:
            promo_error = "promo_not_found"
        elif promo_err := _promo_code_error(
            promo_obj, plan_key=plan_key, months=months, base_price=base_price
        ):
            promo_error = promo_err
        elif promo_obj.one_per_user and await promo_repo.user_has_used(promo_obj.id, user_id):
            promo_error = "promo_already_used"
        elif promo_obj.assigned_telegram_id is not None and not _is_personal_promo(
            promo_obj, telegram_id
        ):
            promo_error = "promo_assigned_other"
        else:
            promo_price = _apply_discount(
                base_price, promo_obj.discount_pct, promo_obj.discount_amount
            )

    promotion_price = base_price
    if best_promotion:
        promotion_price = _apply_discount(
            base_price, best_promotion.discount_pct, best_promotion.discount_amount
        )

    final_price = base_price
    applied_promotion: Promotion | None = None
    applied_promo: PromoCode | None = None
    label_parts: list[str] = []

    if promo_error:
        return DiscountResult(
            base_price=base_price,
            final_price=base_price,
            discount_total=0,
            error=promo_error,
        )

    if best_promotion and promo_obj:
        if best_promotion.stackable_with_promo:
            stacked = _apply_discount(
                promotion_price,
                promo_obj.discount_pct,
                promo_obj.discount_amount,
            )
            final_price = stacked
            applied_promotion = best_promotion
            applied_promo = promo_obj
            label_parts.append(_label("promotion_label", name=best_promotion.name))
            label_parts.append(_label("promo_code_label", code=promo_obj.code))
        elif _is_personal_promo(promo_obj, telegram_id):
            # Персональный промокод всегда применяется, если пользователь его ввёл.
            final_price = promo_price
            applied_promo = promo_obj
            label_parts.append(_label("promo_code_label", code=promo_obj.code))
        else:
            promo_savings = base_price - promo_price
            if promo_savings >= best_promo_savings:
                final_price = promo_price
                applied_promo = promo_obj
                label_parts.append(_label("promo_code_label", code=promo_obj.code))
            else:
                final_price = promotion_price
                applied_promotion = best_promotion
                label_parts.append(_label("promotion_label", name=best_promotion.name))
    elif promo_obj:
        final_price = promo_price
        applied_promo = promo_obj
        label_parts.append(_label("promo_code_label", code=promo_obj.code))
    elif best_promotion:
        final_price = promotion_price
        applied_promotion = best_promotion
        label_parts.append(_label("promotion_label", name=best_promotion.name))

    discount_total = base_price - final_price
    discount_label = None
    if label_parts:
        discount_label = " + ".join(label_parts)

    return DiscountResult(
        base_price=base_price,
        final_price=final_price,
        discount_total=discount_total,
        promotion_id=applied_promotion.id if applied_promotion else None,
        promotion_name=applied_promotion.name if applied_promotion else None,
        promo_code=applied_promo.code if applied_promo else None,
        promo_code_id=applied_promo.id if applied_promo else None,
        discount_label=discount_label,
    )


async def preview_discounts_for_plan(
    session: AsyncSession,
    *,
    telegram_id: int,
    user_id: int,
    plan_key: str,
    is_new_user: bool = False,
    locale: str | None = None,
) -> dict:
    """Предпросмотр цен по всем срокам тарифа (для Mini App)."""
    plan = PLANS.get(plan_key)
    if not plan or plan_key == "FREE":
        return {"plan": plan_key, "months": {}}

    months_prices: dict[str, dict] = {}
    for months in plan.get("prices", {}):
        result = await calculate_discount(
            session,
            telegram_id=telegram_id,
            user_id=user_id,
            plan_key=plan_key,
            months=int(months),
            is_new_user=is_new_user,
            locale=locale,
        )
        months_prices[str(months)] = {
            "base_price": result.base_price,
            "final_price": result.final_price,
            "discount_total": result.discount_total,
            "promotion_name": result.promotion_name,
            "discount_label": result.discount_label,
        }

    return {"plan": plan_key, "months": months_prices}
