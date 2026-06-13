"""Routes /api/decision"""

from flask import Blueprint, current_app, jsonify
from utils import get_verdict, build_risks

bp = Blueprint("decision", __name__)


@bp.get("/decision/<zone_id>")
def get_decision(zone_id):
    engine = current_app.config["DATA_ENGINE"]
    zone = engine.get_zone_by_id(zone_id)

    if not zone:
        # Fallback : chercher par wilaya_code seul
        try:
            code = int(zone_id.split("_")[0])
            zones = engine.get_zones()
            zone = next((z for z in zones if int(z["wilaya_code"]) == code), None)
        except (ValueError, IndexError):
            pass

    if not zone:
        return jsonify({"error": "Zone introuvable", "status": 404}), 404

    verdict, confidence, actions = get_verdict(zone)
    risks = build_risks(zone)

    # Rationale (points forts)
    strengths = []
    if zone.get("mean_ghi", 0) > 0.3:
        strengths.append(f"Ensoleillement exceptionnel (GHI moyen : {zone['mean_ghi']:.3f} kWh/m²/h)")
    if zone.get("mean_clearness", 0) > 0.6:
        strengths.append(f"Indice de clarté élevé ({zone['mean_clearness']:.2f})")
    if zone.get("score", 0) >= 75:
        strengths.append(f"Score solaire composite : {zone['score']:.1f}/100")
    if not strengths:
        strengths.append("Potentiel solaire à confirmer par mesure terrain")

    return jsonify({
        "data": {
            "zone":       zone,
            "verdict":    verdict,
            "confidence": confidence,
            "strengths":  strengths,
            "risks":      risks,
            "actions":    actions,
        },
        "status": 200,
    })
