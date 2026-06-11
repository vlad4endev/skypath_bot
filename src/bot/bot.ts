import { Bot, session } from "grammy";
import type { BotContext, BotDependencies, SessionData } from "./context.js";
import { createStartHandlers } from "./handlers/start.js";
import { createAccountHandlers } from "./handlers/account.js";
import { createSubscriptionHandlers } from "./handlers/subscription.js";
import { createPaymentHandlers } from "./handlers/payment.js";

export function createBot(deps: BotDependencies): Bot<BotContext> {
  const bot = new Bot<BotContext>(deps.env.BOT_TOKEN);

  bot.use(
    session({
      initial: (): SessionData => ({}),
    }),
  );

  bot.use(createStartHandlers(deps));
  bot.use(createAccountHandlers(deps));
  bot.use(createSubscriptionHandlers(deps));
  bot.use(createPaymentHandlers(deps));

  bot.catch((err) => {
    console.error("Bot error:", err);
  });

  return bot;
}
