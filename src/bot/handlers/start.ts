import { Composer } from "grammy";
import type { BotContext, BotDependencies } from "../context.js";
import { mainMenuKeyboard, backToMainKeyboard } from "../keyboards.js";
import { getOrCreateUser } from "../../shared/subscriptionService.js";

const WELCOME_TEXT = `
👋 <b>Добро пожаловать в VPN-сервис!</b>

🛡 Безопасный и быстрый интернет без ограничений.

<b>Что вы получаете:</b>
• 🔒 Защита данных в любой сети
• ⚡ Высокая скорость без лимитов
• 📱 До 5 устройств одновременно
• 💰 От 250 ₽/месяц

Выберите действие в меню ниже 👇
`.trim();

const ABOUT_TEXT = `
ℹ️ <b>О сервисе</b>

Мы предоставляем надёжный VPN на базе VLESS + XTLS.

<b>Тарифы:</b>
• 1 мес — 250 ₽
• 2 мес — 500 ₽
• 3 мес — 750 ₽
• 6 мес — 1250 ₽

<b>Пробный период:</b> 1 день, 10 ГБ — один раз на аккаунт.

Поддержка: @${"support"}
`.trim();

const APPS_TEXT = `
📱 <b>Приложения для подключения</b>

<b>iOS / macOS:</b>
• Streisand, V2Box, FoXray

<b>Android:</b>
• v2rayNG, NekoBox

<b>Windows:</b>
• Hiddify, v2rayN

<b>Инструкция:</b>
1. Установите приложение
2. Скопируйте ссылку подписки из раздела «Моя подписка»
3. Добавьте подписку в приложение
`.trim();

export function createStartHandlers(_deps: BotDependencies): Composer<BotContext> {
  const composer = new Composer<BotContext>();

  composer.command("start", async (ctx) => {
    const from = ctx.from;
    if (!from) return;

    await getOrCreateUser(BigInt(from.id), {
      username: from.username,
      firstName: from.first_name,
      lastName: from.last_name,
    });

    await ctx.reply(WELCOME_TEXT, {
      parse_mode: "HTML",
      reply_markup: mainMenuKeyboard(),
    });
  });

  composer.callbackQuery("menu:main", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.editMessageText(WELCOME_TEXT, {
      parse_mode: "HTML",
      reply_markup: mainMenuKeyboard(),
    });
  });

  composer.callbackQuery("info:about", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.editMessageText(ABOUT_TEXT, {
      parse_mode: "HTML",
      reply_markup: backToMainKeyboard(),
    });
  });

  composer.callbackQuery("info:apps", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.editMessageText(APPS_TEXT, {
      parse_mode: "HTML",
      reply_markup: backToMainKeyboard(),
    });
  });

  return composer;
}
