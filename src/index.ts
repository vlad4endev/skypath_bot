import "dotenv/config";
import { loadEnv } from "./env.js";
import { prisma } from "./db.js";
import { PlategaClient } from "./api/platega.js";
import { createBot } from "./bot/bot.js";
import { createServer } from "./server/webhook.js";
import { startCronJobs } from "./jobs/index.js";

async function main(): Promise<void> {
  const env = loadEnv();
  const platega = new PlategaClient(env);
  const deps = { env, platega };
  const bot = createBot(deps);

  startCronJobs(bot);

  if (env.isProduction && !env.WEBHOOK_URL) {
    throw new Error("WEBHOOK_URL is required when NODE_ENV=production");
  }

  if (env.isProduction && env.WEBHOOK_URL) {
    const webhookUrl = `${env.WEBHOOK_URL.replace(/\/$/, "")}/webhook/telegram`;
    await bot.api.deleteWebhook({ drop_pending_updates: true });
    await bot.api.setWebhook(webhookUrl);
    console.log(`Telegram webhook: ${webhookUrl}`);
    await createServer(bot, env);
  } else {
    console.log("Starting bot in polling mode (development)");
    await bot.api.deleteWebhook({ drop_pending_updates: true });
    void createServer(bot, env);
    await bot.start({
      onStart: (info) => console.log(`Bot @${info.username} started`),
    });
  }
}

main().catch(async (error) => {
  console.error("Fatal error:", error);
  await prisma.$disconnect();
  process.exit(1);
});

process.on("SIGINT", async () => {
  await prisma.$disconnect();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await prisma.$disconnect();
  process.exit(0);
});
