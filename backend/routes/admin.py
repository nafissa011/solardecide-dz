"""
All endpoints below are gated by @admin_required (role == 'admin').

Routes
──────
  GET    /api/admin/dashboard-stats
  GET    /api/admin/users          ?plan=&search=
  PUT    /api/admin/users/<id>/plan
  POST   /api/admin/users/<id>/reset-quota
  PUT    /api/admin/users/<id>/toggle-active
  DELETE /api/admin/users/<id>
  GET    /api/admin/analytics
  GET    /api/admin/logs           ?type=&date=
  GET    /api/admin/reports
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from services.admin_service import admin_required, log_activity

logger = logging.getLogger(__name__)
bp = Blueprint("admin", __name__)


# ─────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────
def _today_start() -> datetime:
    n = datetime.utcnow()
    return datetime(n.year, n.month, n.day)


def _month_start() -> datetime:
    n = datetime.utcnow()
    return datetime(n.year, n.month, 1)


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────────────
#  GET /api/admin/dashboard-stats
# ─────────────────────────────────────────────────────────────────────
@bp.get("/admin/dashboard-stats")
@admin_required
def admin_dashboard_stats():
    from db_models import (
        db, User, ActivityLog, ZoneAnalysisHistory, ForecastHistory,
        ROIHistory, Report, Analysis,
    )

    today = _today_start()
    month = _month_start()

    total_users = db.session.query(User).count()
    active_today = db.session.query(User).filter(
        User.last_login != None, User.last_login >= today  # noqa: E711
    ).count()

    def _count_after(model, since):
        try:
            return db.session.query(model).filter(model.created_at >= since).count()
        except Exception:
            return 0

    # Aggregate across all activity models — no single unified table
    analyses_today = sum(_count_after(m, today) for m in
                         (ZoneAnalysisHistory, ROIHistory, ForecastHistory, Analysis))
    analyses_month = sum(_count_after(m, month) for m in
                         (ZoneAnalysisHistory, ROIHistory, ForecastHistory, Analysis))

    reports_today = _count_after(Report, today)
    reports_month = _count_after(Report, month)

    plan_counts_raw = (
        db.session.query(User.plan, func.count(User.id))
        .group_by(User.plan)
        .all()
    )
    plan_distribution = {"free": 0, "pro": 0, "enterprise": 0}
    for plan, n in plan_counts_raw:
        key = (plan or "free").lower()
        if key not in plan_distribution:
            key = "free"
        plan_distribution[key] = int(n)

    # Wilaya names are embedded in activity_log.details as "wilaya:Xxx ..."
    top_wilayas = []
    try:
        rows = (
            db.session.query(ActivityLog.details)
            .filter(ActivityLog.created_at >= month)
            .filter(ActivityLog.action.in_(["analyse_zone", "calcul_roi", "rapport"]))
            .all()
        )
        wcount = {}
        for (det,) in rows:
            if not det or "wilaya:" not in det:
                continue
            try:
                part = det.split("wilaya:", 1)[1]
                w = part.split()[0].strip().rstrip(",;|")
                if w:
                    wcount[w] = wcount.get(w, 0) + 1
            except Exception:
                continue
        top_wilayas = [
            {"wilaya": k, "count": v}
            for k, v in sorted(wcount.items(), key=lambda x: -x[1])[:5]
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("top_wilayas computation failed: %s", exc)
        top_wilayas = []

    return jsonify({
        "data": {
            "total_users":       total_users,
            "active_today":      active_today,
            "analyses_today":    int(analyses_today),
            "analyses_month":    int(analyses_month),
            "reports_today":     int(reports_today),
            "reports_month":     int(reports_month),
            "plan_distribution": plan_distribution,
            "top_wilayas":       top_wilayas,
            "generated_at":      datetime.utcnow().isoformat(),
        },
        "status": 200,
        "source": "sqlite",
    })


# ─────────────────────────────────────────────────────────────────────
#  GET /api/admin/users
# ─────────────────────────────────────────────────────────────────────
@bp.get("/admin/users")
@admin_required
def admin_list_users():
    from db_models import db, User, Report, Analysis, ZoneAnalysisHistory, ROIHistory, ForecastHistory

    plan_filter = (request.args.get("plan") or "all").strip().lower()
    search      = (request.args.get("search") or "").strip().lower()

    q = db.session.query(User)
    if plan_filter and plan_filter != "all":
        q = q.filter(User.plan == plan_filter)
    if search:
        like = f"%{search}%"
        q = q.filter((User.name.ilike(like)) | (User.email.ilike(like)))
    users = q.order_by(User.id.desc()).all()

    month = _month_start()
    out = []
    for u in users:
        try:
            a_month = sum([
                db.session.query(ZoneAnalysisHistory).filter(
                    ZoneAnalysisHistory.user_id == u.id,
                    ZoneAnalysisHistory.created_at >= month).count(),
                db.session.query(ROIHistory).filter(
                    ROIHistory.user_id == u.id,
                    ROIHistory.created_at >= month).count(),
                db.session.query(ForecastHistory).filter(
                    ForecastHistory.user_id == u.id,
                    ForecastHistory.created_at >= month).count(),
                db.session.query(Analysis).filter(
                    Analysis.user_id == u.id,
                    Analysis.created_at >= month).count(),
            ])
        except Exception:
            a_month = 0
        try:
            r_month = db.session.query(Report).filter(
                Report.user_id == u.id,
                Report.created_at >= month).count()
        except Exception:
            r_month = 0

        out.append({
            "id":         u.id,
            "name":       u.name,
            "email":      u.email,
            "plan":       u.effective_plan(),
            "plan_raw":   u.plan,
            "role":       getattr(u, "role", "user"),
            "is_active":  int(getattr(u, "is_active", 1) or 0),
            "analyses_month": int(a_month),
            "reports_month":  int(r_month),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if getattr(u, "last_login", None) else None,
        })

    return jsonify({"data": out, "count": len(out), "status": 200})


# ─────────────────────────────────────────────────────────────────────
#  PUT /api/admin/users/<id>/plan
# ─────────────────────────────────────────────────────────────────────
@bp.put("/admin/users/<int:user_id>/plan")
@admin_required
def admin_update_user_plan(user_id: int):
    from db_models import db, User

    body = request.get_json(silent=True) or {}
    new_plan = (body.get("plan") or "").strip().lower()
    if new_plan not in ("free", "pro", "enterprise"):
        return jsonify({"error": "invalid_plan", "status": 400}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user_not_found", "status": 404}), 404
    old = user.plan
    user.plan = new_plan
    user.plan_expires_at = None if new_plan == "free" else datetime.utcnow() + timedelta(days=30)
    db.session.commit()

    log_activity("admin_update_plan",
                 user_id=user.id,
                 details=f"by_admin from {old} to {new_plan}")
    return jsonify({
        "data": {"id": user.id, "plan": user.effective_plan(), "previous": old},
        "status": 200,
    })


# ─────────────────────────────────────────────────────────────────────
#  POST /api/admin/users/<id>/reset-quota
# ─────────────────────────────────────────────────────────────────────
@bp.post("/admin/users/<int:user_id>/reset-quota")
@admin_required
def admin_reset_user_quota(user_id: int):
    from db_models import db, User

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user_not_found", "status": 404}), 404
    user.analyses_count_month        = 0
    user.recommandations_count_month = 0
    user.counters_reset_at           = datetime.utcnow()
    db.session.commit()

    log_activity("admin_reset_quota", user_id=user.id, details="manual reset")
    return jsonify({"data": {"id": user.id, "analyses_count_month": 0,
                             "recommandations_count_month": 0},
                    "status": 200})


# ─────────────────────────────────────────────────────────────────────
#  PUT /api/admin/users/<id>/toggle-active
# ─────────────────────────────────────────────────────────────────────
@bp.put("/admin/users/<int:user_id>/toggle-active")
@admin_required
def admin_toggle_user_active(user_id: int):
    from db_models import db, User

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user_not_found", "status": 404}), 404
    new_state = 0 if (getattr(user, "is_active", 1) or 0) == 1 else 1
    user.is_active = new_state
    db.session.commit()
    log_activity("admin_toggle_active", user_id=user.id,
                 details=f"is_active={new_state}")
    return jsonify({"data": {"id": user.id, "is_active": new_state}, "status": 200})


# ─────────────────────────────────────────────────────────────────────
#  DELETE /api/admin/users/<id>
# ─────────────────────────────────────────────────────────────────────
@bp.delete("/admin/users/<int:user_id>")
@admin_required
def admin_delete_user(user_id: int):
    from db_models import (
        db, User, ZoneAnalysisHistory, ForecastHistory,
        ROIHistory, Analysis, Report, ActivityLog
    )

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user_not_found", "status": 404}), 404
    if (user.role or "").lower() == "admin":
        return jsonify({"error": "cannot_delete_admin", "status": 400}), 400
    email = user.email

    # Manual cascade — SQLite FKs have no CASCADE DELETE by default
    try:
        ZoneAnalysisHistory.query.filter_by(user_id=user_id).delete()
        ForecastHistory.query.filter_by(user_id=user_id).delete()
        ROIHistory.query.filter_by(user_id=user_id).delete()
        Analysis.query.filter_by(user_id=user_id).delete()
        Report.query.filter_by(user_id=user_id).delete()
        ActivityLog.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("admin_delete_user failed for user_id=%s: %s", user_id, exc)
        return jsonify({"error": "delete_failed", "detail": str(exc), "status": 500}), 500

    log_activity("admin_delete_user", details=f"email={email}")
    return jsonify({"data": {"id": user_id, "deleted": True}, "status": 200})


# ─────────────────────────────────────────────────────────────────────
#  GET /api/admin/analytics
# ─────────────────────────────────────────────────────────────────────
@bp.get("/admin/analytics")
@admin_required
def admin_analytics():
    from db_models import db, User, ActivityLog

    today = _today_start()
    start = today - timedelta(days=29)

    reg_per_day = (
        db.session.query(func.date(User.created_at), func.count(User.id))
        .filter(User.created_at >= start)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )
    registrations = {str(d): int(n) for d, n in reg_per_day}

    act_per_day = (
        db.session.query(func.date(ActivityLog.created_at), func.count(ActivityLog.id))
        .filter(ActivityLog.created_at >= start)
        .filter(ActivityLog.action.in_(["analyse_zone", "calcul_roi", "rapport", "forecast"]))
        .group_by(func.date(ActivityLog.created_at))
        .order_by(func.date(ActivityLog.created_at))
        .all()
    )
    daily_activity = {str(d): int(n) for d, n in act_per_day}

    # Fill missing days with 0 so the frontend always gets a 30-point series
    series_labels = []
    series_reg    = []
    series_act    = []
    for i in range(30):
        d = (start + timedelta(days=i)).date().isoformat()
        series_labels.append(d)
        series_reg.append(int(registrations.get(d, 0)))
        series_act.append(int(daily_activity.get(d, 0)))

    # Wilaya names are embedded in activity_log.details as "wilaya:Xxx ..."
    rows = (
        db.session.query(ActivityLog.details)
        .filter(ActivityLog.created_at >= start)
        .all()
    )
    wcount = {}
    for (det,) in rows:
        if not det or "wilaya:" not in det:
            continue
        try:
            part = det.split("wilaya:", 1)[1]
            w = part.split()[0].strip().rstrip(",;|")
            if w:
                wcount[w] = wcount.get(w, 0) + 1
        except Exception:
            continue
    top_wilayas = [
        {"wilaya": k, "count": v}
        for k, v in sorted(wcount.items(), key=lambda x: -x[1])[:10]
    ]

    month = _month_start()
    top_users_raw = (
        db.session.query(ActivityLog.user_id, func.count(ActivityLog.id))
        .filter(ActivityLog.created_at >= month)
        .filter(ActivityLog.user_id != None)  # noqa: E711
        .group_by(ActivityLog.user_id)
        .order_by(func.count(ActivityLog.id).desc())
        .limit(5)
        .all()
    )
    top_users = []
    for uid, n in top_users_raw:
        u = db.session.get(User, uid)
        if u is None:
            continue
        top_users.append({"id": u.id, "name": u.name, "email": u.email, "actions": int(n)})

    total = db.session.query(User).count()
    paid  = db.session.query(User).filter(User.plan.in_(["pro", "enterprise"])).count()
    conv  = round((paid / total * 100), 2) if total else 0.0

    return jsonify({
        "data": {
            "labels":            series_labels,
            "registrations":     series_reg,
            "daily_activity":    series_act,
            "top_wilayas":       top_wilayas,
            "top_active_users":  top_users,
            "total_users":       int(total),
            "paid_users":        int(paid),
            "conversion_rate":   conv,
        },
        "status": 200,
    })


# ─────────────────────────────────────────────────────────────────────
#  GET /api/admin/logs
# ─────────────────────────────────────────────────────────────────────
@bp.get("/admin/logs")
@admin_required
def admin_logs():
    from db_models import db, ActivityLog, ErrorLog, User

    action_type = (request.args.get("type") or "all").strip().lower()
    date_str    = (request.args.get("date") or "").strip()

    activity_q = db.session.query(ActivityLog)
    error_q    = db.session.query(ErrorLog)

    if action_type and action_type != "all":
        activity_q = activity_q.filter(ActivityLog.action == action_type)

    if date_str:
        try:
            d = datetime.fromisoformat(date_str)
            d_end = d + timedelta(days=1)
            activity_q = activity_q.filter(
                ActivityLog.created_at >= d, ActivityLog.created_at < d_end)
            error_q = error_q.filter(
                ErrorLog.created_at >= d, ErrorLog.created_at < d_end)
        except ValueError:
            pass

    activities = activity_q.order_by(ActivityLog.created_at.desc()).limit(50).all()
    errors     = error_q.order_by(ErrorLog.created_at.desc()).limit(50).all()

    # Batch-load users to avoid N+1 queries
    uids = {a.user_id for a in activities if a.user_id} | {e.user_id for e in errors if e.user_id}
    user_lookup = {}
    if uids:
        for u in db.session.query(User).filter(User.id.in_(uids)).all():
            user_lookup[u.id] = {"id": u.id, "name": u.name, "email": u.email}

    return jsonify({
        "data": {
            "activities": [
                {**a.to_dict(), "user": user_lookup.get(a.user_id)}
                for a in activities
            ],
            "errors": [
                {**e.to_dict(), "user": user_lookup.get(e.user_id)}
                for e in errors
            ],
        },
        "status": 200,
    })


# ─────────────────────────────────────────────────────────────────────
#  GET /api/admin/reports
# ─────────────────────────────────────────────────────────────────────
@bp.get("/admin/reports")
@admin_required
def admin_reports():
    from db_models import db, Report, User

    try:
        reports = db.session.query(Report).order_by(Report.created_at.desc()).limit(500).all()
    except Exception:
        reports = []

    # Batch-load users to avoid N+1 queries
    uids = {r.user_id for r in reports if getattr(r, "user_id", None)}
    user_lookup = {}
    if uids:
        for u in db.session.query(User).filter(User.id.in_(uids)).all():
            user_lookup[u.id] = {"id": u.id, "name": u.name, "email": u.email}

    out = []
    by_type, by_wilaya = {}, {}
    for r in reports:
        # Report model has inconsistent column names across migrations — getattr guards both
        rtype  = getattr(r, "type",        None) or getattr(r, "report_type", None) or "—"
        wilaya = getattr(r, "wilaya_name", None) or getattr(r, "wilaya",      None) or "—"
        by_type[rtype]     = by_type.get(rtype, 0) + 1
        by_wilaya[wilaya]  = by_wilaya.get(wilaya, 0) + 1

        out.append({
            "id":         r.id,
            "user":       user_lookup.get(getattr(r, "user_id", None)),
            "type":       rtype,
            "wilaya":     wilaya,
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            "filename":   getattr(r, "filename", None),
        })

    most_type   = max(by_type.items(),   key=lambda x: x[1], default=("—", 0))
    most_wilaya = max(by_wilaya.items(), key=lambda x: x[1], default=("—", 0))

    return jsonify({
        "data": {
            "reports": out,
            "count":   len(out),
            "stats":   {
                "most_generated_type":   {"type":   most_type[0],   "count": most_type[1]},
                "most_requested_wilaya": {"wilaya": most_wilaya[0], "count": most_wilaya[1]},
            },
        },
        "status": 200,
    })