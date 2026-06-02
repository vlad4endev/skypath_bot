"""
Конфигурация из переменных окружения (.env)
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "SkyPathVPN_Bot")
    ADMIN_IDS: list[int] = None  # заполняется в __post_init__

    # Server
    WEBHOOK_BASE_URL: str = os.getenv("WEBHOOK_BASE_URL", "https://your-domain.com")
    PORT: int = int(os.getenv("PORT", "8080"))
    MINI_APP_URL: str = os.getenv("MINI_APP_URL", "https://your-domain.com/app")

    # Database (PostgreSQL)
    DB_URL: str = os.getenv(
        "DB_URL",
        "postgresql+asyncpg://vpnbot:password@localhost:5432/skypath"
    )

    # Redis (FSM + кеш)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # YooKassa
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "")
    YOOKASSA_RETURN_URL: str = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/SkyPathVPN_Bot")

    # 3X-UI VPN Panel
    XUI_HOST: str = os.getenv("XUI_HOST", "https://178.208.87.245:2053")
    XUI_URL_PREFIX: str = os.getenv("XUI_URL_PREFIX", "/KolbUBTWA0")
    XUI_USERNAME: str = os.getenv("XUI_USERNAME", "admin")
    XUI_PASSWORD: str = os.getenv("XUI_PASSWORD", "password")
    XUI_INBOUND_IDS: dict = None  # заполняется в __post_init__

    # Support
    SUPPORT_URL: str = os.getenv("SUPPORT_URL", "https://t.me/SkyPathsupport")
    SUPPORT_CHANNEL: str = os.getenv("SUPPORT_CHANNEL", "@SkyPathVPN")
    ADMIN_NOTIFY_ID: int = int(os.getenv("ADMIN_NOTIFY_ID", "86517651"))

    def __post_init__(self):
        self.ADMIN_IDS = [
            int(x) for x in os.getenv("ADMIN_IDS", "86517651").split(",") if x.strip()
        ]
        # Inbound IDs для разных локаций
        self.XUI_INBOUND_IDS = {
            "🇷🇺 Россия": int(os.getenv("INBOUND_RU", "1")),
            "🇺🇸 США": int(os.getenv("INBOUND_US", "19")),
            "🇰🇿 Казахстан": int(os.getenv("INBOUND_KZ", "20")),
            "🇩🇪 Германия": int(os.getenv("INBOUND_DE", "21")),
            "🇳🇱 Нидерланды": int(os.getenv("INBOUND_NL", "22")),
        }


# Тарифные планы
PLANS = {
    "FREE": {
        "name": "🆓 Пробный",
        "price": 0,
        "months": 0,
        "days": 3,
        "limit_ip": 1,
        "traffic_gb": 5,
        "description": "3 дня бесплатно, 1 устройство, 5 ГБ",
    },
    "BASIC": {
        "name": "💎 Базовый",
        "prices": {1: 250, 2: 450, 3: 650, 6: 1200, 12: 2000},
        "limit_ip": 3,
        "traffic_gb": 0,  # 0 = безлимит
        "description": "До 3 устройств, безлимитный трафик",
    },
    "MULTI": {
        "name": "🚀 Мульти",
        "prices": {1: 350, 2: 650, 3: 900, 6: 1700, 12: 2800},
        "limit_ip": 5,
        "traffic_gb": 0,
        "description": "До 5 устройств, все локации",
    },
    "SUPER": {
        "name": "👑 Супер",
        "prices": {1: 450, 2: 850, 3: 1200, 6: 2200, 12: 3500},
        "limit_ip": 10,
        "traffic_gb": 0,
        "description": "До 10 устройств, приоритет, все локации",
    },
}

MONTHS_LABELS = {
    1: "1 месяц",
    2: "2 месяца",
    3: "3 месяца",
    6: "6 месяцев",
    12: "12 месяцев (год)",
}
