import cron from "node-cron";
import type { Bot } from "grammy";
import type { BotContext } from "../bot/context.js";
import {
  expireSubscriptions,
  getExpiringSubscriptions,
  markNotified,
} from "../shared/subscriptionService.js";
import { InlineKeyboard } from "grammy";

export function startCronJobs(bot: Bot<BotContext>): void {
  cron.schedule("0 5 * * *", async () => {
    console.log("[cron] Expiry reminders");
    await sendReminders(bot, 3);
    await sendReminders(bot, 0);
  });

  cron.schedule("0 6 * * *", async () => {
    console.log("[cron] Disabling expired subscriptions");
    const count = await expireSubscriptions();
    console.log(`[cron] Expired ${count} subscriptions`);
  });

  console.log("Cron jobs scheduled: reminders 05:00 UTC, expire 06:00 UTC");
}

async function sendReminders(bot: Bot<BotContext>, daysBefore: number): Promise<void> {
  const subs = await getExpiringSubscriptions(daysBefore);

  for (const sub of subs) {
    const expires = sub.expiresAt?.toLocaleDateString("ru-RU") ?? "—";
    const text =
      daysBefore === 3
        ? `⏰ Ваша подписка истекает через 3 дня (${expires}). Продлите, чтобы не потерять доступ.`
        : `⚠️ Сегодня последний день подписки (${expires}). Продлите сейчас!`;

    const keyboard = new InlineKeyboard().text("🔄 Продлить", "pay:plans");

    try {
      await bot.api.sendMessage(Number(sub.user.telegramId), text, {
        reply_markup: keyboard,
      });
      await markNotified(sub.id, daysBefore);
    } catch (error) {
      console.error(`Failed to notify user ${sub.user.telegramId}:`, error);
    }
  }
}
