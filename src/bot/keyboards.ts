import { InlineKeyboard } from "grammy";
import { AVAILABLE_MONTHS, formatPrice } from "../shared/pricing.js";

export function mainMenuKeyboard(): InlineKeyboard {
  return new InlineKeyboard()
    .text("🔑 Моя подписка", "sub:view")
    .text("👤 Аккаунт", "account:view")
    .row()
    .text("💳 Купить подписку", "pay:plans")
    .text("🆓 Пробный период", "sub:trial")
    .row()
    .text("📱 Приложения", "info:apps")
    .text("ℹ️ О сервисе", "info:about");
}

export function backToMainKeyboard(): InlineKeyboard {
  return new InlineKeyboard().text("◀️ Назад", "menu:main");
}

export function plansKeyboard(): InlineKeyboard {
  const kb = new InlineKeyboard();
  for (let i = 0; i < AVAILABLE_MONTHS.length; i += 2) {
    const left = AVAILABLE_MONTHS[i];
    const right = AVAILABLE_MONTHS[i + 1];
    if (left !== undefined) {
      kb.text(formatPrice(left), `pay:month:${left}`);
    }
    if (right !== undefined) {
      kb.text(formatPrice(right), `pay:month:${right}`);
    }
    kb.row();
  }
  kb.text("◀️ Назад", "menu:main");
  return kb;
}

export function paymentKeyboard(paymentUrl: string, orderId: string): InlineKeyboard {
  return new InlineKeyboard()
    .url("💳 Оплатить", paymentUrl)
    .row()
    .text("✅ Проверить оплату", `pay:check:${orderId}`)
    .row()
    .text("◀️ Назад", "pay:plans");
}

export function subscriptionKeyboard(): InlineKeyboard {
  return new InlineKeyboard()
    .text("🔄 Продлить", "pay:plans")
    .row()
    .text("◀️ Назад", "menu:main");
}
