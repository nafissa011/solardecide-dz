"""Routes /api/zones"""

from flask import Blueprint, current_app, jsonify, request
from config import CAPACITY_FACTOR

bp = Blueprint("zones", __name__)


def _engine():
    return current_app.config["DATA_ENGINE"]


@bp.get("/zones")
def list_zones():
    wilaya = request.args.get("wilaya")
    zones = _engine().get_zones(wilaya_name=wilaya)
    return jsonify({"data": zones, "total": len(zones), "status": 200})


@bp.get("/zones/<zone_id>")
def get_zone(zone_id):
    zone = _engine().get_zone_by_id(zone_id)
    if not zone:
        return jsonify({"error": "Zone introuvable", "status": 404}), 404
    return jsonify({"data": zone, "status": 200})
