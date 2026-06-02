# Деплой SkyPath VPN Bot на VPS

Репозиторий: https://github.com/vlad4endev/skypath_bot

## 1. На VPS (Ubuntu/Debian)

```bash
git clone https://github.com/vlad4endev/skypath_bot.git
cd skypath_bot
./scripts/bootstrap.sh
nano .env   # секреты
./scripts/deploy.sh
./scripts/ssl.sh   # после заполнения CERTBOT_EMAIL
```

## 2. YooKassa — URL уведомлений

В [личном кабинете YooKassa](https://yookassa.ru/) → Настройки → HTTP-уведомления:

```
https://<NGINX_DOMAIN>/yookassa/webhook
```

События: `payment.succeeded`, `payment.canceled` (если используете).

## 3. Telegram

Webhook выставляется автоматически при старте бота:

```
https://<NGINX_DOMAIN>/webhook/<BOT_TOKEN>
```

Mini App URL в @BotFather: `https://<NGINX_DOMAIN>/app`

## 4. Проверка

```bash
docker compose ps
curl -s https://<домен>/health
./scripts/logs.sh bot
```

В Telegram: `/start`

## 5. Обновление

```bash
git pull
./scripts/deploy.sh
```
