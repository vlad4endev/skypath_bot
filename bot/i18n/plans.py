"""Localized plan serialization for API and bot."""
from bot.config import PLANS
from bot.i18n import get_months_labels, get_plan_features, get_plans, normalize_locale, t


def serialize_plans(locale: str) -> dict:
    loc = normalize_locale(locale)
    plan_names = get_plans(loc)
    features = get_plan_features(loc)
    result = {}
    for key, plan in PLANS.items():
        localized = plan_names.get(key, {})
        entry = {
            "key": key,
            "name": localized.get("name", plan["name"]),
            "description": localized.get("description", plan.get("description", "")),
            "limit_ip": plan.get("limit_ip", 1),
            "traffic_gb": plan.get("traffic_gb", 0),
            "features": features.get(key, []),
            "recommended": key == "MULTI",
        }
        if key == "FREE":
            entry["price"] = 0
            entry["days"] = plan.get("days", 3)
        else:
            entry["prices"] = plan.get("prices", {})
        result[key] = entry
    return result


def plan_display_name(plan_key: str | None, locale: str) -> str:
    if not plan_key:
        return "—"
    loc = normalize_locale(locale)
    names = get_plans(loc)
    if plan_key in names and names[plan_key].get("name"):
        return names[plan_key]["name"]
    return PLANS.get(plan_key, {}).get("name", plan_key)


def months_labels(locale: str) -> dict[int, str]:
    return get_months_labels(locale)


def i18n_bundle(locale: str) -> dict:
    """App + cabinet UI strings for frontends."""
    from bot.i18n import LOCALE_LABELS, SUPPORTED_LOCALES, _load_locale, is_rtl

    loc = normalize_locale(locale)
    data = _load_locale(loc)
    return {
        "locale": loc,
        "rtl": is_rtl(loc),
        "supported_locales": list(SUPPORTED_LOCALES),
        "locale_labels": LOCALE_LABELS,
        "app": data.get("app", {}),
        "cabinet": data.get("cabinet", {}),
        "lang": data.get("lang", {}),
    }
