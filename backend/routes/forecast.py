import json
import time
import logging
from flask import Blueprint, current_app, jsonify, request
from functools import wraps

from schemas import (
    ForecastRequest,
    ModelComparisonRequest,
    validate_wilaya_code,
    validate_variable
)
from services import ForecastingService
from db_models import db, ForecastHistory

logger = logging.getLogger(__name__)
bp = Blueprint("forecast", __name__)


def _get_user_id():
    """Extract user_id from httpOnly auth cookie or Authorization header."""
    from flask import request as flask_request
    token = flask_request.cookies.get("auth_token")
    if not token:
        auth = flask_request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        import jwt
        from config import JWT_SECRET, JWT_ALGORITHM
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


@bp.get("/forecast")
def get_forecast():
    """
    GET /api/forecast?model=patchtst&variable=GHI&wilaya=33&horizon=30d

    model:    patchtst | vmd_patchtst | tft | nhits
    variable: GHI | DNI | DHI | T2M | WS10M | CLEARNESS_KT
    wilaya:   1-58
    horizon:  24h | 48h | 7j | 14j | 30j
    """
    start_time = time.time()

    try:
        model_id         = request.args.get("model", "patchtst")
        variable         = request.args.get("variable", "GHI")
        wilaya_code_str  = request.args.get("wilaya", "09")
        horizon          = request.args.get("horizon", "30d")

        try:
            req = ForecastRequest(
                model_id=model_id,
                variable=variable,
                wilaya_code=int(wilaya_code_str),
                horizon=horizon
            )
        except ValueError as ve:
            logger.warning(f"Parameter validation error: {ve}")
            return jsonify({
                "error": f"Invalid parameters: {str(ve)}",
                "status": 400,
                "details": {
                    "model": model_id,
                    "variable": variable,
                    "wilaya": wilaya_code_str,
                    "horizon": horizon
                }
            }), 400

        forecast_service: ForecastingService = current_app.config.get("FORECASTING_SERVICE")
        if not forecast_service:
            logger.error("ForecastingService not initialized")
            return jsonify({"error": "Service unavailable", "status": 503}), 503

        response = forecast_service.generate_forecast(
            model_id=req.model_id,
            variable=req.variable,
            wilaya_code=req.wilaya_code,
            horizon=req.horizon
        )

        proc_time = (time.time() - start_time) * 1000
        logger.info(
            f"Forecast complete: {req.model_id} on {req.variable} "
            f"for wilaya {req.wilaya_code}, {len(response.forecasts)} points, "
            f"source={response.source}, time={proc_time:.2f}ms"
        )

        response_dict = response.dict()

        user_id = _get_user_id()
        if user_id:
            try:
                engine = current_app.config.get('DATA_ENGINE')
                wilaya_name = ''
                if engine:
                    w = engine.get_wilaya_detail(req.wilaya_code)
                    wilaya_name = w.get('wilaya_name', '') if w else ''
                record = ForecastHistory(
                    user_id=user_id,
                    wilaya_code=req.wilaya_code,
                    wilaya_name=wilaya_name,
                    model_id=req.model_id,
                    variable=req.variable,
                    horizon=req.horizon,
                    metrics_json=json.dumps(response_dict.get('metrics') or {}),
                    result_json=json.dumps(response_dict),
                    processing_time_ms=round(proc_time, 2),
                )
                db.session.add(record)
                db.session.commit()
                response_dict['history_id'] = record.id
            except Exception as db_err:
                logger.warning(f"Could not save forecast to history: {db_err}")
                db.session.rollback()

        return jsonify({
            "data": response_dict,
            "status": 200,
            "processing_time_ms": round(proc_time, 2)
        })

    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        return jsonify({"error": str(ve), "status": 400}), 400
    except Exception as e:
        logger.error(f"Forecast error: {e}", exc_info=True)
        # Primary service failed — fall back to mock so the client gets a usable response
        try:
            forecast_service = current_app.config.get("FORECASTING_SERVICE")
            if forecast_service:
                horizon_hours = {"24h": 24, "48h": 48, "7j": 168, "14j": 336, "30j": 720}.get(horizon, 24)
                mock_response = forecast_service._generate_mock_forecast(
                    model_id or "patchtst",
                    variable or "GHI",
                    int(wilaya_code_str) if wilaya_code_str else 9,
                    horizon_hours,
                    start_time
                )
                return jsonify({
                    "data": mock_response.dict(),
                    "status": 200,
                    "warning": "Using persistence forecast due to error"
                })
        except Exception:
            pass
        return jsonify({"error": "Internal server error", "status": 500}), 500


@bp.get("/forecast/compare")
def compare_forecasts():
    """
    GET /api/forecast/compare?wilaya=33&variable=GHI&horizon=7j

    Runs all available models on the same input and returns their forecasts
    and metrics side-by-side.
    """
    start_time = time.time()

    try:
        wilaya_code = int(request.args.get("wilaya", "9"))
        variable    = request.args.get("variable", "GHI")
        horizon     = request.args.get("horizon", "7j")

        if not 1 <= wilaya_code <= 58:
            raise ValueError(f"Invalid wilaya code: {wilaya_code}")
        variable = validate_variable(variable)

        forecast_service: ForecastingService = current_app.config.get("FORECASTING_SERVICE")
        if not forecast_service:
            return jsonify({"error": "Service unavailable", "status": 503}), 503

        all_models = forecast_service.model_loader.get_all_metadata()

        models_data = []
        for model_meta in all_models:
            try:
                forecast = forecast_service.generate_forecast(
                    model_id=model_meta["id"],
                    variable=variable,
                    wilaya_code=wilaya_code,
                    horizon=horizon
                )
                models_data.append({
                    "model":     model_meta,
                    "forecasts": [f.dict() for f in forecast.forecasts],
                    "labels":    [f.timestamp for f in forecast.forecasts],
                    "metrics":   forecast.metrics,
                    "source":    forecast.source
                })
            except Exception as e:
                logger.error(f"Failed model {model_meta['id']}: {e}")
                continue

        metrics_table = [
            {
                "model": m["model"]["name"],
                "mae":   m["metrics"].get("mae", 0),
                "rmse":  m["metrics"].get("rmse", 0),
                "mape":  m["metrics"].get("mape", 0),
                "r2":    m["metrics"].get("r2", 0),
            }
            for m in models_data
        ]

        proc_time = (time.time() - start_time) * 1000
        logger.info(f"Comparison complete: {len(models_data)} models in {proc_time:.2f}ms")

        return jsonify({
            "data": {
                "models":        models_data,
                "metrics_table": metrics_table,
            },
            "status": 200,
            "processing_time_ms": round(proc_time, 2)
        })

    except ValueError as ve:
        logger.warning(f"Validation error: {ve}")
        return jsonify({"error": str(ve), "status": 400}), 400
    except Exception as e:
        logger.error(f"Comparison error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error", "status": 500}), 500