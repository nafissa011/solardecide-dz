from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from flask import Blueprint, Response, jsonify, request, send_file

logger = logging.getLogger(__name__)
bp = Blueprint("profile", __name__)

PLAN_LIMITS = {"free": 5, "pro": 50, "enterprise": None}  # None = unlimited


def _current_user():
    try:
        from services.plan_service import get_current_user  # type: ignore
        return get_current_user()
    except Exception:
        return None


def _auth_required():
    u = _current_user()
    if u is None:
        return None, (jsonify({"error": "not_authenticated", "status": 401}), 401)
    return u, None


def _plan_cap(user, requested: Optional[int]) -> Optional[int]:
    """Return the effective LIMIT value after applying the user's plan ceiling."""
    plan = (user.effective_plan() if hasattr(user, "effective_plan") else (user.plan or "free")).lower()
    plan_max = PLAN_LIMITS.get(plan, 5)
    if plan_max is None:
        return requested if (requested and requested > 0) else None
    if requested is None or requested <= 0:
        return plan_max
    return min(int(requested), plan_max)


def _month_start() -> datetime:
    n = datetime.utcnow()
    return datetime(n.year, n.month, 1)


@bp.get("/profile")
def api_profile():
    user, err = _auth_required()
    if err:
        return err

    from db_models import db, ZoneAnalysisHistory, ROIHistory, Analysis, Report

    month = _month_start()
    plan  = user.effective_plan()

    def _safe_count(model, *filters):
        try:
            q = db.session.query(model)
            for f in filters:
                q = q.filter(f)
            return int(q.count())
        except Exception:
            return 0

    # Analyses span two tables — ZoneAnalysisHistory (legacy) and Analysis (Phase 3)
    analyses_month = (
        _safe_count(ZoneAnalysisHistory,
                    ZoneAnalysisHistory.user_id == user.id,
                    ZoneAnalysisHistory.created_at >= month) +
        _safe_count(Analysis,
                    Analysis.user_id == user.id,
                    Analysis.created_at >= month)
    )
    roi_month     = _safe_count(ROIHistory, ROIHistory.user_id == user.id, ROIHistory.created_at >= month)
    reports_month = _safe_count(Report, Report.user_id == user.id, Report.generated_at >= month)

    plan_limit = PLAN_LIMITS.get(plan, 5)
    return jsonify({
        "data": {
            "id":              user.id,
            "name":            user.name,
            "email":           user.email,
            "role":            getattr(user, "role", "user"),
            "plan":            plan,
            "plan_raw":        user.plan,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "is_active":       int(getattr(user, "is_active", 1) or 0),
            "created_at":      user.created_at.isoformat() if user.created_at else None,
            "last_login":      user.last_login.isoformat() if getattr(user, "last_login", None) else None,
            "counters": {
                "analyses_month":                int(analyses_month),
                "roi_month":                     int(roi_month),
                "reports_month":                 int(reports_month),
                "analyses_count_month":          int(user.analyses_count_month or 0),
                "recommandations_count_month":   int(user.recommandations_count_month or 0),
            },
            "plan_limit_history": plan_limit,  # None = unlimited
        },
        "status": 200,
    })


@bp.get("/profile/analyses")
def api_profile_analyses():
    user, err = _auth_required()
    if err:
        return err

    from db_models import db, ZoneAnalysisHistory, Analysis

    cap = _plan_cap(user, request.args.get("limit", type=int))

    # Merge ZoneAnalysisHistory (legacy) and Analysis (Phase 3) into a single list
    rows = []

    try:
        zah = (db.session.query(ZoneAnalysisHistory)
               .filter(ZoneAnalysisHistory.user_id == user.id)
               .order_by(ZoneAnalysisHistory.created_at.desc())
               .limit(cap or 1000)
               .all())
        for r in zah:
            res = None
            try:
                import json as _j
                res = _j.loads(r.result_json) if r.result_json else None
            except Exception:
                res = None
            rows.append({
                "id":          r.id,
                "source":      "zone_analysis",
                "wilaya_code": r.wilaya_code,
                "wilaya":      r.wilaya_name or "—",
                "commune":     (res.get("commune") if isinstance(res, dict) else None) or "—",
                "score":       (res.get("score_commune") or res.get("score") if isinstance(res, dict) else None),
                "ghi":         (res.get("ghi_annuel_kwh_m2") or res.get("ghi") if isinstance(res, dict) else None),
                "date":        r.created_at.isoformat() if r.created_at else None,
            })
    except Exception as exc:
        logger.warning("ZoneAnalysisHistory fetch failed: %s", exc)

    try:
        an = (db.session.query(Analysis)
              .filter(Analysis.user_id == user.id)
              .order_by(Analysis.created_at.desc())
              .limit(cap or 1000)
              .all())
        for a in an:
            # Name is stored as "Wilaya / Commune"
            wilaya, commune = "—", "—"
            try:
                if a.name and "/" in a.name:
                    parts   = a.name.split("/", 1)
                    wilaya  = parts[0].strip() or "—"
                    commune = parts[1].strip() or "—"
                elif a.name:
                    wilaya = a.name
            except Exception:
                pass

            ghi, score = None, None
            try:
                from utils.data_service import get_commune_analysis  # type: ignore
                if commune and commune != "—":
                    rs = get_commune_analysis(wilaya, commune)
                    if rs:
                        ghi   = rs.get("ghi_annuel_kwh_m2")
                        score = rs.get("score_commune")
            except Exception:
                pass

            rows.append({
                "id":          a.id,
                "source":      "saved",
                "wilaya_code": a.wilaya_code,
                "wilaya":      wilaya,
                "commune":     commune,
                "score":       score,
                "ghi":         ghi,
                "capacity_mw": a.capacity_mw,
                "date":        a.created_at.isoformat() if a.created_at else None,
            })
    except Exception as exc:
        logger.warning("Analysis fetch failed: %s", exc)

    rows.sort(key=lambda x: x.get("date") or "", reverse=True)
    if cap is not None:
        rows = rows[:cap]

    return jsonify({
        "data":          rows,
        "count":         len(rows),
        "limit_applied": cap,
        "plan":          user.effective_plan(),
        "status":        200,
    })


@bp.get("/profile/roi-history")
def api_profile_roi():
    user, err = _auth_required()
    if err:
        return err

    from db_models import db, ROIHistory

    cap = _plan_cap(user, request.args.get("limit", type=int))

    q = (db.session.query(ROIHistory)
         .filter(ROIHistory.user_id == user.id)
         .order_by(ROIHistory.created_at.desc()))
    if cap is not None:
        q = q.limit(cap)

    out = []
    for r in q.all():
        out.append({
            "id":            r.id,
            "wilaya":        r.wilaya_name or "—",
            "wilaya_code":   r.wilaya_code,
            "capacity_kwc":  round(float(r.capacity_mw or 0.0) * 1000.0, 2),
            "capacity_mw":   r.capacity_mw,
            "scenario":      r.scenario,
            "roi_pct":       round(float(r.irr or 0.0) * 100.0, 2) if r.irr else None,
            "irr":           r.irr,
            "npv":           r.npv,
            "capex":         r.capex,
            "payback_years": r.payback_years,
            "lcoe":          r.lcoe_usd_kwh,
            "date":          r.created_at.isoformat() if r.created_at else None,
        })
    return jsonify({
        "data":          out,
        "count":         len(out),
        "limit_applied": cap,
        "plan":          user.effective_plan(),
        "status":        200,
    })


@bp.get("/profile/reports")
def api_profile_reports():
    user, err = _auth_required()
    if err:
        return err

    from db_models import db, Report

    cap = _plan_cap(user, request.args.get("limit", type=int))

    q = (db.session.query(Report)
         .filter(Report.user_id == user.id)
         .order_by(Report.generated_at.desc()))
    if cap is not None:
        q = q.limit(cap)

    out = []
    for r in q.all():
        out.append({
            "id":           r.id,
            "title":        r.title,
            "report_type":  r.report_type,
            "wilaya":       r.wilaya_name,
            "capacity_mw":  r.capacity_mw,
            "date":         r.generated_at.isoformat() if r.generated_at else None,
            "has_pdf":      bool(r.pdf_path and os.path.exists(r.pdf_path)),
            "download_url": f"/api/profile/reports/{r.id}/download",
        })
    return jsonify({
        "data":   out,
        "count":  len(out),
        "plan":   user.effective_plan(),
        "status": 200,
    })


@bp.get("/profile/reports/<int:report_id>/download")
def api_profile_report_download(report_id: int):
    user, err = _auth_required()
    if err:
        return err

    from db_models import db, Report

    r = db.session.get(Report, report_id)
    if r is None or r.user_id != user.id:
        return jsonify({"error": "report_not_found", "status": 404}), 404
    if not r.pdf_path or not os.path.exists(r.pdf_path):
        return jsonify({"error": "pdf_unavailable", "status": 410}), 410

    safe     = (r.wilaya_name or "report").replace(" ", "_")
    filename = f"report_{safe}_{r.id}.pdf"
    return send_file(r.pdf_path, mimetype="application/pdf",
                     as_attachment=True, download_name=filename)