import json
import time
import logging
from flask import Blueprint, current_app, jsonify, request

from schemas import ZoneRecommendationRequest
from services import RecommendationService
from services.zone_model_service import ZoneModelService
from db_models import db, ZoneAnalysisHistory

logger = logging.getLogger(__name__)
bp = Blueprint("recommendation", __name__)


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


@bp.post("/recommendation/deterministic")
def deterministic_recommendation():
    """
    POST /api/recommendation/deterministic
    Body: { "wilaya_code": 33, "target_capacity_mw": 100.0 }
    """
    start_time = time.time()

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON", "status": 400}), 400

        wilaya_code        = data.get('wilaya_code')
        target_capacity_mw = data.get('target_capacity_mw')

        if wilaya_code is None:
            return jsonify({"error": "wilaya_code is required", "status": 400}), 400
        if target_capacity_mw is None:
            return jsonify({"error": "target_capacity_mw is required", "status": 400}), 400

        req = ZoneRecommendationRequest(
            wilaya_code=wilaya_code,
            target_capacity_mw=target_capacity_mw,
            objective="utility"
        )

        rec_service: RecommendationService = current_app.config.get("RECOMMENDATION_SERVICE")
        if not rec_service:
            logger.error("RecommendationService not initialized")
            return jsonify({"error": "Service unavailable", "status": 503}), 503

        response    = rec_service.component.recommend_zones(req)
        proc_time   = (time.time() - start_time) * 1000
        result_dict = response.dict()

        logger.info(f"Deterministic recommendation complete: {len(response.recommended_zones)} zones in {proc_time:.2f}ms")

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

        return jsonify({"data": result_dict, "status": 200, "processing_time_ms": round(proc_time, 2)})

    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        return jsonify({"error": str(ve), "status": 400}), 400
    except Exception as e:
        logger.error(f"Deterministic recommendation error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "status": 500}), 500


@bp.post("/recommendation/ml")
def ml_recommendation():
    """
    POST /api/recommendation/ml
    Body: { "wilaya_code": 33, "target_capacity_mw": 100.0, "approach": "old_approach|new_approach", "model_name": "random_forest" }
    """
    start_time = time.time()

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON", "status": 400}), 400

        wilaya_code        = data.get('wilaya_code')
        target_capacity_mw = data.get('target_capacity_mw')
        approach           = data.get('approach')
        model_name         = data.get('model_name')

        if wilaya_code is None:
            return jsonify({"error": "wilaya_code is required", "status": 400}), 400
        if target_capacity_mw is None:
            return jsonify({"error": "target_capacity_mw is required", "status": 400}), 400
        if approach is None:
            return jsonify({"error": "approach is required (old_approach or new_approach)", "status": 400}), 400
        if approach not in ('old_approach', 'new_approach'):
            return jsonify({"error": "approach must be 'old_approach' or 'new_approach'", "status": 400}), 400
        if model_name is None:
            return jsonify({"error": "model_name is required", "status": 400}), 400
        if not (1 <= wilaya_code <= 58):
            return jsonify({"error": f"Invalid wilaya code: {wilaya_code}. Must be 1-58.", "status": 400}), 400
        if target_capacity_mw <= 0:
            return jsonify({"error": f"Invalid capacity: {target_capacity_mw}. Must be > 0.", "status": 400}), 400

        model_service: ZoneModelService = current_app.config.get("ZONE_MODEL_SERVICE")
        data_engine                     = current_app.config.get("DATA_ENGINE")

        if not model_service:
            logger.error("ZoneModelService not initialized")
            return jsonify({"error": "Model service unavailable", "status": 503}), 503
        if not data_engine:
            logger.error("DataEngine not initialized")
            return jsonify({"error": "Data engine unavailable", "status": 503}), 503

        wilaya_data = data_engine.get_wilaya_detail(wilaya_code)
        if not wilaya_data:
            return jsonify({"error": f"Wilaya {wilaya_code} not found", "status": 404}), 404

        zones = data_engine.get_zones(wilaya_name=wilaya_data['wilaya_name'])
        if not zones:
            logger.warning(f"No zones found for wilaya {wilaya_code}")
            return jsonify({
                "wilaya_code":      wilaya_code,
                "wilaya_name":      wilaya_data['wilaya_name'],
                "wilaya_score":     0.0,
                "target_capacity_mw": target_capacity_mw,
                "recommended_zones": [],
                "summary_statistics": {
                    'total_zones_available':  0,
                    'zones_selected':         0,
                    'cumulative_potential_mw': 0.0,
                    'average_score':          0.0,
                    'best_zone':              None,
                },
                "processing_time_ms": (time.time() - start_time) * 1000,
            }), 200

        scored_zones = []
        for zone in zones:
            try:
                score        = model_service.predict_zone_score(approach, model_name, zone)
                zone['score'] = max(0.0, min(100.0, float(score)))  # clamp to [0, 100]
            except Exception as e:
                logger.warning(f"ML scoring failed for zone {zone.get('commune_name')}: {e}")
                # Fall back to deterministic scoring for this zone
                from ai_zone_recommendation import ZoneRecommendationComponent
                zone['score'] = ZoneRecommendationComponent(data_engine)._compute_zone_score(zone)
            scored_zones.append(zone)

        scored_zones.sort(key=lambda z: z['score'], reverse=True)
        for i, zone in enumerate(scored_zones):
            zone['rank'] = i + 1

        # Select zones greedily until target capacity is met; split the last zone if needed
        selected_zones      = []
        cumulative_capacity = 0.0

        for zone in scored_zones:
            zone_capacity = zone.get('potential_mw', 1.0)
            if cumulative_capacity + zone_capacity <= target_capacity_mw:
                selected_zones.append(zone)
                cumulative_capacity += zone_capacity
            else:
                remaining = target_capacity_mw - cumulative_capacity
                if remaining > 0:
                    partial_zone = zone.copy()
                    partial_zone['allocated_capacity_mw'] = remaining
                    partial_zone['utilization']           = remaining / zone_capacity
                    selected_zones.append(partial_zone)
                break

        # Wilaya-level score uses the deterministic method for consistency across endpoints
        from ai_zone_recommendation import ZoneRecommendationComponent
        wilaya_score = ZoneRecommendationComponent(data_engine)._get_wilaya_score(wilaya_code)

        summary_statistics = {
            'total_zones_available':  len(scored_zones),
            'zones_selected':         len(selected_zones),
            'cumulative_potential_mw': round(cumulative_capacity, 2),
            'average_score':          round(
                sum(z['score'] for z in selected_zones) / len(selected_zones)
                if selected_zones else 0, 2
            ),
            'best_zone': selected_zones[0].get('commune_name') if selected_zones else None,
        }

        response_zones = []
        for zone in selected_zones:
            response_zones.append({
                'rank':                  zone.get('rank', 0),
                'commune_name':          zone.get('commune_name', 'Unknown'),
                'score':                 round(zone.get('score', 0), 2),
                'mean_ghi':              round(zone.get('mean_ghi', 0), 2),
                'mean_ghi_annual':       round(zone.get('mean_ghi', 0.0) * 8760.0, 2),
                'mean_dni':              float(zone.get('mean_dni', 0.0)),
                'mean_dhi':              float(zone.get('mean_dhi', 0.0)),
                'mean_t2m':              round(zone.get('temperature', 25), 1),
                'mean_ws10m':            float(zone.get('mean_ws10m', 0.0)),
                'mean_clearness':        round(zone.get('mean_clearness', 0), 3),
                'latitude':              zone.get('latitude', 0.0),
                'longitude':             zone.get('longitude', 0.0),
                'potential_mw':          round(zone.get('potential_mw', 0.0), 2),
                'capacity_factor':       round(zone.get('capacity_factor', 0.25), 3),
                'variability':           round(zone.get('variability', 0.0), 3),
                'recommendation':        'build' if zone.get('score', 0) >= 80 else 'study' if zone.get('score', 0) >= 60 else 'wait',
                'climate':               str(zone.get('climate', 'Unknown')),
                'allocated_capacity_mw': round(zone.get('allocated_capacity_mw', zone.get('potential_mw', 0.0)), 2),
                'utilization':           round(zone.get('utilization', 1.0), 3),
            })

        processing_time = (time.time() - start_time) * 1000
        logger.info(f"ML recommendation complete: {len(response_zones)} zones selected in {processing_time:.1f}ms")

        result_dict = {
            'wilaya_code':        wilaya_code,
            'wilaya_name':        wilaya_data['wilaya_name'],
            'wilaya_score':       wilaya_score,
            'target_capacity_mw': target_capacity_mw,
            'recommended_zones':  response_zones,
            'summary_statistics': summary_statistics,
            'processing_time_ms': processing_time,
        }

        user_id = _get_user_id()
        if user_id:
            try:
                record = ZoneAnalysisHistory(
                    user_id=user_id,
                    wilaya_code=wilaya_code,
                    wilaya_name=wilaya_data['wilaya_name'],
                    target_capacity_mw=target_capacity_mw,
                    objective='utility',
                    result_json=json.dumps(result_dict),
                    processing_time_ms=round(processing_time, 2),
                )
                db.session.add(record)
                db.session.commit()
                result_dict['history_id'] = record.id
            except Exception as db_err:
                logger.warning(f"Could not save zone analysis to history: {db_err}")
                db.session.rollback()

        return jsonify({"data": result_dict, "status": 200, "processing_time_ms": round(processing_time, 2)})

    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        return jsonify({"error": str(ve), "status": 400}), 400
    except Exception as e:
        logger.error(f"ML recommendation error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "status": 500}), 500