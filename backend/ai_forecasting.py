import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import torch
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from config import VARIABLES, HORIZONS, MODEL_REGISTRY
from models.loader import ModelLoader
from preprocessing import SolarPreprocessor
from data_engine import DataEngine
from schemas import ForecastRequest, ForecastResponse, ForecastDataPoint

logger = logging.getLogger(__name__)


@dataclass
class ForecastMetrics:
    mae: float
    rmse: float
    mape: Optional[float] = None
    r2: Optional[float] = None


class ForecastingComponent:

    def __init__(self, model_loader: ModelLoader, preprocessor: SolarPreprocessor, data_engine: DataEngine):
        self.model_loader = model_loader
        self.preprocessor = preprocessor
        self.data_engine = data_engine
        self._load_model_registry()
        logger.info("ForecastingComponent initialized")

    def _load_model_registry(self):
        self.model_registry = MODEL_REGISTRY.copy()
        logger.info(f"Model registry loaded: {len(self.model_registry)} models")

    def _validate_inputs(self, request: ForecastRequest):
        if not (1 <= request.wilaya_code <= 58):
            raise ValueError(f"Invalid wilaya code: {request.wilaya_code}")
        if request.variable not in VARIABLES:
            raise ValueError(f"Invalid variable: {request.variable}. Must be one of {list(VARIABLES.keys())}")
        if request.horizon not in HORIZONS:
            raise ValueError(f"Invalid horizon: {request.horizon}. Must be one of {list(HORIZONS.keys())}")
        if request.model_id not in self.model_registry:
            raise ValueError(f"Invalid model: {request.model_id}. Must be one of {list(self.model_registry.keys())}")

    def _get_horizon_hours(self, horizon: str) -> int:
        return HORIZONS[horizon]

    def _hours_to_horizon(self, hours: int) -> str:
        reverse_map = {v: k for k, v in HORIZONS.items()}
        return reverse_map.get(hours, f"{hours}h")

    def _compute_metrics(self, actual: np.ndarray, predicted: np.ndarray) -> ForecastMetrics:
        mae = mean_absolute_error(actual, predicted)
        rmse = np.sqrt(mean_squared_error(actual, predicted))

        # Skip MAPE when actuals contain zeros to avoid division by zero
        mask = actual != 0
        mape = np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100 if np.any(mask) else None

        ss_res = np.sum((actual - predicted) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else None

        return ForecastMetrics(
            mae=round(mae, 4),
            rmse=round(rmse, 4),
            mape=round(mape, 2) if mape is not None else None,
            r2=round(r2, 4) if r2 is not None else None
        )

    def _generate_persistence_forecast(self, variable: str, wilaya_code: int, horizon_hours: int) -> List[ForecastDataPoint]:
        """Fallback for variables without an AI model — repeats the last observed value."""
        try:
            values = self.data_engine.get_recent_hourly(wilaya_code, hours=24, variable=variable)
            if not values:
                raise ValueError(f"No recent data for {variable} in wilaya {wilaya_code}")

            last_value = values[-1]
            base_time = datetime.now()

            return [
                ForecastDataPoint(
                    timestamp=(base_time + timedelta(hours=i+1)).isoformat(),
                    value=round(last_value, 4),
                    confidence_lower=round(max(0, last_value * 0.9), 4),
                    confidence_upper=round(last_value * 1.1, 4)
                )
                for i in range(horizon_hours)
            ]

        except Exception as e:
            logger.error(f"Persistence forecast failed: {e}")
            # Return zeros rather than propagating — keeps the API response intact
            base_time = datetime.now()
            return [
                ForecastDataPoint(
                    timestamp=(base_time + timedelta(hours=i+1)).isoformat(),
                    value=0.0, confidence_lower=0.0, confidence_upper=0.0
                )
                for i in range(horizon_hours)
            ]

    def _predict_with_model(self, model: Any, processed: torch.Tensor) -> np.ndarray:
        """Supports both plain callables and VMD fusion models (dict with 'branches' + 'fusion' keys)."""
        if callable(model):
            prediction = model(processed)
        elif isinstance(model, dict) and 'branches' in model and 'fusion' in model:
            branch_preds = [branch(processed) for branch in model['branches']]
            prediction = model['fusion'](*branch_preds)
        else:
            raise ValueError(f"Unsupported model type for prediction: {type(model)}")

        if isinstance(prediction, torch.Tensor):
            return prediction.squeeze().cpu().numpy()
        raise ValueError("Model prediction did not return a torch.Tensor")

    def _generate_ai_forecast(self, model_id: str, variable: str, wilaya_code: int, horizon_hours: int) -> List[ForecastDataPoint]:
        try:
            model = self.model_loader.load(model_id)
            if not model:
                logger.warning(f"Model {model_id} not available, falling back to persistence")
                return self._generate_persistence_forecast(variable, wilaya_code, horizon_hours)

            seq_len = 168  # 7-day lookback window
            data = self.data_engine.get_vmd_window(wilaya_code, seq_len + 24)
            data = [{"value": float(v), "timestamp": ""} for v in data]

            if len(data) < seq_len:
                logger.warning(f"Insufficient data for AI forecast, falling back to persistence")
                return self._generate_persistence_forecast(variable, wilaya_code, horizon_hours)

            values = np.array([d['value'] for d in data])

            # vmd_patchtst expects 1 feature; all other models expect 6
            seq_features = 1 if model_id == 'vmd_patchtst' else 6
            values_expanded = np.tile(values[-seq_len:].reshape(1, seq_len, 1), (1, 1, seq_features))
            processed = torch.tensor(values_expanded, dtype=torch.float32)

            with torch.no_grad():
                forecast_values = self._predict_with_model(model, processed)

            # Pad with persistence if model output is shorter than the requested horizon
            if len(forecast_values) < horizon_hours:
                last_values = values[-(horizon_hours - len(forecast_values)):]
                forecast_values = np.concatenate([forecast_values, last_values])

            base_time = datetime.now()
            forecasts = []
            for i in range(min(horizon_hours, len(forecast_values))):
                value = float(forecast_values[i])
                std_dev = np.std(values[-24:]) if len(values) >= 24 else 0.1
                forecasts.append(ForecastDataPoint(
                    timestamp=(base_time + timedelta(hours=i+1)).isoformat(),
                    value=round(max(0, value), 4),
                    confidence_lower=round(max(0, value - 1.96 * std_dev), 4),
                    confidence_upper=round(max(0, value + 1.96 * std_dev), 4)
                ))

            return forecasts

        except Exception as e:
            logger.error(f"AI forecast failed: {e}")
            return self._generate_persistence_forecast(variable, wilaya_code, horizon_hours)

    def _generate_derived_forecast(self, variable: str, wilaya_code: int, horizon_hours: int) -> List[ForecastDataPoint]:
        """
        Derives DHI/DNI from a GHI forecast using fixed decomposition ratios.
        TODO: replace with clearness index (Kt) model for better accuracy.
        """
        try:
            horizon_label = self._hours_to_horizon(horizon_hours)
            ghi_forecast = self.generate_forecast(ForecastRequest(
                model_id='patchtst',
                variable='GHI',
                wilaya_code=wilaya_code,
                horizon=horizon_label
            ))

            # DHI ≈ 30% of GHI, DNI ≈ 70% — rough Saharan approximation
            ratio = 0.3 if variable == 'DHI' else 0.7

            return [
                ForecastDataPoint(
                    timestamp=point.timestamp,
                    value=round(point.value * ratio, 4),
                    confidence_lower=round(point.confidence_lower * ratio, 4),
                    confidence_upper=round(point.confidence_upper * ratio, 4)
                )
                for point in ghi_forecast.forecasts
            ]

        except Exception as e:
            logger.error(f"Derived forecast failed: {e}")
            raise

    def generate_forecast(self, request: ForecastRequest) -> ForecastResponse:
        start_time = time.time()
        logger.info(f"Forecast request: {request.model_id}, {request.variable}, wilaya={request.wilaya_code}, horizon={request.horizon}")

        try:
            self._validate_inputs(request)
            horizon_hours = self._get_horizon_hours(request.horizon)
            model_meta = self.model_registry[request.model_id]

            # Routing: AI model for GHI, derived for DHI/DNI, persistence for everything else
            if request.variable == 'GHI' and model_meta.get('type') == 'ai':
                forecasts = self._generate_ai_forecast(
                    request.model_id, request.variable, request.wilaya_code, horizon_hours
                )
            elif request.variable in ['DHI', 'DNI']:
                forecasts = self._generate_derived_forecast(
                    request.variable, request.wilaya_code, horizon_hours
                )
            else:
                # T2M, WS10M, CLEARNESS_KT use persistence
                forecasts = self._generate_persistence_forecast(
                    request.variable, request.wilaya_code, horizon_hours
                )

            # Metrics are best-effort — actual data may not be available yet
            metrics = None
            try:
                actual_data = self.data_engine.get_recent_hourly(
                    request.wilaya_code, hours=horizon_hours, variable=request.variable
                )
                if len(actual_data) >= len(forecasts):
                    actual_values = np.array(actual_data[:len(forecasts)])
                    predicted_values = np.array([f.value for f in forecasts])
                    metrics = self._compute_metrics(actual_values, predicted_values)
            except Exception as e:
                logger.warning(f"Could not compute metrics: {e}")

            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Forecast completed: {len(forecasts)} points, {processing_time:.1f}ms")

            return ForecastResponse(
                forecasts=forecasts,
                metrics=asdict(metrics) if metrics else None,
                model={
                    'id': request.model_id,
                    'name': model_meta.get('name', request.model_id),
                    'type': model_meta.get('type', 'unknown'),
                    'description': model_meta.get('description', ''),
                    'params': model_meta.get('params', 'N/A'),
                    'training_time': 'Local checkpoint' if model_meta.get('available', False) else 'Unavailable',
                    'available': model_meta.get('available', False),
                },
                source='ai_model' if model_meta.get('type') == 'ai' else 'derived',
                processing_time_ms=processing_time
            )

        except Exception as e:
            logger.error(f"Forecast generation failed: {e}", exc_info=True)
            raise

    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        return self.model_registry.copy()

    def get_forecast_metadata(self, variable: str, horizon: str) -> Dict[str, Any]:
        return {
            'variable': variable,
            'horizon': horizon,
            'horizon_hours': self._get_horizon_hours(horizon),
            'available_models': [
                model_id for model_id, meta in self.model_registry.items()
                if meta.get('variables', ['GHI']) == ['GHI'] or variable in meta.get('variables', [])
            ],
            'recommended_model': 'patchtst' if variable == 'GHI' else 'persistence'
        }