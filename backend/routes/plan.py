from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from services.plan_service import (
    PLAN_ORDER, PLAN_PRICES_DZD, QUOTAS,
    effective_plan, get_current_user, reset_counters_if_new_month,
    upgrade_user, downgrade_to_free,
)

logger = logging.getLogger(__name__)
bp = Blueprint("plan", __name__)


@bp.get("/plan/info")
def plan_info():
    user = get_current_user()
    if user is None:
        # Unauthenticated users can still read prices and quotas for the pricing page
        return jsonify({
            "data": {
                "plan":          "free",
                "authenticated": False,
                "prices":        PLAN_PRICES_DZD,
                "quotas":        _serialisable_quotas(),
            },
            "status": 200,
        })
    reset_counters_if_new_month(user)
    return jsonify({
        "data": {
            "authenticated":               True,
            "plan":                        effective_plan(user),
            "plan_stored":                 user.plan,
            "plan_expires_at":             user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "analyses_count_month":        int(user.analyses_count_month or 0),
            "recommandations_count_month": int(user.recommandations_count_month or 0),
            "prices":                      PLAN_PRICES_DZD,
            "quotas":                      _serialisable_quotas(),
        },
        "status": 200,
    })


@bp.get("/plan/quotas")
def plan_quotas():
    return jsonify({"data": _serialisable_quotas(), "status": 200})


@bp.post("/upgrade-plan")
def upgrade_plan():
    """
    POST /api/upgrade-plan
    Body: { "plan": "pro"|"enterprise", "duration_days": 30 }

    Simulates a successful payment — real CIB/Baridimob integration is Phase 3.
    """
    user = get_current_user()
    if user is None:
        return jsonify({"error": "not_authenticated"}), 401

    data = request.get_json(silent=True) or {}
    plan     = (data.get("plan") or "").lower().strip()
    duration = int(data.get("duration_days") or 30)

    if plan not in PLAN_ORDER:
        return jsonify({"error": "invalid_plan", "allowed": list(PLAN_ORDER.keys())}), 400

    if plan == "free":
        downgrade_to_free(user)
    else:
        upgrade_user(user, plan, duration_days=duration)

    try:
        from services.admin_service import log_activity
        log_activity("upgrade", user_id=user.id,
                     details=f"free→{plan}" if plan != "free" else "pro→free")
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        "data": {
            "plan":            user.effective_plan(),
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "message":         f"Plan {plan} activé pour {duration} jours (simulation)",
            "simulation":      True,
        },
        "status": 200,
    })


@bp.post("/plan/downgrade")
def downgrade():
    """POST /api/plan/downgrade — user-initiated cancel, drops back to free."""
    user = get_current_user()
    if user is None:
        return jsonify({"error": "not_authenticated"}), 401
    downgrade_to_free(user)
    return jsonify({"data": {"plan": "free"}, "status": 200})


@bp.post("/plan/admin-set")
def admin_set():
    """
    POST /api/plan/admin-set — admin override, requires role='admin'.
    Body: { "user_id": int, "plan": "pro"|"enterprise"|"free", "duration_days": 30 }
    """
    me = get_current_user()
    if me is None or getattr(me, "role", "user") != "admin":
        return jsonify({"error": "forbidden"}), 403

    from db_models import User
    data     = request.get_json(silent=True) or {}
    target   = User.query.get(int(data.get("user_id") or 0))
    if not target:
        return jsonify({"error": "user_not_found"}), 404
    plan     = (data.get("plan") or "free").lower()
    duration = int(data.get("duration_days") or 30)

    if plan == "free":
        downgrade_to_free(target)
    else:
        upgrade_user(target, plan, duration_days=duration)

    return jsonify({"data": target.to_public_dict(), "status": 200})


def _serialisable_quotas():
    """Convert QUOTAS to JSON-safe dict, replacing float('inf') with None."""
    out = {}
    for plan, m in QUOTAS.items():
        out[plan] = {k: (None if v == float("inf") else v) for k, v in m.items()}
    return out