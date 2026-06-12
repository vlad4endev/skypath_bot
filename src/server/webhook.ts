import Fastify from "fastify";
import { webhookCallback } from "grammy";
import type { Bot } from "grammy";
import type { BotContext } from "../bot/context.js";
import type { Env } from "../env.js";
import { parsePlategaWebhook, verifyPlategaWebhookHeaders } from "../api/platega.js";
import { processPaidOrder } from "../shared/subscriptionService.js";

export async function createServer(bot: Bot<BotContext>, env: Env) {
  const app = Fastify({ logger: true });

  app.get("/health", async () => ({ ok: true }));

  const telegramWebhook = webhookCallback(bot, "fastify");
  app.post("/webhook/telegram", telegramWebhook);

  app.post("/webhook/platega", async (request, reply) => {
    if (!verifyPlategaWebhookHeaders(request.headers, env)) {
      return reply.code(401).send({ error: "Unauthorized" });
    }

    const parsed = parsePlategaWebhook(request.body);
    if (!parsed) {
      return reply.code(400).send({ error: "Invalid payload" });
    }

    if (!parsed.isPaid) {
      return reply.send({ ok: true, skipped: parsed.isCancelled ? "cancelled" : true });
    }

    const paymentRef = parsed.orderId ?? parsed.transactionId;
    if (!paymentRef) {
      return reply.code(400).send({ error: "Missing payment reference" });
    }

    try {
      const result = await processPaidOrder(paymentRef, env);

      if (result.subLink) {
        const text = result.alreadyPaid
          ? `✅ Подписка уже активна.\n\n🔗 <code>${result.subLink}</code>`
          : `✅ Оплата получена!\n\n🔗 Ссылка для подключения:\n<code>${result.subLink}</code>`;

        await bot.api.sendMessage(Number(result.telegramId), text, {
          parse_mode: "HTML",
        });
      }
    } catch (error) {
      request.log.error({ error, paymentRef }, "Platega webhook failed");
      return reply.code(500).send({ error: "Processing failed" });
    }

    return reply.send({ ok: true });
  });

  await app.listen({ port: env.PORT, host: "0.0.0.0" });
  return app;
}
