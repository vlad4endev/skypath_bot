"""
Конфигурация из переменных окружения (.env)
"""
import hashlib
import logging
import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Telegram secret_token: только A-Za-z0-9_- (двоеточие в BOT_TOKEN недопустимо)
_WEBHOOK_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


def resolve_webhook_secret(bot_token: str, explicit: str = "") -> str:
    explicit = (explicit or "").strip()
    if explicit and _WEBHOOK_SECRET_RE.fullmatch(explicit):
        return explicit
    if explicit:
        logger.warning(
            "WEBHOOK_SECRET in .env is invalid for Telegram; using derived secret. "
            "Remove WEBHOOK_SECRET or use only A-Za-z0-9_-"
        )
    return hashlib.sha256(bot_token.encode()).hexdigest()[:48]


@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "SkyPathVPN_Bot")
    BRAND_NAME: str = os.getenv("BRAND_NAME", "SKYFLOW VPN")
    ADMIN_IDS: list[int] = None  # заполняется в __post_init__

    # Server — BOT_MODE: webhook (default) | polling (если Telegram не достучится до VPS)
    BOT_MODE: str = os.getenv("BOT_MODE", "webhook")
    WEBHOOK_BASE_URL: str = os.getenv("WEBHOOK_BASE_URL", "https://your-domain.com")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
    PORT: int = int(os.getenv("PORT", "8080"))
    MINI_APP_URL: str = os.getenv("MINI_APP_URL", "https://your-domain.com/app")
    WELCOME_PHOTO_URL: str = os.getenv("WELCOME_PHOTO_URL", "")

    # Database (PostgreSQL)
    DB_URL: str = os.getenv(
        "DB_URL",
        "postgresql+asyncpg://vpnbot:password@localhost:5432/skypath"
    )

    # Redis (FSM + кеш)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Platega.io — https://docs.platega.io/
    PLATEGA_MERCHANT_ID: str = os.getenv("PLATEGA_MERCHANT_ID", "")
    PLATEGA_SECRET: str = os.getenv("PLATEGA_SECRET", "")
    # Пусто = v2 (пользователь выбирает способ на странице Platega).
    # 2=СБП, 11=карта, 12=международная, 13=крипто
    PLATEGA_PAYMENT_METHOD = None

    # 3X-UI VPN Panel
    XUI_HOST: str = os.getenv("XUI_HOST", "https://178.208.87.245:2053")
    XUI_URL_PREFIX: str = os.getenv("XUI_URL_PREFIX", "/KolbUBTWA0")
    XUI_USERNAME: str = os.getenv("XUI_USERNAME", "admin")
    XUI_PASSWORD: str = os.getenv("XUI_PASSWORD", "password")
    XUI_API_TOKEN: str = os.getenv("XUI_API_TOKEN", "")
    XUI_SUB_PATH: str = os.getenv("XUI_SUB_PATH", "/sub/")
    # База subscription URL (обратный прокси из 3X-UI → Settings → Subscription).
    # Пример: https://sub.skypath.fun:8671/vk098 → ссылка .../vk098/{subId}
    XUI_SUB_BASE_URL: str = os.getenv("XUI_SUB_BASE_URL", "")
    XUI_INBOUND_IDS: dict = None  # заполняется в __post_init__

    # Legal
    TERMS_URL: str = os.getenv(
        "TERMS_URL",
        "https://telegra.ph/Polzovatelskoe-soglashenie-02-05-18",
    )
    PRIVACY_URL: str = os.getenv(
        "PRIVACY_URL",
        "https://telegra.ph/Politika-konfidencialnosti-02-05-18",
    )

    # Support
    SUPPORT_URL: str = os.getenv("SUPPORT_URL", "https://t.me/SkyPathsupport")
    SUPPORT_CHANNEL: str = os.getenv("SUPPORT_CHANNEL", "@SkyPathVPN")
    ADMIN_NOTIFY_ID: int = int(os.getenv("ADMIN_NOTIFY_ID", "86517651"))

    # Web admin panel (SHA256 hash of password, see scripts/gen_admin_password.py)
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_PASSWORD_SALT: str = os.getenv("ADMIN_PASSWORD_SALT", "")

    def __post_init__(self):
        self.BOT_MODE = self.BOT_MODE.strip().lower()
        self.WEBHOOK_SECRET = resolve_webhook_secret(self.BOT_TOKEN, self.WEBHOOK_SECRET)
        method_raw = os.getenv("PLATEGA_PAYMENT_METHOD", "").strip()
        self.PLATEGA_PAYMENT_METHOD = int(method_raw) if method_raw else None
        self.ADMIN_IDS = [
            int(x) for x in os.getenv("ADMIN_IDS", "86517651").split(",") if x.strip()
        ]
        if not self.ADMIN_PASSWORD_SALT:
            self.ADMIN_PASSWORD_SALT = self.WEBHOOK_SECRET[:32] or "skypath-admin-salt"
        self.XUI_INBOUND_IDS = {
            "🇷🇺 Россия": int(os.getenv("INBOUND_RU", "1")),
            "🇺🇸 США": int(os.getenv("INBOUND_US", "19")),
            "🇰🇿 Казахстан": int(os.getenv("INBOUND_KZ", "20")),
            "🇩🇪 Германия": int(os.getenv("INBOUND_DE", "21")),
            "🇳🇱 Нидерланды": int(os.getenv("INBOUND_NL", "22")),
        }

    @property
    def use_polling(self) -> bool:
        return self.BOT_MODE == "polling"

    def xui_sub_url(self, sub_id: str) -> str:
        if self.XUI_SUB_BASE_URL.strip():
            base = self.XUI_SUB_BASE_URL.strip().rstrip("/")
            return f"{base}/{sub_id}"

        path = self.XUI_SUB_PATH if self.XUI_SUB_PATH.startswith("/") else f"/{self.XUI_SUB_PATH}"
        if not path.endswith("/"):
            path = f"{path}/"
        # Subscription-сервер не использует секретный префикс панели (XUI_URL_PREFIX).
        return f"{self.XUI_HOST.rstrip('/')}{path}{sub_id}"


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
