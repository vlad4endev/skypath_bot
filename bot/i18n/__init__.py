"""
Internationalization — ru, en, hi, ar
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from database.models import User

SUPPORTED_LOCALES = ("ru", "en", "hi", "ar")
DEFAULT_LOCALE = "ru"
LOCALES_DIR = Path(__file__).parent / "locales"

LOCALE_LABELS = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "hi": "🇮🇳 हिन्दी",
    "ar": "🇸🇦 العربية",
}

_TELEGRAM_LANG_MAP: dict[str, str] = {
    "ru": "ru",
    "uk": "ru",
    "be": "ru",
    "en": "en",
    "hi": "hi",
    "ar": "ar",
    "fa": "ar",
    "ur": "ar",
}


def normalize_locale(code: str | None) -> str:
    if not code:
        return DEFAULT_LOCALE
    base = code.strip().lower().split("-")[0]
    return base if base in SUPPORTED_LOCALES else DEFAULT_LOCALE


def map_telegram_language(language_code: str | None) -> str:
    if not language_code:
        return DEFAULT_LOCALE
    base = language_code.strip().lower().split("-")[0]
    return _TELEGRAM_LANG_MAP.get(base, DEFAULT_LOCALE)


def get_user_locale(user: User | None, telegram_lang: str | None = None) -> str:
    if user and user.preferred_locale:
        return normalize_locale(user.preferred_locale)
    if telegram_lang:
        return map_telegram_language(telegram_lang)
    return DEFAULT_LOCALE


@lru_cache(maxsize=8)
def _load_locale(locale: str) -> dict[str, Any]:
    loc = normalize_locale(locale)
    path = LOCALES_DIR / f"{loc}.json"
    if not path.exists():
        path = LOCALES_DIR / f"{DEFAULT_LOCALE}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def t(locale: str, key: str, **kwargs: Any) -> str:
    """Translate dot-separated key, e.g. t('en', 'welcome.new', brand='X')."""
    loc = normalize_locale(locale)
    data = _load_locale(loc)
    parts = key.split(".")
    node: Any = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            fallback = _load_locale(DEFAULT_LOCALE)
            node = fallback
            for p in parts:
                if isinstance(node, dict) and p in node:
                    node = node[p]
                else:
                    return key
            break
        node = node[part]
    if not isinstance(node, str):
        return key
    if kwargs:
        try:
            return node.format(**kwargs)
        except (KeyError, ValueError):
            return node
    return node


def get_section(locale: str, section: str) -> dict[str, Any]:
    loc = normalize_locale(locale)
    data = _load_locale(loc)
    section_data = data.get(section, {})
    return section_data if isinstance(section_data, dict) else {}


def get_months_labels(locale: str) -> dict[int, str]:
    raw = get_section(locale, "months")
    return {int(k): v for k, v in raw.items()}


def get_plans(locale: str) -> dict[str, dict[str, Any]]:
    return get_section(locale, "plans")


def get_plan_features(locale: str) -> dict[str, list[str]]:
    return get_section(locale, "plan_features")


def is_rtl(locale: str) -> bool:
    return normalize_locale(locale) == "ar"


def clear_cache() -> None:
    _load_locale.cache_clear()
