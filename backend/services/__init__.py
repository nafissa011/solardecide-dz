"""SolarDZ — Services package.

ML-dependent imports are tolerated: when torch/joblib are unavailable, the
optional services are exposed as ``None`` so that non-ML modules (e.g.
plan_service) can still be imported safely.
"""

__all__ = [
    "RecommendationService",
    "ForecastingService",
    "ZoneModelService",
]

try:
    from .recommendation_service import RecommendationService  # noqa: F401
except Exception:  # noqa: BLE001
    RecommendationService = None  # type: ignore

try:
    from .forecasting_service import ForecastingService  # noqa: F401
except Exception:  # noqa: BLE001
    ForecastingService = None  # type: ignore

try:
    from .zone_model_service import ZoneModelService  # noqa: F401
except Exception:  # noqa: BLE001
    ZoneModelService = None  # type: ignore
