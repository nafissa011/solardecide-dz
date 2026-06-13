"""Routes /api/wilayas"""

import json
from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("wilayas", __name__)


def _engine():
    return current_app.config["DATA_ENGINE"]


@bp.get("/wilayas")
def list_wilayas():
    filters = {
        k: v for k, v in {
            "region":   request.args.get("region"),
            "climate":  request.args.get("climate"),
            "minScore": request.args.get("minScore"),
            "search":   request.args.get("search"),
            "sort":     request.args.get("sort"),
        }.items() if v is not None
    }
    # JSON string is the cache key for DataEngine's LRU cache
    wilayas = _engine().get_wilayas_summary(json.dumps(filters, sort_keys=True))
    return jsonify({"data": wilayas, "total": len(wilayas), "status": 200})


@bp.get("/wilayas/<int:code>")
def get_wilaya(code):
    w = _engine().get_wilaya_detail(code)
    if not w:
        return jsonify({"error": "Wilaya introuvable", "status": 404}), 404
    return jsonify({"data": w, "status": 200})


@bp.get("/wilayas/<int:code>/timeseries")
def get_timeseries(code):
    variable = request.args.get("variable", "GHI")
    ts = _engine().get_monthly_timeseries(code, variable)
    ts["wilaya"] = code
    ts["period"] = "monthly"
    ts["data_source"] = "NASA_POWER"
    return jsonify({"data": ts, "status": 200})


@bp.get("/wilayas/<int:code>/hourly")
def get_hourly(code):
    season = request.args.get("season", "summer")
    profile = _engine().get_hourly_profile(code, season)
    profile["wilaya"] = code
    return jsonify({"data": profile, "status": 200})