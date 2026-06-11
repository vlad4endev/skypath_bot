import { Composer } from "grammy";
import type { BotContext, BotDependencies } from "../context.js";
import { backToMainKeyboard } from "../keyboards.js";
import { getOrCreateUser } from "../../shared/subscriptionService.js";

export function createAccountHandlers(_deps: BotDependencies): Composer<BotContext> {
  const composer = new Composer<BotContext>();

  composer.callbackQuery("account:view", async (ctx) => {
    await ctx.answerCallbackQuery();
    const from = ctx.from;
    if (!from) return;

    const user = await getOrCreateUser(BigInt(from.id), {
      username: from.username,
      firstName: from.first_name,
      lastName: from.last_name,
    });

    const name = [user.firstName, user.lastName].filter(Boolean).join(" ") || "—";
    const username = user.username ? `@${user.username}` : "—";

    const text = `
👤 <b>Аккаунт</b>

<b>Имя:</b> ${name}
<b>Username:</b> ${username}
<b>Telegram ID:</b> <code>${user.telegramId}</code>
<b>Регистрация:</b> ${user.createdAt.toLocaleDateString("ru-RU")}
`.trim();

    await ctx.editMessageText(text, {
      parse_mode: "HTML",
      reply_markup: backToMainKeyboard(),
    });
  });

  return composer;
}
