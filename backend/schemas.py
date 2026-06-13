"""
Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict
from datetime import datetime


class ZoneRecommendationRequest(BaseModel):
    wilaya_code: int = Field(..., ge=1, le=58)
    target_capacity_mw: float = Field(..., gt=0)
    objective: Optional[str] = Field(
        "utility",
        pattern=r"^(utility|industrial|residential)$",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "wilaya_code": 33,
                "target_capacity_mw": 100.0,
                "objective": "utility"
            }
        }


class ZoneScore(BaseModel):
    rank: int
    commune_name: str
    score: float = Field(..., ge=0, le=100)
    mean_ghi: float = Field(..., ge=0)
    mean_ghi_annual: float = Field(..., ge=0)
    mean_dni: Optional[float] = None
    mean_dhi: Optional[float] = None
    mean_t2m: float
    mean_ws10m: Optional[float] = None
    mean_clearness: float = Field(..., ge=0, le=1)
    latitude: float = Field(..., ge=10, le=37)
    longitude: float = Field(..., ge=-8, le=12)
    potential_mw: float
    capacity_factor: Optional[float] = None
    variability: float
    recommendation: Literal["build", "study", "wait"]
    climate: str

    class Config:
        extra = "allow"  # tolère les champs supplémentaires selon la wilaya


class ZoneRecommendationResponse(BaseModel):
    wilaya_code: int
    wilaya_name: str
    wilaya_score: float = Field(..., ge=0, le=100)
    target_capacity_mw: float
    recommended_zones: List[ZoneScore]
    summary_statistics: dict
    processing_time_ms: float

    class Config:
        json_schema_extra = {
            "example": {
                "wilaya_code": 33,
                "wilaya_name": "Illizi",
                "wilaya_score": 68.17,
                "target_capacity_mw": 100.0,
                "recommended_zones": [
                    {
                        "rank": 1,
                        "commune_name": "Djanet",
                        "score": 50.0,
                        "mean_ghi": 0.285,
                        "mean_ghi_annual": 2496.0,
                        "mean_t2m": 28.5,
                        "mean_clearness": 0.72,
                        "latitude": 24.55,
                        "longitude": 9.48,
                        "potential_mw": 450.0,
                        "variability": 0.05,
                        "recommendation": "build",
                        "climate": "Saharan"
                    }
                ],
                "summary_statistics": {
                    "total_zones": 4,
                    "avg_score": 42.5,
                    "best_zone": "Djanet"
                },
                "processing_time_ms": 145.2
            }
        }


class ForecastRequest(BaseModel):
    model_id: str
    variable: str = Field(..., pattern=r"^(GHI|DNI|DHI|T2M|WS10M|CLEARNESS_KT)$")
    wilaya_code: int = Field(..., ge=1, le=58)
    horizon: str = Field(..., pattern=r"^(24h|48h|7j|14j|30j|1d|2d|7d|14d|30d)$")

    class Config:
        json_schema_extra = {
            "example": {
                "model_id": "patchtst",
                "variable": "GHI",
                "wilaya_code": 33,
                "horizon": "30j"
            }
        }


class ForecastDataPoint(BaseModel):
    timestamp: str
    value: float
    actual: Optional[float] = None
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None


class ForecastResponse(BaseModel):
    forecasts: List[ForecastDataPoint]
    metrics: Optional[Dict] = None
    model: Dict
    source: str
    processing_time_ms: float

    class Config:
        json_schema_extra = {
            "example": {
                "forecasts": [
                    {
                        "timestamp": "2025-04-24T12:00:00Z",
                        "value": 6.2,
                        "confidence_lower": 5.8,
                        "confidence_upper": 6.6
                    }
                ],
                "metrics": {"mae": 0.15, "rmse": 0.22, "mape": 2.5, "r2": 0.89},
                "model": {
                    "id": "patchtst",
                    "name": "PatchTST",
                    "type": "ai",
                    "description": "Transformer-based forecasting model"
                },
                "source": "ai_model",
                "processing_time_ms": 45.2
            }
        }


class ModelComparisonRequest(BaseModel):
    wilaya_code: int = Field(..., ge=1, le=58)
    variable: str = Field(..., pattern=r"^(GHI|DNI|DHI|T2M|WS10M|CLEARNESS_KT)$")
    horizon: Literal["24h", "48h", "7j"] = "7j"

    class Config:
        json_schema_extra = {
            "example": {
                "wilaya_code": 33,
                "variable": "GHI",
                "horizon": "7j"
            }
        }


class ModelInfo(BaseModel):
    id: str
    name: str
    family: str
    description: str
    params: str
    mae: float
    rmse: float
    mape: float
    r2: float
    available: bool


def validate_wilaya_code(code: int) -> int:
    if not 1 <= code <= 58:
        raise ValueError(f"Invalid wilaya code: {code}. Must be 1-58.")
    return code


def normalize_horizon(horizon: str) -> str:
    """Accepte les suffixes 'd' (anglais) et 'j' (français) de manière interchangeable."""
    horizon_map = {
        "1d": "24h", "2d": "48h", "7d": "7j", "14d": "14j", "30d": "30j",
        "24h": "24h", "48h": "48h", "7j": "7j", "14j": "14j", "30j": "30j"
    }
    return horizon_map.get(horizon, horizon)


def validate_horizon(horizon: str) -> int:
    """Retourne la durée en jours."""
    horizon_map = {"24h": 1, "48h": 2, "7j": 7, "14j": 14, "30j": 30}
    if horizon not in horizon_map:
        raise ValueError(f"Invalid horizon: {horizon}. Must be one of {list(horizon_map.keys())}")
    return horizon_map[horizon]


def validate_variable(variable: str) -> str:
    valid = {"GHI", "DNI", "DHI", "T2M", "WS10M", "CLEARNESS_KT"}
    var = variable.upper()
    if var not in valid:
        raise ValueError(f"Invalid variable: {variable}. Must be one of {valid}")
    return var