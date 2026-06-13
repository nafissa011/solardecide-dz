"""Plan/subscription service — single source of truth for plan gating and quotas."""
from __future__ import annotations

import functools
import logging
from datetime import datetime, timedelta
from typing import Optional

from flask import jsonify, request

from db_models import User, db

logger = logging.getLogger(__name__)

PLAN_ORDER = {"free": 0, "pro": 1, "enterprise": 2}

PLAN_PRICES_DZD = {
    "free":       0,
    "pro":        4_000,
    "enterprise": 7_000,
}

# Mirrors frontend/js/plan.js FEATURE_MATRIX — keep in sync
FEATURE_REQUIREMENTS = {
    "action.export_csv_ranking":       "pro",
    "action.export_raw_csv":           "enterprise",
    "action.wilaya_pdf":               "pro",
    "action.zone_run_analysis":        "pro",
    "action.comparison_run":           "pro",
    "action.forecast_24h":             "pro",
    "action.forecast_7d":              "pro",
    "action.forecast_30d":             "enterprise",
    "action.forecast_1y":              "enterprise",
    "action.forecast_longterm":        "enterprise",
    "action.roi_compute":              "pro",
    "action.report_investor":          "pro",
    "action.report_government":        "enterprise",
    "action.recommendation":           "pro",
    "action.recommendation_unlimited": "enterprise",
    "action.api_access":               "enterprise",
}

# Monthly quotas per plan
QUOTAS = {
    "free":       {"recommandations": 0},
    "pro":        {"recommandations": 5},
    "enterprise": {"recommandations": float("inf")},
}


def _decode_jwt_from_request() -> Optional[dict]:
    """Reads from auth_token cookie, falls back to Authorization: Bearer."""
    import jwt as pyjwt
    from config import JWT_SECRET, JWT_ALGORITHM

    token = request.cookies.get("auth_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def get_current_user() -> Optional[User]:
    """Return the SQLAlchemy User matching the JWT, or None."""
    payload = _decode_jwt_from_request()
    if not payload:
        return None
    try:
        uid = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    return User.query.get(uid)


def effective_plan(user: Optional[User]) -> str:
    """Returns 'free' if user is None, plan is unknown, or plan has expired."""
    if user is None:
        return "free"
    p = (user.plan or "free").lower()
    if p not in PLAN_ORDER:
        return "free"
    if p != "free" and user.plan_expires_at and user.plan_expires_at < datetime.utcnow():
        return "free"
    return p


def has_plan(user: Optional[User], required: str) -> bool:
    """True iff user has at least the required plan tier."""
    return PLAN_ORDER.get(effective_plan(user), 0) >= PLAN_ORDER.get(required, 0)


def reset_counters_if_new_month(user: User) -> None:
    """Reset monthly counters when the calendar month changes."""
    now = datetime.utcnow()
    last = user.counters_reset_at or user.created_at or now
    if (last.year, last.month) != (now.year, now.month):
        user.analyses_count_month = 0
        user.recommandations_count_month = 0
        user.counters_reset_at = now
        db.session.commit()


def increment_counter(user: User, name: str) -> None:
    if name == "analyses":
        user.analyses_count_month = (user.analyses_count_month or 0) + 1
    elif name == "recommandations":
        user.recommandations_count_month = (user.recommandations_count_month or 0) + 1
    else:
        raise ValueError(f"Unknown counter '{name}'")
    db.session.commit()


def upgrade_user(user: User, plan: str, duration_days: int = 30) -> User:
    if plan not in PLAN_ORDER:
        raise ValueError(f"Unknown plan '{plan}'")
    user.plan = plan
    user.plan_expires_at = (
        None if plan == "free" else datetime.utcnow() + timedelta(days=duration_days)
    )
    db.session.commit()
    logger.info("User %s upgraded to %s (expires %s)", user.email, plan, user.plan_expires_at)
    return user


def downgrade_to_free(user: User) -> User:
    user.plan = "free"
    user.plan_expires_at = None
    db.session.commit()
    logger.info("User %s downgraded to free", user.email)
    return user


def _plan_required_response(required: str, feature: Optional[str] = None):
    payload = {
        "error":    "plan_required",
        "required": required,
        "message":  f"Cette fonctionnalité nécessite le plan {required.capitalize()}",
    }
    if feature:
        payload["feature"] = feature
    return jsonify(payload), 402


def _quota_exceeded_response(name: str, limit, used: int):
    return jsonify({
        "error":   "quota_exceeded",
        "counter": name,
        "limit":   limit if limit != float("inf") else None,
        "used":    used,
        "message": (
            f"Quota mensuel atteint ({used}/{limit}). "
            "Passez au plan Entreprise pour un usage illimité."
        ),
    }), 429


# Disables plan gating for end-to-end testing — set to False to restore paywall
TEST_MODE_OPEN_ALL_FEATURES = True


def check_plan(required: str = "pro", feature: Optional[str] = None):
    """
    Decorator: requires at least `required` plan.
    When TEST_MODE_OPEN_ALL_FEATURES is True, only authentication is checked.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify({"error": "not_authenticated", "status": 401}), 401
            reset_counters_if_new_month(user)
            if TEST_MODE_OPEN_ALL_FEATURES:
                return fn(*args, **kwargs)
            if not has_plan(user, required):
                return _plan_required_response(required, feature)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def consume_quota(counter_name: str):
    """
    Decorator: enforces and consumes a monthly quota.
    Always pair with @check_plan above this decorator.
    Counter is incremented BEFORE the handler runs — prevents unlimited retries on handler failure.
    Enterprise plan bypasses quota (limit = inf).
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify({"error": "not_authenticated"}), 401
            reset_counters_if_new_month(user)
            plan  = effective_plan(user)
            limit = QUOTAS.get(plan, {}).get(counter_name, 0)
            used  = getattr(user, f"{counter_name}_count_month", 0) or 0
            if (not TEST_MODE_OPEN_ALL_FEATURES) and limit != float("inf") and used >= limit:
                return _quota_exceeded_response(counter_name, limit, used)
            increment_counter(user, counter_name)
            return fn(*args, **kwargs)
        return wrapper
    return decorator