import { Composer } from "grammy";
import type { BotContext, BotDependencies } from "../context.js";
import { plansKeyboard, paymentKeyboard, backToMainKeyboard } from "../keyboards.js";
import { prisma } from "../../db.js";
import {
  buildSubLink,
  getOrCreateUser,
  createPendingPayment,
} from "../../shared/subscriptionService.js";
import { getPrice } from "../../shared/pricing.js";

export function createPaymentHandlers(deps: BotDependencies): Composer<BotContext> {
  const composer = new Composer<BotContext>();

  composer.callbackQuery("pay:plans", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.editMessageText(
      "💳 <b>Выберите срок подписки:</b>",
      {
        parse_mode: "HTML",
        reply_markup: plansKeyboard(),
      },
    );
  });

  composer.callbackQuery(/^pay:month:(\d+)$/, async (ctx) => {
    await ctx.answerCallbackQuery();
    const from = ctx.from;
    if (!from) return;

    const months = Number(ctx.match[1]);
    const price = getPrice(months);
    if (price === undefined) {
      await ctx.editMessageText("❌ Неверный период", {
        reply_markup: backToMainKeyboard(),
      });
      return;
    }

    const user = await getOrCreateUser(BigInt(from.id), {
      username: from.username,
      firstName: from.first_name,
      lastName: from.last_name,
    });

    try {
      const { amount, subscription } = await createPendingPayment(user.id, months);

      const invoice = await deps.platega.createInvoice({
        userId: user.id,
        months,
        amount,
        description: `VPN подписка на ${months} мес.`,
      });

      await prisma.payment.create({
        data: {
          userId: user.id,
          subscriptionId: subscription.id,
          orderId: invoice.orderId,
          months,
          amount,
          paymentUrl: invoice.paymentUrl,
          status: "PENDING",
        },
      });

      ctx.session.pendingOrderId = invoice.orderId;

      await ctx.editMessageText(
        `
💳 <b>Оплата подписки</b>

<b>Период:</b> ${months} мес.
<b>Сумма:</b> ${amount} ₽

Нажмите «Оплатить», затем «Проверить оплату».
`.trim(),
        {
          parse_mode: "HTML",
          reply_markup: paymentKeyboard(invoice.paymentUrl, invoice.orderId),
        },
      );
    } catch (error) {
      console.error("Payment creation failed:", error);
      await ctx.editMessageText("❌ Не удалось создать счёт. Попробуйте позже.", {
        reply_markup: backToMainKeyboard(),
      });
    }
  });

  composer.callbackQuery(/^pay:check:(.+)$/, async (ctx) => {
    await ctx.answerCallbackQuery({ text: "Проверяем оплату…" });
    const orderId = ctx.match[1];
    if (!orderId) return;

    const payment = await prisma.payment.findUnique({ where: { orderId } });
    if (!payment) {
      await ctx.reply("❌ Платёж не найден");
      return;
    }

    if (payment.status === "PAID") {
      await showPaidMessage(ctx, deps, orderId);
      return;
    }

    await ctx.reply(
      "⏳ Оплата ещё не подтверждена. Если вы уже оплатили — подождите минуту и нажмите снова.",
      { reply_markup: paymentKeyboard(payment.paymentUrl ?? "", orderId) },
    );
  });

  return composer;
}

async function showPaidMessage(
  ctx: BotContext,
  deps: BotDependencies,
  orderId: string,
): Promise<void> {
  const payment = await prisma.payment.findUnique({
    where: { orderId },
    include: { subscription: true },
  });

  const subId = payment?.subscription?.subId;
  if (!subId) {
    await ctx.reply("✅ Оплата подтверждена. Ссылка появится в разделе «Моя подписка» через минуту.");
    return;
  }

  const subLink = buildSubLink(deps.env, subId);
  await ctx.reply(
    `
✅ <b>Оплата подтверждена!</b>

<b>Ссылка для подключения:</b>
<code>${subLink}</code>

Скопируйте ссылку и добавьте в VPN-приложение.
`.trim(),
    { parse_mode: "HTML" },
  );
}
