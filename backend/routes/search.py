"""Routes /api/search"""

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("search", __name__)


@bp.get("/search")
def search():
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"data": [], "status": 200})

    engine = current_app.config["DATA_ENGINE"]
    wilayas, zones = engine.get_search_data()

    results = []

    for w in wilayas:
        name = (w.get("wilaya_name") or "").lower()
        region = (w.get("region") or "").lower()
        if q in name or q in region:
            results.append({
                "type":     "wilaya",
                "id":       str(w["wilaya_code"]),
                "name":     w["wilaya_name"],
                "subtitle": f"{w.get('region', '')} • Score: {w.get('score', 0):.0f}",
            })

    for z in zones[:200]:  # cap zone scan for performance
        zone_name = (z.get("commune_name") or "").lower()
        wilaya_n  = (z.get("wilaya_name") or "").lower()
        if q in zone_name or q in wilaya_n:
            results.append({
                "type":     "zone",
                "id":       z.get("id", ""),
                "name":     z["commune_name"],
                "subtitle": f"{z.get('wilaya_name', '')} • GHI: {z.get('mean_ghi', 0):.3f}",
            })

    return jsonify({"data": results[:20], "status": 200})