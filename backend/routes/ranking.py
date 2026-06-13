import json
import time
import logging
import numpy as np
from flask import Blueprint, current_app, jsonify, request

from schemas import ZoneRecommendationRequest, ZoneRecommendationResponse
from services import RecommendationService
from db_models import db, ZoneAnalysisHistory

logger = logging.getLogger(__name__)
bp = Blueprint("ranking", __name__)


def _get_user_id():
    """Extract user_id from auth cookie, Authorization header, or request body."""
    token = request.cookies.get("auth_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        body = request.get_json(silent=True) or {}
        try:
            return int(body.get('user_id')) if body.get('user_id') else None
        except (ValueError, TypeError):
            return None
    try:
        import jwt
        from config import JWT_SECRET, JWT_ALGORITHM
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


@bp.get("/ranking")
def get_ranking():
    """GET /api/ranking?region=&climate=&minScore=&search=&sort=score|ghi|potential"""
    start_time = time.time()

    try:
        engine  = current_app.config["DATA_ENGINE"]
        wilayas = engine.get_wilayas_summary()

        region    = request.args.get("region")
        climate   = request.args.get("climate")
        min_score = request.args.get("minScore")
        search    = request.args.get("search")
        sort      = request.args.get("sort")

        if region:
            wilayas = [w for w in wilayas if w.get("region") == region]
        if climate:
            wilayas = [w for w in wilayas if w.get("climate") == climate]
        if min_score:
            ms = float(min_score)
            wilayas = [w for w in wilayas if w.get("score", 0) >= ms]
        if search:
            q = search.lower()
            wilayas = [w for w in wilayas if q in w.get("wilaya_name", "").lower()]
        if sort == "score":
            wilayas.sort(key=lambda x: x.get("score", 0), reverse=True)
        elif sort == "ghi":
            wilayas.sort(key=lambda x: x.get("mean_ghi", 0), reverse=True)
        elif sort == "potential":
            wilayas.sort(key=lambda x: x.get("potential_mw", 0), reverse=True)

        proc_time = (time.time() - start_time) * 1000
        logger.info(f"Ranking returned {len(wilayas)} wilayas in {proc_time:.2f}ms")

        return jsonify({
            "data":               wilayas,
            "status":             200,
            "processing_time_ms": round(proc_time, 2)
        })

    except Exception as e:
        logger.error(f"Ranking error: {e}", exc_info=True)
        return jsonify({"error": str(e), "status": 500}), 500


@bp.get("/ranking/<int:wilaya_code>")
def get_wilaya_ranking(wilaya_code: int):
    """GET /api/ranking/<wilaya_code> — top 10 zones + statistics for one wilaya."""
    start_time = time.time()

    try:
        if not 1 <= wilaya_code <= 58:
            return jsonify({"error": f"Invalid wilaya code: {wilaya_code}. Must be 1-58.", "status": 400}), 400

        engine = current_app.config["DATA_ENGINE"]
        wilaya = engine.get_wilaya_detail(wilaya_code)
        if not wilaya:
            return jsonify({"error": f"Wilaya {wilaya_code} not found", "status": 404}), 404

        zones = engine.get_zones(wilaya_name=wilaya.get("wilaya_name"))

        rec_service: RecommendationService = current_app.config.get("RECOMMENDATION_SERVICE")
        if rec_service:
            scored_zones = rec_service.get_wilaya_zones_sorted(wilaya_code)
        else:
            # RecommendationService unavailable — compute scores inline
            scored_zones = []
            for zone in zones:
                mean_ghi       = float(zone.get("mean_ghi", 0))
                peak_ghi       = float(zone.get("peak_ghi", 0))
                sunshine_frac  = float(zone.get("sunshine_frac", 0))
                mean_clearness = float(zone.get("mean_clearness", 0))
                variability    = float(zone.get("variability", 0))

                # Composite score: GHI(35%) + Peak GHI(15%) + Sunshine(20%) + Clearness(15%) + Low Variability(15%)
                score = (
                    (mean_ghi / 0.4)                    * 0.35 +
                    (peak_ghi / 1.2)                    * 0.15 +
                    sunshine_frac                        * 0.20 +
                    mean_clearness                       * 0.15 +
                    (1.0 - min(variability / 0.15, 1.0)) * 0.15
                ) * 100
                zone["score"] = round(score, 2)
                zone["recommendation"] = "build" if score >= 80 else "study" if score >= 60 else "wait"
                scored_zones.append(zone)

            scored_zones.sort(key=lambda z: z.get("score", 0), reverse=True)
            for i, z in enumerate(scored_zones):
                z["rank"] = i + 1

        top10 = []
        for z in scored_zones[:10]:
            mean_ghi_hourly = float(z.get("mean_ghi", 0))
            top10.append({
                "rank":             z.get("rank", 0),
                "commune_name":     z.get("commune_name", ""),
                "score":            z.get("score", 0),
                "mean_ghi_hourly":  round(mean_ghi_hourly, 3),
                "mean_ghi_annual":  round(mean_ghi_hourly * 8760, 0),
                "mean_dni":         round(z.get("mean_dni", 0), 3),
                "mean_dhi":         round(z.get("mean_dhi", 0), 3),
                "mean_t2m":         round(z.get("mean_t2m", 0), 1),
                "mean_clearness":   round(z.get("mean_clearness", 0), 2),
                "latitude":         z.get("latitude", 0),
                "longitude":        z.get("longitude", 0),
                # potential_mw: annual GHI × 18% panel efficiency × 40 km² / 1000
                "potential_mw":     round((mean_ghi_hourly * 8760 * 0.18 * 40) / 1000, 0),
                "variability":      round(z.get("variability", 0), 2),
                "recommendation":   z.get("recommendation", "study"),
                "climate":          z.get("climate", ""),
            })

        scores = [z.get("score", 0) for z in scored_zones]
        stats = {
            "total_zones":    len(scored_zones),
            "excellent":      sum(1 for s in scores if s >= 80),
            "good":           sum(1 for s in scores if 60 <= s < 80),
            "study_required": sum(1 for s in scores if 40 <= s < 60),
            "poor":           sum(1 for s in scores if s < 40),
            "avg_score":      round(np.mean(scores), 1) if scores else 0,
            "median_score":   round(np.median(scores), 1) if scores else 0,
        }

        proc_time = (time.time() - start_time) * 1000
        logger.info(f"Wilaya ranking complete: {len(top10)} zones, {stats['excellent']} excellent, {proc_time:.2f}ms")

        return jsonify({
            "data": {
                "wilaya":          wilaya,
                "communes_count":  len(scored_zones),
                "communes":        top10,
                "avg_ghi":         round(wilaya.get("mean_ghi", 0) * 8760, 0),
                "total_score":     round(wilaya.get("score", 0), 1),
                "statistics":      stats,
                "processing_time_ms": round(proc_time, 2),
            },
            "status": 200,
        })

    except Exception as e:
        logger.error(f"Wilaya ranking error: {e}", exc_info=True)
        return jsonify({"error": str(e), "status": 500}), 500


@bp.post("/ranking/recommend")
def recommend_zones():
    """
    POST /api/ranking/recommend
    Body: { "wilaya_code": 33, "target_capacity_mw": 100.0, "objective": "utility|industrial|residential" }

    Returns ranked zones that cumulatively meet the target capacity.
    """
    start_time = time.time()

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON", "status": 400}), 400

        req = ZoneRecommendationRequest(**data)

        rec_service: RecommendationService = current_app.config.get("RECOMMENDATION_SERVICE")
        if not rec_service:
            logger.error("RecommendationService not initialized")
            return jsonify({"error": "Service unavailable", "status": 503}), 503

        response = rec_service.recommend_zones_for_capacity(
            wilaya_code=req.wilaya_code,
            target_capacity_mw=req.target_capacity_mw,
            objective=req.objective or "utility"
        )

        proc_time   = (time.time() - start_time) * 1000
        result_dict = response.dict()

        logger.info(f"Recommendation complete: {len(response.recommended_zones)} zones in {proc_time:.2f}ms")

        user_id = _get_user_id()
        if user_id:
            try:
                record = ZoneAnalysisHistory(
                    user_id=user_id,
                    wilaya_code=req.wilaya_code,
                    wilaya_name=result_dict.get('wilaya_name', ''),
                    target_capacity_mw=req.target_capacity_mw,
                    objective=req.objective or 'utility',
                    result_json=json.dumps(result_dict),
                    processing_time_ms=round(proc_time, 2),
                )
                db.session.add(record)
                db.session.commit()
                result_dict['history_id'] = record.id
            except Exception as db_err:
                logger.warning(f"Could not save zone analysis to history: {db_err}")
                db.session.rollback()

        return jsonify({
            "data":               result_dict,
            "status":             200,
            "processing_time_ms": round(proc_time, 2)
        })

    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        return jsonify({"error": str(ve), "status": 400}), 400
    except Exception as e:
        logger.error(f"Recommendation error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "status": 500}), 500