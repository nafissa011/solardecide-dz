import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

PARQUET_PATH = os.environ.get(
    "PARQUET_PATH",
    str(BASE_DIR / "data" / "algeria_solar_communes_REAL.parquet")
)
MODELS_DIR  = os.environ.get("MODELS_DIR", str(BASE_DIR / "data" / "checkpoints"))
CACHE_DIR   = str(BASE_DIR / "cache")
METRICS_JSON = str(BASE_DIR / "data" / "models" / "metrics.json")

VARIABLES = {
    "GHI": {
        "name": "Global Horizontal Irradiance",
        "unit": "kWh/m²/h",
        "description": "GHI total au sol",
        "feat_col": "GHI",
        "default": True,
    },
    "DNI": {
        "name": "Direct Normal Irradiance",
        "unit": "kWh/m²/h",
        "description": "Irradiance directe normale",
        "feat_col": "DNI",
        "default": False,
    },
    "DHI": {
        "name": "Diffuse Horizontal Irradiance",
        "unit": "kWh/m²/h",
        "description": "Irradiance diffuse horizontale",
        "feat_col": "DHI",
        "default": False,
    },
    "T2M": {
        "name": "Temperature at 2m",
        "unit": "°C",
        "description": "Température à 2m du sol",
        "feat_col": "T2M",
        "default": False,
    },
    "WS10M": {
        "name": "Wind Speed at 10m",
        "unit": "m/s",
        "description": "Vitesse du vent à 10m",
        "feat_col": "WS10M",
        "default": False,
    },
    "CLEARNESS_KT": {
        "name": "Clearness Index",
        "unit": "index (0-1)",
        "description": "Indice de clarté (KT = GHI / extraterrestrial)",
        "feat_col": "CLEARNESS_KT",
        "default": False,
    },
}

DEFAULT_VARIABLE = "GHI"

HORIZONS = {
    "24h": 24,
    "48h": 48,
    "7j":  168,
    "14j": 336,
    "30j": 720,
}
DEFAULT_HORIZON   = "24h"
HORIZON           = HORIZONS[DEFAULT_HORIZON]
MAX_HORIZON_HOURS = 720

MODEL_REGISTRY = {
    "patchtst": {
        "name":        "PatchTST",
        "family":      "Transformer",
        "description": "PatchTST horizon flexible - tous variables",
        "params":      "1.2M",
        "checkpoint":  "patchtst.pt",
        "variable":    "all",
        "available":   True,
        "type":        "ai",
    },
    # vmd_patchtst: 3 parallel PatchTST branches fused after VMD decomposition
    "vmd_patchtst": {
        "name":        "VMD-PatchTST",
        "family":      "Hybrid",
        "description": "3 branches PatchTST parallèles avec fusion VMD - tous variables",
        "params":      "3.6M",
        "checkpoint":  "vmd_patchtst.pt",
        "variable":    "all",
        "available":   False,
        "type":        "ai",
    },
    "tft": {
        "name":        "TFT",
        "family":      "Transformer",
        "description": "Temporal Fusion Transformer production-ready - tous variables",
        "params":      "2.1M",
        "checkpoint":  "tft.pt",
        "variable":    "all",
        "available":   True,
        "type":        "ai",
    },
    "nhits": {
        "name":        "N-HiTS",
        "family":      "MLP",
        "description": "N-HiTS sobre para fallback rapide - tous variables",
        "params":      "0.8M",
        "checkpoint":  "nhits.pt",
        "variable":    "all",
        "available":   True,
        "type":        "ai",
    },
    "persistence": {
        "name":        "Persistence",
        "family":      "Naive",
        "description": "Persistance des dernières valeurs",
        "params":      "N/A",
        "checkpoint":  None,
        "variable":    "all",
        "available":   True,
        "type":        "naive",
    },
    # DHI/DNI derived from GHI using fixed Saharan decomposition ratios
    "dhi_derived": {
        "name":           "DHI (derived)",
        "family":         "Transformation",
        "description":    "DHI calculé à partir de GHI (fraction diffuse 18%)",
        "params":         "N/A",
        "checkpoint":     None,
        "variable":       "DHI",
        "horizon_hours":  24,
        "role":           "derived",
        "transformation": "ghi * 0.18",
    },
    "dni_derived": {
        "name":           "DNI (derived)",
        "family":         "Transformation",
        "description":    "DNI calculé à partir de GHI et angle zénith (approx)",
        "params":         "N/A",
        "checkpoint":     None,
        "variable":       "DNI",
        "horizon_hours":  24,
        "role":           "derived",
        "transformation": "ghi * 1.08",
    },
    "t2m_persistence": {
        "name":          "T2M (persistence)",
        "family":        "Naive",
        "description":   "Température: persistance jour sur jour (séries saisonnières)",
        "params":        "N/A",
        "checkpoint":    None,
        "variable":      "T2M",
        "horizon_hours": 24,
        "role":          "baseline",
        "method":        "persistence",
    },
    "ws10m_persistence": {
        "name":          "WS10M (persistence)",
        "family":        "Naive",
        "description":   "Vitesse vent: persistance heure sur heure",
        "params":        "N/A",
        "checkpoint":    None,
        "variable":      "WS10M",
        "horizon_hours": 24,
        "role":          "baseline",
        "method":        "persistence",
    },
    "kt_persistence": {
        "name":          "CLEARNESS_KT (persistence)",
        "family":        "Naive",
        "description":   "Clearness index: persistance (peu variable)",
        "params":        "N/A",
        "checkpoint":    None,
        "variable":      "CLEARNESS_KT",
        "horizon_hours": 24,
        "role":          "baseline",
        "method":        "persistence",
    },
}

FEAT_COLS  = ["GHI", "DNI", "DHI", "T2M", "RH2M", "WS10M", "CLEARNESS_KT"]
TARGET_COL = "GHI"   # primary prediction target used for zone scoring
SEQ_LEN    = 168     # 7-day lookback window (hours)
VMD_K      = 3       # number of VMD decomposition modes

SCORE_WEIGHTS = {
    "mean_ghi":        0.35,
    "peak_ghi":        0.15,
    "sunshine_hours":  0.20,
    "clearness":       0.15,
    "low_variability": 0.15,
}
GHI_THRESH = 0.15  # minimum GHI (kWh/m²) to count an hour as sunny

CLIMATE_REGIONS = {
    "Saharan":   "Grand Sud",
    "Arid":      "Hauts Plateaux",
    "Semi-Arid": "Steppe",
    "Highland":  "Atlas",
    "Coastal":   "Littoral",
}

ZONE_AVERAGE_AREA_KM2           = 40.0   # avg commune area
CAPACITY_FACTOR                 = 0.18   # PV efficiency × losses
INSTALLATION_DENSITY_MW_PER_KM2 = 0.18  # ≈ 1 MW per 5–6 ha

ROI_SCENARIOS = {
    "base": {
        "capex_per_mw":    850_000,
        "opex_per_mw_yr":   18_000,
        "tariff_usd_kwh":    0.065,
        "degradation_pct":     0.5,
        "discount_rate":      0.08,
        "label":            "Base",
        "irr":              12.4,
        "npv":         4_200_000,
        "payback":           8.5,
        "lcoe":            0.038,
    },
    "conservative": {
        "capex_per_mw":    950_000,
        "opex_per_mw_yr":   22_000,
        "tariff_usd_kwh":    0.055,
        "degradation_pct":     0.8,
        "discount_rate":      0.10,
        "label":      "Conservateur",
        "irr":               9.2,
        "npv":         2_800_000,
        "payback":          10.8,
        "lcoe":            0.045,
    },
    "optimistic": {
        "capex_per_mw":    750_000,
        "opex_per_mw_yr":   14_000,
        "tariff_usd_kwh":    0.075,
        "degradation_pct":     0.3,
        "discount_rate":      0.07,
        "label":        "Optimiste",
        "irr":              16.1,
        "npv":         6_100_000,
        "payback":           7.0,
        "lcoe":            0.031,
    },
}

FORECAST_RATE_LIMIT = 10  # requests/min per IP

# Change JWT_SECRET via env var before deploying — default is dev-only
JWT_SECRET          = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM       = "HS256"
JWT_EXPIRATION_HOURS = 24

CORS_ORIGINS_DEV  = ["http://localhost:*", "http://127.0.0.1:*"]
CORS_ORIGINS_PROD = os.environ.get("ALLOWED_ORIGINS", "*")

DEFAULT_TARGET_CAPACITY_MW = 100.0
MAX_TARGET_CAPACITY_MW     = 1000.0
MIN_TARGET_CAPACITY_MW     = 0.1