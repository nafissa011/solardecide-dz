"""Admin decorators and logging helpers."""
from __future__ import annotations

import functools
import logging
from datetime import datetime
from typing import Optional

from flask import jsonify, request

logger = logging.getLogger(__name__)


def admin_required(fn):
    """403 unless the JWT belongs to a user with role='admin'."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            from services.plan_service import get_current_user
            user = get_current_user()
        except Exception:
            user = None
        if user is None:
            return jsonify({"error": "not_authenticated", "status": 401}), 401
        role = (getattr(user, "role", "") or "").lower()
        if role != "admin":
            return jsonify({"error": "admin_required", "status": 403}), 403
        return fn(*args, **kwargs)
    return wrapper


def log_activity(action: str, *, user_id: Optional[int] = None, details: str = "") -> None:
    """Best-effort insert into activity_logs. Never raises."""
    try:
        from db_models import db, ActivityLog
        row = ActivityLog(
            user_id    = user_id,
            action     = (action or "")[:50],
            details    = (details or "")[:500],
            created_at = datetime.utcnow(),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as exc:
        logger.debug("log_activity skipped: %s", exc)


def log_error(message: str, *, page: str = "", user_id: Optional[int] = None) -> None:
    """Best-effort insert into error_logs. Never raises."""
    try:
        from db_models import db, ErrorLog
        row = ErrorLog(
            message    = (message or "")[:2000],
            page       = (page or "")[:200],
            user_id    = user_id,
            created_at = datetime.utcnow(),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as exc:
        logger.debug("log_error skipped: %s", exc)


def install_error_logger(app) -> None:
    """Register a 500-handler that persists errors to error_logs."""
    @app.errorhandler(500)
    def _on_500(err):
        try:
            from services.plan_service import get_current_user
            user = get_current_user()
            uid = user.id if user else None
        except Exception:
            uid = None
        try:
            log_error(str(err), page=request.path, user_id=uid)
        except Exception:
            pass
        return jsonify({"error": "internal_error", "status": 500}), 500