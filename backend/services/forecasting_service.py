"""Forecasting service — multi-variable, multi-horizon."""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ai_forecasting import ForecastingComponent
from models.loader import ModelLoader
from preprocessing import SolarPreprocessor
from data_engine import DataEngine
from schemas import (
    ForecastRequest,
    ForecastDataPoint,
    ForecastResponse,
    ModelComparisonRequest,
    ModelInfo,
)
from config import VARIABLES, HORIZONS

logger = logging.getLogger(__name__)


class ForecastingService:

    def __init__(
        self,
        model_loader: ModelLoader,
        preprocessor: SolarPreprocessor,
        data_engine: DataEngine
    ):
        self.model_loader = model_loader
        self.preprocessor = preprocessor
        self.data_engine = data_engine
        self.ai_component = ForecastingComponent(model_loader, preprocessor, data_engine)

    def generate_forecast(
        self,
        model_id: str,
        variable: str,
        wilaya_code: int,
        horizon: str
    ) -> ForecastResponse:
        start_time = time.time()
        logger.info(
            f"Forecast started: model={model_id}, var={variable}, "
            f"wilaya={wilaya_code}, horizon={horizon}"
        )

        request = ForecastRequest(
            model_id=model_id,
            variable=variable,
            wilaya_code=wilaya_code,
            horizon=horizon
        )

        response = self.ai_component.generate_forecast(request)

        processing_time = (time.time() - start_time) * 1000
        logger.info(f"Forecast completed: {len(response.forecasts)} points, {processing_time:.1f}ms")

        return response

    def compare_forecasts(
        self,
        models: List[str],
        variable: str,
        wilaya_code: int,
        horizon: str
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"Forecast comparison started: {len(models)} models, {variable}, wilaya={wilaya_code}, {horizon}")

        results = {}
        for model_id in models:
            try:
                forecast = self.generate_forecast(model_id, variable, wilaya_code, horizon)
                results[model_id] = {'forecast': forecast, 'success': True}
            except Exception as e:
                logger.error(f"Model {model_id} failed: {e}")
                results[model_id] = {'error': str(e), 'success': False}

        processing_time = (time.time() - start_time) * 1000

        return {
            'comparisons': results,
            'metadata': {
                'variable': variable,
                'wilaya_code': wilaya_code,
                'horizon': horizon,
                'models_compared': models,
                'processing_time_ms': processing_time
            }
        }

    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        return self.ai_component.get_available_models()

    def get_forecast_metadata(self, variable: str, horizon: str) -> Dict[str, Any]:
        return self.ai_component.get_forecast_metadata(variable, horizon)

    def _get_horizon_hours(self, horizon: str) -> int:
        """Convert horizon label (e.g. '7j') to hours."""
        h = HORIZONS.get(horizon)
        if h is None:
            raise ValueError(f"Invalid horizon: {horizon}. Must be one of {list(HORIZONS.keys())}")
        return h

    def _horizon_label(self, hours: int) -> str:
        """Reverse lookup: hours → horizon label."""
        rev = {v: k for k, v in HORIZONS.items()}
        return rev.get(hours, f"{hours}h")

    def _get_model_metadata(self, model_id: str) -> dict:
        """Returns stub with available=False if model_id not found in registry."""
        all_meta = self.model_loader.get_all_metadata()
        for m in all_meta:
            if m["id"] == model_id:
                return m
        return {
            "id": model_id,
            "name": model_id,
            "mae": 0.1,
            "rmse": 0.15,
            "mape": 10.0,
            "r2": 0.5,
            "available": False,
        }

    def _select_best_ghi_model(self) -> str:
        """Returns highest-r2 available GHI model, falls back to 'patchtst'."""
        all_meta = self.model_loader.get_all_metadata()
        ghi_models = [m for m in all_meta if m.get("variable") == "GHI" and m.get("available")]
        if ghi_models:
            ghi_models.sort(key=lambda m: m.get("r2", 0), reverse=True)
            return ghi_models[0]["id"]
        return "patchtst"

    def _get_recent_ratio(self, wilaya_code: int, numerator: str, denominator: str, default: float = 0.18) -> float:
        """Compute median(numerator/denominator) over last 7 days. Returns default on failure."""
        try:
            num = self.data_engine.get_recent_actual(wilaya_code, days=7, variable=numerator)
            den = self.data_engine.get_recent_actual(wilaya_code, days=7, variable=denominator)
            num_vals = np.array(num["values"], dtype=float)
            den_vals = np.array(den["values"], dtype=float)
            mask = (den_vals > 0) & ~np.isnan(num_vals) & ~np.isnan(den_vals)
            if mask.sum() > 0:
                ratios = num_vals[mask] / den_vals[mask]
                ratio = float(np.median(ratios))
                if np.isfinite(ratio) and ratio > 0:
                    return ratio
        except Exception:
            pass
        return default

    def _extend_horizon(self, pred_24: np.ndarray, horizon_hours: int, variable: str) -> tuple:
        """
        Extend a 24h prediction to a longer horizon.
        ≤24h: clip and return with 95% CI from std.
        >24h: tile into daily buckets, return daily mean ± 95% CI.
        """
        if horizon_hours <= 24:
            predicted = pred_24.clip(0 if variable in ("GHI", "DNI", "DHI") else -50, 1000)
            sigma = float(np.std(predicted)) if len(predicted) > 1 else 0.1
            return predicted, predicted - 1.96*sigma, predicted + 1.96*sigma

        n_days = int(np.ceil(horizon_hours / 24))
        tiled = np.tile(pred_24, n_days)[:horizon_hours]

        if len(tiled) < n_days * 24:
            pad_len = n_days * 24 - len(tiled)
            tiled = np.concatenate([tiled, np.full(pad_len, np.nan)])
        daily = tiled[: n_days*24].reshape(n_days, 24)
        daily_mean = np.nanmean(daily, axis=1)
        daily_std  = np.nanstd(daily, axis=1)

        return daily_mean, daily_mean - 1.96 * daily_std, daily_mean + 1.96 * daily_std

    def _generate_timestamps(self, horizon_hours: int) -> List[str]:
        base_date = datetime.today()
        if horizon_hours > 24:
            n_days = int(np.ceil(horizon_hours / 24))
            return [
                (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(n_days)
            ]
        return [
            (base_date + timedelta(hours=i)).strftime("%Y-%m-%d %H:00")
            for i in range(horizon_hours)
        ]

    def _get_actual_values(self, wilaya_code: int, variable: str, horizon_hours: int) -> List[Optional[float]]:
        if horizon_hours <= 24:
            try:
                vals = self.data_engine.get_recent_hourly(wilaya_code, hours=horizon_hours, variable=variable)
                return vals[:horizon_hours]
            except Exception:
                pass

        days_needed = int(np.ceil(horizon_hours / 24)) + 1
        try:
            recent = self.data_engine.get_recent_actual(wilaya_code, days=days_needed, variable=variable)
            values = recent.get("values", [])
        except Exception:
            values = []

        n_points = int(np.ceil(horizon_hours / 24))
        if len(values) < n_points:
            values = list(values) + [None] * (n_points - len(values))
        return values[:n_points]

    def _generate_mock_forecast(
        self,
        model_id: str,
        variable: str,
        wilaya_code: int,
        horizon_hours: int,
        start_time: float = None
    ) -> ForecastResponse:
        """Persistence fallback: last known value repeated across the horizon."""
        try:
            values = self.data_engine.get_recent_hourly(wilaya_code, hours=24, variable=variable or "GHI")
            last_value = values[-1] if values else 0.5
        except Exception:
            last_value = 0.5

        if horizon_hours <= 24:
            timestamps = [
                (datetime.now() + timedelta(hours=i + 1)).strftime("%Y-%m-%d %H:00")
                for i in range(horizon_hours)
            ]
        else:
            days = int(np.ceil(horizon_hours / 24))
            timestamps = [
                (datetime.now() + timedelta(days=i + 1)).strftime("%Y-%m-%d")
                for i in range(days)
            ]

        forecasts = [
            ForecastDataPoint(
                timestamp=ts,
                value=round(last_value, 4),
                confidence_lower=round(max(0, last_value * 0.9), 4),
                confidence_upper=round(last_value * 1.1, 4)
            )
            for ts in timestamps
        ]

        model_meta = self._get_model_metadata(model_id)
        return ForecastResponse(
            forecasts=forecasts,
            metrics={"mae": 0.0, "rmse": 0.0, "mape": 0.0, "r2": 0.0},
            model={
                'id':          model_meta['id'],
                'name':        model_meta.get('name', model_id),
                'type':        model_meta.get('type', 'unknown'),
                'description': model_meta.get('description', '')
            },
            source='persistence',
            processing_time_ms=0.0
        )

    def compare_models(self, request: ModelComparisonRequest = None, **kwargs) -> Dict[str, Any]:
        """
        Accepts either a ModelComparisonRequest or kwargs (wilaya_code, variable, horizon).
        Includes derived/persistence baselines for non-GHI variables.
        """
        if request is None:
            request = ModelComparisonRequest(**kwargs)

        start_time = time.time()
        logger.info(f"Model comparison: var={request.variable}, wilaya={request.wilaya_code}")

        all_meta = self.model_loader.get_all_metadata()
        applicable = []
        for m in all_meta:
            var = m.get("variable")
            if var is None:
                name_lower = m["name"].lower()
                if request.variable.lower() in name_lower or "all" in name_lower:
                    applicable.append(m)
            elif var == request.variable:
                applicable.append(m)

        # DHI/DNI have no dedicated models — use physics-based derivation from GHI
        if request.variable in ("DHI", "DNI"):
            applicable.append({
                "id":          f"{request.variable.lower()}_derived",
                "name":        f"{request.variable} (derived from GHI)",
                "family":      "Transformation",
                "description": "Physics-based transformation of GHI forecast",
                "params":      "N/A",
                "mae": 0.12, "rmse": 0.18, "mape": 12.0, "r2": 0.65,
                "available":   True,
            })
        elif request.variable in ("T2M", "WS10M", "CLEARNESS_KT"):
            applicable.append({
                "id":          f"{request.variable.lower()}_persistence",
                "name":        f"{request.variable} (persistence)",
                "family":      "Baseline",
                "description": "Persistence forecast (today = tomorrow)",
                "params":      "N/A",
                "mae":  2.5 if request.variable == "T2M" else 1.2,
                "rmse": 3.0 if request.variable == "T2M" else 1.5,
                "mape": 8.0, "r2": 0.6,
                "available": True,
            })

        forecasts = []
        for m in applicable:
            try:
                f = self.generate_forecast(
                    model_id=m["id"],
                    variable=request.variable,
                    wilaya_code=request.wilaya_code,
                    horizon=request.horizon
                )
                forecasts.append({
                    "model":              m,
                    "forecasts":          [fp.dict() for fp in f.forecasts],
                    "metrics":            f.metrics,
                    "source":             f.source,
                    "processing_time_ms": f.processing_time_ms,
                })
            except Exception as e:
                logger.error(f"Model {m['id']} failed: {e}")
                continue

        proc_time = (time.time() - start_time) * 1000

        return {
            "models": forecasts,
            "metrics_table": [
                {
                    "model":  f["model"]["name"],
                    "family": f["model"].get("family", ""),
                    "mae":    f["metrics"].get("mae", 0),
                    "rmse":   f["metrics"].get("rmse", 0),
                    "mape":   f["metrics"].get("mape", 0),
                    "r2":     f["metrics"].get("r2", 0),
                }
                for f in forecasts
            ],
            "processing_time_ms": round(proc_time, 2)
        }