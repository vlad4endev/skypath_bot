"""Localized API response messages for mini app and web cabinet."""
from __future__ import annotations

from typing import Any

from bot.i18n import DEFAULT_LOCALE, t

# Re-export for convenience
__all__ = ["api_msg", "localize_purchase_result"]


def api_msg(locale: str, key: str, **kwargs: Any) -> str:
    """Translate api.{key}; fall back to Russian if missing."""
    loc = locale or DEFAULT_LOCALE
    text = t(loc, f"api.{key}", **kwargs)
    if text == f"api.{key}":
        text = t(DEFAULT_LOCALE, f"api.{key}", **kwargs)
    return text


def localize_purchase_result(result: dict[str, Any], locale: str) -> dict[str, Any]:
    """Add localized message field from error code when present."""
    out = dict(result)
    error = out.get("error")
    if error and isinstance(error, str):
        out["message"] = api_msg(locale, error)
    elif out.get("message_key"):
        out["message"] = api_msg(locale, str(out.pop("message_key")))
    elif out.get("free_trial") and out.get("provisioned"):
        out["message"] = api_msg(locale, "trial_activated")
    return out
