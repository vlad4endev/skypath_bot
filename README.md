# 🛡 SkyPath VPN Bot

**Production-ready Telegram бот для VPN сервиса с Telegram Mini App**

Полная замена n8n воркфлоу — работает автономно на сервере без сторонних сервисов автоматизации.

---

## 🆚 Сравнение: было (n8n) vs стало (этот бот)

| Функция | n8n + NocoDB | Этот бот |
|---|---|---|
| База данных | NocoDB (ограниченный API) | **PostgreSQL** (полный SQL, индексы) |
| Платежи | Webhook → n8n | **YooKassa прямо в боте** |
| VPN API | HTTP Request ноды | **Готовый XUIClient класс** |
| Рассылки | Schedule Trigger | **APScheduler внутри бота** |
| Надёжность | Зависит от n8n | **Standalone, Docker** |
| Масштабирование | Сложное | **PostgreSQL + Redis** |
| Mini App | WebApp кнопка | **Полноценный личный кабинет** |

---

## 📦 Стек технологий

- **Python 3.12** + **aiogram 3.x** (async Telegram bot)
- **PostgreSQL 16** — основная база (вместо NocoDB)
- **Redis** — FSM состояния + кеш
- **SQLAlchemy 2.0** — ORM с async поддержкой
- **YooKassa** — приём платежей по карте
- **3X-UI API** — управление VPN клиентами
- **APScheduler** — cron задачи (уведомления, деактивация)
- **Docker Compose** — деплой в один команды
- **Nginx** — SSL + раздача Mini App

---

## 🚀 Быстрый старт

### 1. Клонируй и настрой

```bash
git clone https://github.com/vlad4endev/skypath_bot.git
cd skypath_bot
./scripts/bootstrap.sh
nano .env   # BOT_TOKEN, YooKassa, 3X-UI, домен
```

### 2. Деплой одной командой

```bash
./scripts/deploy.sh
./scripts/ssl.sh   # Let's Encrypt (нужен CERTBOT_EMAIL в .env)
```

Подробнее: [DEPLOY.md](DEPLOY.md)

### 3. Webhook

Бот сам ставит Telegram webhook при старте. В YooKassa укажи:

`https://<твой-домен>/yookassa/webhook`

---

## 📋 Переменные окружения (.env)

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен от @BotFather |
| `ADMIN_IDS` | Telegram ID администраторов (через запятую) |
| `WEBHOOK_BASE_URL` | HTTPS домен сервера |
| `NGINX_DOMAIN` | Домен без https:// (для nginx и SSL) |
| `CERTBOT_EMAIL` | Email для Let's Encrypt |
| `MINI_APP_URL` | URL Telegram Mini App |
| `DB_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `YOOKASSA_SHOP_ID` | ID магазина YooKassa |
| `YOOKASSA_SECRET_KEY` | Секретный ключ YooKassa |
| `XUI_HOST` | URL 3X-UI панели (с портом) |
| `XUI_URL_PREFIX` | Префикс URL (из настроек панели) |
| `XUI_USERNAME` | Логин в 3X-UI |
| `XUI_PASSWORD` | Пароль в 3X-UI |
| `INBOUND_RU/US/DE/KZ/NL` | ID inbound для каждой страны |

---

## 🗄 Структура БД (PostgreSQL)

```
users          — пользователи бота
subscriptions  — подписки и VPN ключи
payments       — история платежей
promo_codes    — промокоды
broadcasts     — рассылки
```

---

## 🤖 Возможности бота

### Для пользователей:
- `/start` — приветствие, регистрация
- 🔑 Получить VPN — выбор тарифа
- 👤 Аккаунт — статус подписки
- 🔑 Мои ключи — VPN ключи и sub-ссылки
- 💳 Продлить/Купить — продление подписки
- 🌐 Личный кабинет — Telegram Mini App
- 📖 Инструкции — настройка VPN приложений

### Тарифы:
- 🆓 Пробный — 3 дня бесплатно
- 💎 Базовый — от 250 руб/мес, 3 устройства
- 🚀 Мульти — от 350 руб/мес, 5 устройств
- 👑 Супер — от 450 руб/мес, 10 устройств

### Для администратора (`/admin`):
- 📊 Статистика — пользователи, выручка, подписки
- 📢 Рассылка — всем или только активным
- 💰 Платежи — история транзакций
- 🔑 Промокоды — управление скидками

### Автоматические задачи (каждый день):
- **08:00** — напоминание о истечении через 1 день
- **09:00** — напоминание о истечении сегодня
- **10:00** — деактивация истёкших подписок + отключение в 3X-UI

---

## 📱 Telegram Mini App

Полноценный личный кабинет прямо в Telegram:
- Статус подписки с прогресс-баром
- Таблица VPN ключей с кнопкой копирования
- Выбор тарифа и оплата
- Статус серверов
- Тёмная тема, адаптивный дизайн

Адрес: `https://your-domain.com/app`

---

## 🔧 Разработка

```bash
# Установить зависимости
pip install -r requirements.txt

# Миграции БД (Alembic)
alembic init alembic
alembic revision --autogenerate -m "init"
alembic upgrade head

# Запуск в режиме polling (для разработки)
python -m bot.main --polling
```

---

## 📞 Поддержка

- Telegram: @SkyPathsupport
- Канал: @SkyPathVPN
