import { Composer } from "grammy";
import type { BotContext, BotDependencies } from "../context.js";
import { subscriptionKeyboard, backToMainKeyboard } from "../keyboards.js";
import {
  activateTrial,
  buildSubLink,
  formatStatus,
  getLatestSubscription,
  getOrCreateUser,
} from "../../shared/subscriptionService.js";

export function createSubscriptionHandlers(deps: BotDependencies): Composer<BotContext> {
  const composer = new Composer<BotContext>();

  composer.callbackQuery("sub:view", async (ctx) => {
    await ctx.answerCallbackQuery();
    const from = ctx.from;
    if (!from) return;

    const user = await getOrCreateUser(BigInt(from.id), {
      username: from.username,
      firstName: from.first_name,
      lastName: from.last_name,
    });

    const sub = await getLatestSubscription(user.id);

    if (!sub || !sub.subId) {
      await ctx.editMessageText(
        "У вас пока нет подписки.\n\nОформите пробный период или купите подписку.",
        { reply_markup: backToMainKeyboard() },
      );
      return;
    }

    const expires = sub.expiresAt
      ? sub.expiresAt.toLocaleString("ru-RU", { timeZone: "UTC" }) + " UTC"
      : "—";
    const subLink = buildSubLink(deps.env, sub.subId);

    const text = `
🔑 <b>Моя подписка</b>

<b>Статус:</b> ${formatStatus(sub.status)}
<b>Окончание:</b> ${expires}
<b>Ссылка для подключения:</b>
<code>${subLink}</code>
`.trim();

    await ctx.editMessageText(text, {
      parse_mode: "HTML",
      reply_markup: subscriptionKeyboard(),
    });
  });

  composer.callbackQuery("sub:trial", async (ctx) => {
    await ctx.answerCallbackQuery();
    const from = ctx.from;
    if (!from) return;

    try {
      const user = await getOrCreateUser(BigInt(from.id), {
        username: from.username,
        firstName: from.first_name,
        lastName: from.last_name,
      });

      const sub = await activateTrial(user.id, {
        firstName: user.firstName,
        lastName: user.lastName,
        telegramId: Number(from.id),
      });

      const subLink = buildSubLink(deps.env, sub.subId!);
      const expires = sub.expiresAt?.toLocaleString("ru-RU", { timeZone: "UTC" }) ?? "—";

      await ctx.editMessageText(
        `
🆓 <b>Пробный период активирован!</b>

<b>Срок:</b> 1 день
<b>Трафик:</b> 10 ГБ
<b>Окончание:</b> ${expires} UTC

<b>Ссылка для подключения:</b>
<code>${subLink}</code>
`.trim(),
        {
          parse_mode: "HTML",
          reply_markup: subscriptionKeyboard(),
        },
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не удалось активировать пробный период";
      await ctx.editMessageText(`❌ ${message}`, {
        reply_markup: backToMainKeyboard(),
      });
    }
  });

  return composer;
}
