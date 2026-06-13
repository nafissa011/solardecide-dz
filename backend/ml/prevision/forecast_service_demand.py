"""
ml/prevision/forecast_service_demand.py
═══════════════════════════════════════════════════════════════════
Service de prévision de la demande électrique (Demand_MW)
SolarDecide DZ — Phase 3+

Modèle : best_models_demand.pkl  (XGBoost / RF selon horizon)
Dataset : algeria_solar_communes_REAL.parquet  (via PARQUET_PATH config)
          → Fallback sur dataset.csv si le parquet est absent

Horizons supportés : 'daily' | 'weekly' | 'monthly'

Fonctions exposées :
    predict_demand_forecast(wilaya_query, horizon) → dict
    get_demand_forecast_response(wilaya_query, horizon) → { success, data }
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import datetime as _dt
import logging
import unicodedata
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger(__name__)

# ─── CHEMINS ─────────────────────────────────────────────────────
_HERE             = Path(__file__).resolve().parent
DEMAND_MODEL_PATH = _HERE / "best_models_demand.pkl"

# Dataset : priorité au parquet de l'app, fallback csv local
def _resolve_dataset_path() -> Path:
    try:
        from config import PARQUET_PATH
        p = Path(PARQUET_PATH)
        if p.exists():
            return p
    except Exception:
        pass
    # Fallback : csv dans le même dossier que ce fichier
    csv_path = _HERE / "dataset.csv"
    if csv_path.exists():
        return csv_path
    raise FileNotFoundError(
        "Dataset introuvable. Définissez PARQUET_PATH ou placez dataset.csv dans ml/prevision/."
    )

# ─── CONSTANTES ──────────────────────────────────────────────────
DEMAND_HORIZON_LABELS = {
    "daily":   "Journalier",
    "weekly":  "Hebdomadaire",
    "monthly": "Mensuel",
}

# ─── CACHES ──────────────────────────────────────────────────────
_demand_bundle_cache: dict | None = None
_dataset_cache = None


# ─── CHARGEMENT MODÈLE ───────────────────────────────────────────
def load_demand_model() -> dict:
    global _demand_bundle_cache
    if _demand_bundle_cache is not None:
        return _demand_bundle_cache
    if not DEMAND_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modèle Demand_MW introuvable : {DEMAND_MODEL_PATH} "
            "— assurez-vous que best_models_demand.pkl est présent dans ml/prevision/."
        )
    pkg = joblib.load(DEMAND_MODEL_PATH)
    _demand_bundle_cache = pkg
    logger.info("✅ Demand_MW bundle chargé — horizons : %s", list(pkg.keys()))
    return pkg


# ─── CHARGEMENT DATASET ──────────────────────────────────────────
def _load_dataset() -> pd.DataFrame:
    global _dataset_cache
    if _dataset_cache is not None:
        return _dataset_cache
    path = _resolve_dataset_path()
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values(["wilaya_name", "datetime"]).reset_index(drop=True)
    _dataset_cache = df
    logger.info("Dataset Demand chargé depuis %s : %d lignes", path.name, len(df))
    return _dataset_cache


# ─── UTILITAIRES ─────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def _resolve(df: pd.DataFrame, query) -> tuple[pd.DataFrame | None, str]:
    col = "wilaya_name"
    try:
        code = int(query)
        m = df[df["wilaya_code"] == code]
        if not m.empty:
            return m, str(m[col].iloc[0])
    except (ValueError, TypeError):
        pass
    m = df[df[col] == str(query)]
    if not m.empty:
        return m, str(m[col].iloc[0])
    target = _norm(query)
    m = df[df[col].astype(str).map(_norm) == target]
    if not m.empty:
        return m, str(m[col].iloc[0])
    return None, str(query)


def _agg_demand(df_w: pd.DataFrame, horizon: str, feat_cols: list[str]) -> pd.DataFrame:
    avail = [c for c in feat_cols if c in df_w.columns]
    if horizon == "monthly":
        tmp = df_w.copy()
        tmp["year"]  = tmp["datetime"].dt.year
        tmp["month"] = tmp["datetime"].dt.month
        out = tmp.groupby(["year", "month"], as_index=False)[avail].mean()
        out["datetime"] = pd.to_datetime(out[["year", "month"]].assign(day=1))
    elif horizon == "weekly":
        iso = df_w["datetime"].dt.isocalendar()
        tmp = df_w.copy()
        tmp["iso_year"] = iso.year.astype(int)
        tmp["iso_week"] = iso.week.astype(int)
        out = tmp.groupby(["iso_year", "iso_week"], as_index=False)[avail].mean()
        out["datetime"] = pd.to_datetime(
            out["iso_year"].astype(str) + "-W" +
            out["iso_week"].astype(str).str.zfill(2) + "-1",
            format="%G-W%V-%u",
        )
    else:  # daily
        tmp = df_w.copy()
        tmp["datetime"] = tmp["datetime"].dt.floor("D")
        out = tmp.groupby("datetime", as_index=False)[avail].mean()
    out["year"] = out["datetime"].dt.year
    return out.sort_values("datetime").reset_index(drop=True)


def _apply_demand_prep(df: pd.DataFrame, prep: dict, feat_cols: list[str]) -> pd.DataFrame:
    avail = [c for c in feat_cols if c in df.columns]
    out   = df.copy()
    out[avail] = prep["imputer"].transform(out[avail])
    for c in avail:
        if c in prep["clips"]:
            lo, hi = prep["clips"][c]
            out[c] = out[c].clip(lo, hi)
    out[avail] = prep["scaler"].transform(out[avail])
    return out


def _build_demand_window(df_scaled: pd.DataFrame, feat_cols: list[str], look_back: int) -> np.ndarray:
    avail = [c for c in feat_cols if c in df_scaled.columns]
    tail  = df_scaled[avail].tail(look_back)
    if len(tail) < look_back:
        pad = pd.DataFrame(
            [df_scaled[avail].mean().values] * (look_back - len(tail)),
            columns=avail,
        )
        tail = pd.concat([pad, tail], ignore_index=True)
    return tail.fillna(0).values.reshape(1, -1)


def _autoregress_demand(
    model, df_sc: pd.DataFrame, df_h: pd.DataFrame,
    prep: dict, feat_cols: list[str], look_back: int, n_steps: int,
) -> list[float]:
    avail  = [c for c in feat_cols if c in df_sc.columns]
    window = df_sc[avail].tail(look_back).copy()
    if len(window) < look_back:
        pad = pd.DataFrame(
            [df_sc[avail].mean().values] * (look_back - len(window)),
            columns=avail,
        )
        window = pd.concat([pad, window], ignore_index=True)
    preds = []
    for _ in range(n_steps):
        pred = float(model.predict(window.values.reshape(1, -1))[0])
        preds.append(max(0.0, pred))
        new_row = window.iloc[-1].copy()
        if "demand_mw" in new_row.index:
            new_row["demand_mw"] = pred
        window = pd.concat(
            [window.iloc[1:].reset_index(drop=True),
             pd.DataFrame([new_row.values], columns=avail)],
            ignore_index=True,
        )
    return preds


def _n_display_points(horizon: str) -> int:
    return {"monthly": 12, "weekly": 16, "daily": 30}[horizon]


def _build_demand_labels(df_h: pd.DataFrame, horizon: str, n_steps: int) -> list[str]:
    if df_h.empty or "datetime" not in df_h.columns:
        return [f"P{i+1}" for i in range(n_steps)]
    last_dt = pd.Timestamp(df_h["datetime"].iloc[-1])
    MONTHS_FR = ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Août","Sep","Oct","Nov","Déc"]
    if horizon == "monthly":
        labels, dt = [], last_dt
        for _ in range(n_steps):
            dt += pd.DateOffset(months=1)
            labels.append(f"{MONTHS_FR[dt.month - 1]} {dt.year}")
        return labels
    elif horizon == "weekly":
        labels, dt = [], last_dt
        for _ in range(n_steps):
            dt += pd.DateOffset(weeks=1)
            labels.append(f"S{dt.isocalendar()[1]:02d}/{dt.year}")
        return labels
    else:
        return [(last_dt + pd.Timedelta(days=i + 1)).strftime("%d/%m/%y") for i in range(n_steps)]


# ─── PRÉVISION DEMAND_MW ─────────────────────────────────────────
def predict_demand_forecast(wilaya_query, horizon: str = "monthly") -> dict:
    """
    Prédit la demande électrique (MW) pour une wilaya et un horizon.

    Parameters
    ----------
    wilaya_query : str | int
    horizon : 'daily' | 'weekly' | 'monthly'

    Returns
    -------
    dict avec labels, demand_mw, best_period, worst_period, model_metrics, ...
    """
    if horizon not in ("daily", "weekly", "monthly"):
        horizon = "monthly"

    bundle = load_demand_model()
    if horizon not in bundle:
        raise ValueError(
            f"Horizon '{horizon}' absent du bundle. "
            f"Horizons disponibles : {list(bundle.keys())}"
        )

    bh         = bundle[horizon]
    model      = bh["model"]
    prep       = bh["preprocessing"]
    feat_cols  = bh["feature_cols"]
    look_back  = bh["look_back"]
    model_name = bh["model_name"]
    metrics_d  = bh.get("best_model_metrics", bh.get("metrics", {}))

    df         = _load_dataset()
    df_w, canonical = _resolve(df, wilaya_query)
    if df_w is None or df_w.empty:
        raise ValueError(f"Wilaya inconnue : {wilaya_query!r}")

    wilaya_code = int(df_w["wilaya_code"].iloc[0]) if "wilaya_code" in df_w.columns else 0
    lat  = float(df_w["latitude"].mean())  if "latitude"  in df_w.columns else 28.0
    lon  = float(df_w["longitude"].mean()) if "longitude" in df_w.columns else 3.0

    df_h   = _agg_demand(df_w, horizon, feat_cols)
    if df_h.empty or "demand_mw" not in df_h.columns:
        raise ValueError(f"Pas de données demand_mw pour '{canonical}'.")

    df_sc      = _apply_demand_prep(df_h, prep, feat_cols)
    n_display  = _n_display_points(horizon)
    pred_vals  = _autoregress_demand(model, df_sc, df_h, prep, feat_cols, look_back, n_display)
    labels     = _build_demand_labels(df_h, horizon, n_display)

    arr        = np.array(pred_vals)
    best_idx   = int(np.argmax(arr))
    worst_idx  = int(np.argmin(arr))
    hist_avg   = float(df_w["demand_mw"].mean()) if "demand_mw" in df_w.columns else None

    return {
        "wilaya":         canonical,
        "wilaya_code":    wilaya_code,
        "latitude":       round(lat, 4),
        "longitude":      round(lon, 4),
        "horizon":        horizon,
        "horizon_label":  DEMAND_HORIZON_LABELS.get(horizon, horizon.capitalize()),
        "labels":         labels,
        "demand_mw":      [round(float(v), 4) for v in pred_vals],
        "best_period": {
            "label":     labels[best_idx],
            "demand_mw": round(float(arr[best_idx]), 4),
            "index":     best_idx,
        },
        "worst_period": {
            "label":     labels[worst_idx],
            "demand_mw": round(float(arr[worst_idx]), 4),
            "index":     worst_idx,
        },
        "total_demand_mw":  round(float(arr.sum()), 4),
        "mean_demand_mw":   round(float(arr.mean()), 4),
        "historical_avg":   round(hist_avg, 4) if hist_avg is not None else None,
        "model_name":       model_name,
        "look_back":        look_back,
        "train_period":     "2019–2022",
        "test_period":      "2023",
        "model_metrics": {
            "RMSE": round(float(metrics_d.get("RMSE", 0)), 4),
            "MAE":  round(float(metrics_d.get("MAE",  0)), 4),
            "R2":   round(float(metrics_d.get("R2",   0)), 6),
            "MAPE": round(float(metrics_d.get("MAPE", 0)), 4),
        },
    }


def get_demand_forecast_response(wilaya_query: str, horizon: str) -> dict:
    """
    Wrapper prêt pour la route Flask.
    Retourne { "success": True, "data": {...} }
    """
    result = predict_demand_forecast(wilaya_query, horizon)
    return {"success": True, "data": result}
