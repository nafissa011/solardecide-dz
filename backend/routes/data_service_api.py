"""
REST wrapper of utils.data_service

All routes are mounted under /api/data-service/* and return the same dicts
exposed by utils.data_service.<function>().  Front-end pages must consume
THIS blueprint (or the JS helper `frontend/js/data-service.js` which wraps
these routes 1-to-1) — never another data source.

Endpoints
─────────────────────────────────────────────────────────────────────────────
    GET /api/data-service/health
    GET /api/data-service/wilayas                       (lightweight list)
    GET /api/data-service/wilaya/<nom>                  (get_wilaya_stats)
    GET /api/data-service/commune/<nom_wilaya>/<commune>(get_commune_stats)
    GET /api/data-service/national                      (get_national_stats)
    GET /api/data-service/top?metric=&n=                (get_top_wilayas)
    GET /api/data-service/monthly-ghi/<nom>             (get_monthly_ghi)
    GET /api/data-service/communes/<nom_wilaya>         (list of communes)
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from utils.data_service import (
    get_climate_zones,
    get_commune_analysis,
    get_commune_monthly_vs_national,
    get_commune_stats,
    get_monthly_ghi,
    get_national_stats,
    get_ranking,
    get_regions_breakdown,
    get_top_wilayas,
    get_wilaya_extras,
    get_wilaya_monthly,
    get_wilaya_of_the_week,
    get_wilaya_radar,
    get_wilaya_stats,
    is_ready,
    list_communes,
    list_wilayas,
)

logger = logging.getLogger(__name__)

bp = Blueprint("data_service_api", __name__)


def _err(message: str, status: int = 404):
    return jsonify({"error": message, "status": status}), status


@bp.get("/data-service/health")
def health():
    return jsonify(is_ready())


@bp.get("/data-service/wilayas")
def api_wilayas():
    data = list_wilayas()
    return jsonify({"data": data, "total": len(data), "status": 200, "source": "data_service"})


@bp.get("/data-service/wilaya/<path:nom>")
def api_wilaya_stats(nom: str):
    data = get_wilaya_stats(nom)
    if data is None:
        return _err(f"Wilaya '{nom}' inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/data-service/commune/<path:nom_wilaya>/<path:commune>")
def api_commune_stats(nom_wilaya: str, commune: str):
    data = get_commune_stats(nom_wilaya, commune)
    if data is None:
        return _err(f"Commune '{commune}' (wilaya '{nom_wilaya}') inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/data-service/national")
def api_national():
    return jsonify({"data": get_national_stats(), "status": 200, "source": "data_service"})


@bp.get("/data-service/top")
def api_top():
    metric = (request.args.get("metric") or "score_composite").strip()
    try:
        n = int(request.args.get("n", 10))
    except (TypeError, ValueError):
        n = 10
    return jsonify({
        "data":   get_top_wilayas(metric=metric, n=n),
        "metric": metric,
        "n":      n,
        "status": 200,
        "source": "data_service",
    })


@bp.get("/data-service/monthly-ghi/<path:nom>")
def api_monthly_ghi(nom: str):
    data = get_monthly_ghi(nom)
    if data is None:
        return _err(f"Wilaya '{nom}' inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/data-service/communes/<path:nom_wilaya>")
def api_communes(nom_wilaya: str):
    data = list_communes(nom_wilaya)
    if data is None:
        return _err(f"Wilaya '{nom_wilaya}' inconnue")
    return jsonify({"data": data, "total": len(data), "status": 200, "source": "data_service"})


# ───────────────────────────────────────────────────────────────────────
#  Phase 3 — landing-page helpers
# ───────────────────────────────────────────────────────────────────────

@bp.get("/data-service/climate-zones")
def api_climate_zones():
    data = get_climate_zones()
    return jsonify({"data": data, "total": len(data), "status": 200, "source": "data_service"})


@bp.get("/data-service/wilaya-of-the-week")
def api_wilaya_of_the_week():
    data = get_wilaya_of_the_week()
    if data is None:
        return _err("Insufficient data for the latest week")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


# ───────────────────────────────────────────────────────────────────────
#  Phase 3 — short URL aliases requested by the landing page spec
# ───────────────────────────────────────────────────────────────────────
# Same data as /api/data-service/* but on the canonical paths the user asked
# for in Phase 3:  /api/national-stats, /api/wilaya-du-jour, /api/analyses-count
# ───────────────────────────────────────────────────────────────────────

@bp.get("/national-stats")
def api_national_stats_alias():
    """Phase 3 alias — returns the same payload as /data-service/national."""
    data = get_national_stats()
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/wilaya-du-jour")
def api_wilaya_du_jour():
    """Phase 3 alias — returns the same payload as /data-service/wilaya-of-the-week."""
    data = get_wilaya_of_the_week()
    if data is None:
        return _err("Insufficient data for the latest week")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


# ──────────────────────────────────────────────────────────────────────
#  Phase 3 — ranking page endpoints
# ──────────────────────────────────────────────────────────────────────

@bp.get("/classement")
def api_classement_v3():
    """
    Phase 3 — unified ranking endpoint.
        ?metric=score|ghi|potentiel
        ?limit=58 (default)
        ?region=Centre|Est|Ouest|Sud-Est|Sud-Ouest|Grand Sud
        ?climate=Saharan|Arid|Semi-Arid|Coastal|Highland
        ?search=...
    Replaces the legacy /api/classement (the legacy blueprint registers
    AFTER data_service so this one wins).
    """
    metric = (request.args.get("metric") or "score").strip()
    try:
        limit = int(request.args.get("limit", 58))
    except (TypeError, ValueError):
        limit = 58
    region  = request.args.get("region") or None
    climate = request.args.get("climate") or None
    search  = request.args.get("search") or None
    rows = get_ranking(metric=metric, limit=limit, region=region, climate=climate, search=search)
    return jsonify({
        "data":   rows,
        "total":  len(rows),
        "metric": metric,
        "filters": {"region": region, "climate": climate, "search": search},
        "status": 200,
        "source": "data_service",
    })


@bp.get("/wilaya-monthly/<path:nom>")
def api_wilaya_monthly(nom: str):
    """
    Phase 3 — monthly profile for the Wilaya dashboard.
    Returns 12 values for GHI / DNI / T2M / WS10M / KT plus annual averages.
    """
    data = get_wilaya_monthly(nom)
    if data is None:
        return _err(f"Wilaya '{nom}' inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/wilaya-extras/<path:nom>")
def api_wilaya_extras(nom: str):
    """Phase 3 — infrastructure box indicators (cloudy days, instability, ...)."""
    data = get_wilaya_extras(nom)
    if data is None:
        return _err(f"Wilaya '{nom}' inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/wilaya-radar/<path:nom>")
def api_wilaya_radar(nom: str):
    """Phase 3 — 5-axis radar (normalised 0-100 on national min/max)."""
    data = get_wilaya_radar(nom)
    if data is None:
        return _err(f"Wilaya '{nom}' inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/wilaya-pdf/<path:nom>")
def api_wilaya_pdf(nom: str):
    """
    Phase 3 — 1-page PDF "Fiche wilaya".
    Plan-gated to Pro/Enterprise (action.wilaya_pdf).
    Uses WeasyPrint if available, else falls back to ReportLab.
    """
    from services.plan_service import check_plan

    @check_plan("pro", feature="action.wilaya_pdf")
    def _gated():
        stats   = get_wilaya_stats(nom)
        monthly = get_wilaya_monthly(nom)
        extras  = get_wilaya_extras(nom)
        if stats is None:
            return _err(f"Wilaya '{nom}' inconnue")

        from utils.wilaya_pdf import build_wilaya_pdf
        try:
            pdf_bytes = build_wilaya_pdf(stats, monthly, extras)
        except Exception as exc:  # noqa: BLE001
            logger.exception("PDF generation failed: %s", exc)
            return jsonify({"error": "pdf_generation_failed", "detail": str(exc)}), 500

        from flask import Response
        safe_name = stats["wilaya_name"].replace(" ", "_")
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="fiche-{safe_name}.pdf"',
                "Cache-Control": "no-store",
            },
        )

    return _gated()


@bp.get("/wilaya-stats/<path:nom>")
def api_wilaya_stats_short(nom: str):
    """Phase 3 alias — same payload as /api/data-service/wilaya/<nom>."""
    data = get_wilaya_stats(nom)
    if data is None:
        return _err(f"Wilaya '{nom}' inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/repartition-regions")
def api_repartition_v3():
    """Phase 3 — region breakdown using the PRIMARY_REGION map."""
    data = get_regions_breakdown()
    return jsonify({"data": data, "total": len(data), "status": 200, "source": "data_service"})


@bp.get("/regions")
def api_regions_list():
    """Lightweight list of region names (for the UI filter)."""
    from utils.data_service import REGIONS
    return jsonify({
        "data":   list(REGIONS.keys()),
        "status": 200,
        "source": "data_service",
    })


@bp.get("/export-csv-classement")
def api_export_csv_classement():
    """
    Phase 3 — CSV export of the full ranking.
    Plan-gated to Pro/Enterprise; the @check_plan middleware returns
    402 plan_required for free users.
    """
    from services.plan_service import check_plan

    @check_plan("pro", feature="action.export_csv_ranking")
    def _gated():
        import csv
        import io
        from flask import Response

        rows = get_ranking(metric="score", limit=58)
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "rank", "wilaya_code", "wilaya_name", "region", "climate", "climate_label",
            "latitude", "longitude", "n_communes",
            "ghi_annuel_kwh_m2", "potentiel_mw", "score_composite",
            "delta_vs_national_pct",
        ])
        for r in rows:
            writer.writerow([
                r.get("rank"), r.get("wilaya_code"), r.get("wilaya_name"),
                r.get("region"), r.get("climate"), r.get("climate_label"),
                r.get("latitude"), r.get("longitude"), r.get("n_communes"),
                r.get("ghi_annuel_kwh_m2"), r.get("potentiel_mw"),
                r.get("score_composite"), r.get("delta_vs_national"),
            ])
        csv_text = buf.getvalue()
        return Response(
            csv_text,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=solardecide-classement.csv",
                "Cache-Control": "no-store",
            },
        )

    return _gated()


@bp.get("/analyses-count")
def api_analyses_count():
    """
    Phase 3 — total number of analyses logged in SQLite across the three
    history tables (zone_analysis_history, forecast_history, roi_history).
    Read-only: anonymous users may access it (the landing page is public).
    """
    try:
        from db_models import db, ZoneAnalysisHistory, ForecastHistory, ROIHistory, Analysis
        zone_n     = db.session.query(ZoneAnalysisHistory).count()
        forecast_n = db.session.query(ForecastHistory).count()
        roi_n      = db.session.query(ROIHistory).count()
        try:
            saved_n = db.session.query(Analysis).count()
        except Exception:
            saved_n = 0
        total = int(zone_n + forecast_n + roi_n + saved_n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyses-count fallback (SQLite unreachable): %s", exc)
        zone_n = forecast_n = roi_n = saved_n = 0
        total = 0
    return jsonify({
        "data": {
            "total_analyses": total,
            "by_type": {
                "zone_analysis":  int(zone_n),
                "forecast":       int(forecast_n),
                "roi":            int(roi_n),
                "saved_analysis": int(saved_n),
            },
        },
        "status": 200,
        "source": "sqlite",
    })


# ──────────────────────────────────────────────────────────────────────
#  Phase 3 — Zone Analysis (per-commune)
# ──────────────────────────────────────────────────────────────────────

@bp.get("/commune-stats/<path:nom_wilaya>/<path:commune>")
def api_commune_stats_phase3(nom_wilaya: str, commune: str):
    """
    Phase 3 — full commune payload for the Zone Analysis page :
      • base stats (GHI, DNI, T2M, WS10M, RH2M, KT, PRECIP, …)
      • LOCAL composite score (recomputed per commune)
      • risk indicators (climatic risk, stability %, clearness label, accessibility)
      • why_this_zone + panel_recommendation (climate-specific text)
    """
    data = get_commune_analysis(nom_wilaya, commune)
    if data is None:
        return _err(f"Commune '{commune}' (wilaya '{nom_wilaya}') inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


@bp.get("/commune-monthly/<path:nom_wilaya>/<path:commune>")
def api_commune_monthly(nom_wilaya: str, commune: str):
    """
    Phase 3 — monthly GHI of the commune VS national monthly average,
    plus estimated monthly production (MWh) for a 10 000 m² @ 20% farm.
    """
    data = get_commune_monthly_vs_national(nom_wilaya, commune)
    if data is None:
        return _err(f"Commune '{commune}' (wilaya '{nom_wilaya}') inconnue")
    return jsonify({"data": data, "status": 200, "source": "data_service"})


# ──────────────────────────────────────────────────────────────────────
#  Phase 3 — Save analysis (plan-gated Pro+)
# ──────────────────────────────────────────────────────────────────────

@bp.post("/save-analysis")
def api_save_analysis():
    """
    Save a zone analysis snapshot in SQLite. Pro/Enterprise only.

    Body JSON :
        { "wilaya": "Adrar", "commune": "Adrar Centre",
          "score":  72.5,    "ghi":     6.41,
          "note":   "..."  (optional) }
    """
    from services.plan_service import check_plan

    @check_plan("pro", feature="action.save_analysis")
    def _gated():
        payload = request.get_json(silent=True) or {}
        wilaya  = (payload.get("wilaya")  or "").strip()
        commune = (payload.get("commune") or "").strip()
        if not wilaya or not commune:
            return jsonify({"error": "wilaya and commune required", "status": 400}), 400

        # Validate against dataset
        validated = get_commune_analysis(wilaya, commune)
        if validated is None:
            return _err(f"Commune '{commune}' (wilaya '{wilaya}') inconnue", 404)

        # Persist into SQLite using existing Analysis model
        try:
            from db_models import db, Analysis
            from services.plan_service import get_current_user
            user = get_current_user()
            user_id = user.id if user else None
            if not user_id:
                return jsonify({"error": "unauthorized", "status": 401}), 401

            a = Analysis(
                user_id     = user_id,
                name        = f"{wilaya} / {commune}",
                capacity_mw = float(validated.get("potentiel_mw") or 0.0),
                wilaya_code = str(validated.get("wilaya_code") or ""),
            )
            db.session.add(a)
            db.session.commit()
            # Phase 3 — admin activity log
            try:
                from services.admin_service import log_activity
                log_activity("analyse_zone", user_id=user_id,
                             details=f"wilaya:{wilaya} commune:{commune}")
            except Exception:  # noqa: BLE001
                pass
            return jsonify({
                "data": {
                    "id":         a.id,
                    "wilaya":     wilaya,
                    "commune":    commune,
                    "score":      float(payload.get("score") or validated.get("score_commune") or 0.0),
                    "ghi":        float(payload.get("ghi")   or validated.get("ghi_annuel_kwh_m2") or 0.0),
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "message":    "Analyse sauvegardée dans votre historique",
                },
                "status": 201,
                "source": "sqlite",
            }), 201
        except Exception as exc:  # noqa: BLE001
            logger.exception("save-analysis failed: %s", exc)
            return jsonify({"error": "save_failed", "detail": str(exc), "status": 500}), 500

    return _gated()
