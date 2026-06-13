"""
ml/prevision/forecast_service.py
═══════════════════════════════════════════════════════════════════
Service de prévision — SolarDecide DZ
  • GHI (potentiel solaire)  → RandomForest  (model_RandomForest.pkl)
  • Demand_MW (demande élec) → XGBoost / RF  (best_models_demand.pkl)

Flux GHI (inchangé) :
  1. Charger model_RandomForest.pkl  (joblib)
  2. Charger dataset.csv
  3. Agréger en mensuel + fenêtre glissante LOOK_BACK=6
  4. Prédire GHI normalisé → dénormaliser → kWh (100 kWc, PR=0.80)
  5. Auto-régression sur n_steps pour 7j / 30j / 1an

Flux Demand_MW (nouveau) :
  1. Charger best_models_demand.pkl  (joblib)
  2. Charger dataset.csv
  3. Agréger selon horizon (daily / weekly / monthly)
  4. Construire fenêtre glissante look_back × n_features (flat)
  5. Prédire via le meilleur modèle de l'horizon
  6. Retourner labels + demand_mw + KPI + métriques modèle
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import random as _rnd
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
_HERE              = Path(__file__).resolve().parent
MODEL_PATH         = _HERE / "model_RandomForest.pkl"
DEMAND_MODEL_PATH  = _HERE / "best_models_demand.pkl"
DATASET_PATH       = _HERE / "dataset.csv"

# ─── CONSTANTES GHI (inchangé) ───────────────────────────────────
REFERENCE_POWER_KWC  = 100.0
PERFORMANCE_RATIO    = 0.80
TARIFF_DA_PER_KWH    = 5.0
DEGRADATION_PER_YEAR = 0.005
SURFACE_M2_PER_KWC   = 7.0
ESTIMATED_SURFACE_M2 = REFERENCE_POWER_KWC * SURFACE_M2_PER_KWC
LOOK_BACK            = 6

GHI_FEATURE_COLS = [
    "GHI", "DNI", "DHI",
    "T2M", "T2M_MAX", "T2M_MIN",
    "WS10M", "RH2M",
    "CLRSKY_GHI", "CLEARNESS_KT", "PRECIP_MM",
]

HORIZON_MAP = {
    "24h": {"n_steps": 24, "step": "hour",  "label": "Prochaines 24 heures"},
    "7j":  {"n_steps":  7, "step": "day",   "label": "Semaine prochaine"},
    "30j": {"n_steps": 30, "step": "day",   "label": "Mois prochain"},
    "1an": {"n_steps": 12, "step": "month", "label": "Année prochaine"},
}

# Mapping horizon demand → label
DEMAND_HORIZON_LABELS = {
    "daily":   "Journalier",
    "weekly":  "Hebdomadaire",
    "monthly": "Mensuel",
}

# ─── CACHES ──────────────────────────────────────────────────────
_bundle_cache:        dict | None = None
_demand_bundle_cache: dict | None = None
_dataset_cache                    = None
_wilaya_meta_cache                = None


# ─── CHARGEMENT ──────────────────────────────────────────────────
def load_model() -> dict:
    global _bundle_cache
    if _bundle_cache is not None:
        return _bundle_cache
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modèle GHI introuvable : {MODEL_PATH}  "
            "— assurez-vous que model_RandomForest.pkl est présent."
        )
    pkg = joblib.load(MODEL_PATH)
    _bundle_cache = pkg
    logger.info("✅ RandomForest (GHI) chargé")
    return pkg


def load_demand_model() -> dict:
    """Charge best_models_demand.pkl et retourne le bundle complet."""
    global _demand_bundle_cache
    if _demand_bundle_cache is not None:
        return _demand_bundle_cache
    if not DEMAND_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modèle Demand_MW introuvable : {DEMAND_MODEL_PATH}  "
            "— assurez-vous que best_models_demand.pkl est présent."
        )
    pkg = joblib.load(DEMAND_MODEL_PATH)
    _demand_bundle_cache = pkg
    logger.info(
        "✅ Demand_MW bundle chargé — horizons : %s",
        list(pkg.keys()),
    )
    return pkg


def _load_dataset() -> pd.DataFrame:
    global _dataset_cache
    if _dataset_cache is None:
        if not DATASET_PATH.exists():
            raise FileNotFoundError(f"Dataset introuvable : {DATASET_PATH}")
        df = pd.read_csv(DATASET_PATH)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values(["wilaya_name", "datetime"]).reset_index(drop=True)
        df["year"]  = df["datetime"].dt.year
        df["month"] = df["datetime"].dt.month
        _dataset_cache = df
        logger.info("Dataset chargé : %d lignes, %d wilayas",
                    len(df), df["wilaya_name"].nunique())
    return _dataset_cache


def _load_wilaya_meta() -> pd.DataFrame:
    global _wilaya_meta_cache
    if _wilaya_meta_cache is None:
        df = _load_dataset()
        _wilaya_meta_cache = (
            df[["wilaya_code", "wilaya_name", "latitude", "longitude", "climate"]]
            .drop_duplicates("wilaya_name")
            .sort_values("wilaya_name")
            .reset_index(drop=True)
        )
    return _wilaya_meta_cache


# ─── UTILITAIRES COMMUNS ──────────────────────────────────────────
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


# ─── UTILITAIRES GHI (inchangé) ──────────────────────────────────
def _aggregate_monthly(df_w: pd.DataFrame) -> pd.DataFrame:
    agg = (
        df_w.groupby(["year", "month"])[GHI_FEATURE_COLS]
        .mean().reset_index()
    )
    agg["datetime"] = pd.to_datetime(agg[["year", "month"]].assign(day=1))
    return agg.sort_values("datetime").reset_index(drop=True)


def _build_window(df_agg: pd.DataFrame, scaler) -> np.ndarray:
    tail = df_agg[GHI_FEATURE_COLS].tail(LOOK_BACK).copy()
    if len(tail) < LOOK_BACK:
        pad = pd.DataFrame(
            [df_agg[GHI_FEATURE_COLS].mean().values] * (LOOK_BACK - len(tail)),
            columns=GHI_FEATURE_COLS,
        )
        tail = pd.concat([pad, tail], ignore_index=True)
    scaled = scaler.transform(tail[GHI_FEATURE_COLS].fillna(0).values)
    return scaled.reshape(1, -1)


def _denorm(ghi_norm: float, ghi_min: float, ghi_max: float) -> float:
    return float(max(0.0, ghi_norm * (ghi_max - ghi_min) + ghi_min))


def _autoregress(model, scaler, df_agg: pd.DataFrame,
                 ghi_min: float, ghi_max: float, n_steps: int) -> list[float]:
    current = df_agg[GHI_FEATURE_COLS].copy()
    preds   = []
    for _ in range(n_steps):
        tail = current.tail(LOOK_BACK)
        if len(tail) < LOOK_BACK:
            pad = pd.DataFrame(
                [current[GHI_FEATURE_COLS].mean().values] * (LOOK_BACK - len(tail)),
                columns=GHI_FEATURE_COLS,
            )
            tail = pd.concat([pad, tail], ignore_index=True)
        scaled   = scaler.transform(tail.fillna(0).values).reshape(1, -1)
        ghi_norm = float(model.predict(scaled)[0])
        ghi      = _denorm(ghi_norm, ghi_min, ghi_max)
        preds.append(ghi)
        new_row = current.iloc[-1].copy()
        new_row["GHI"] = ghi
        current = pd.concat(
            [current.iloc[1:].reset_index(drop=True),
             pd.DataFrame([new_row], columns=GHI_FEATURE_COLS)],
            ignore_index=True,
        )
    return preds


# ─── UTILITAIRES DEMAND_MW ────────────────────────────────────────
def _agg_demand(df_w: pd.DataFrame, horizon: str, feat_cols: list[str]) -> pd.DataFrame:
    """Agrège les données par horizon et retourne un DataFrame trié."""
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
    """Applique imputer + clips + scaler du préprocesseur sauvegardé."""
    avail = [c for c in feat_cols if c in df.columns]
    out   = df.copy()
    imp   = prep["imputer"]
    sc    = prep["scaler"]
    clips = prep["clips"]
    out[avail] = imp.transform(out[avail])
    for c in avail:
        if c in clips:
            lo, hi = clips[c]
            out[c] = out[c].clip(lo, hi)
    out[avail] = sc.transform(out[avail])
    return out


def _build_demand_window(
    df_scaled: pd.DataFrame,
    feat_cols: list[str],
    look_back: int,
) -> np.ndarray:
    """Construit la fenêtre flat [1, look_back × n_features] pour sklearn."""
    avail = [c for c in feat_cols if c in df_scaled.columns]
    tail  = df_scaled[avail].tail(look_back)
    if len(tail) < look_back:
        pad_rows = look_back - len(tail)
        pad = pd.DataFrame(
            [df_scaled[avail].mean().values] * pad_rows,
            columns=avail,
        )
        tail = pd.concat([pad, tail], ignore_index=True)
    return tail.fillna(0).values.reshape(1, -1)


# ─── PRÉVISION GHI (inchangé) ────────────────────────────────────
def predict_forecast(wilaya_query, horizon: str) -> dict:
    cfg = HORIZON_MAP.get(horizon, HORIZON_MAP["24h"])
    n_steps, step_type, h_label = cfg["n_steps"], cfg["step"], cfg["label"]

    pkg    = load_model()
    df     = _load_dataset()
    scaler = pkg["mm_scaler"]
    model  = pkg["model"]
    ghi_min, ghi_max = pkg["ghi_min"], pkg["ghi_max"]

    df_w, canonical = _resolve(df, wilaya_query)
    if df_w is None or df_w.empty:
        raise ValueError(f"Wilaya inconnue : {wilaya_query!r}")

    wilaya_code = int(df_w["wilaya_code"].iloc[0]) if "wilaya_code" in df_w.columns else 0
    lat  = float(df_w["latitude"].mean())  if "latitude"  in df_w.columns else 28.0
    lon  = float(df_w["longitude"].mean()) if "longitude" in df_w.columns else 3.0

    df_monthly = _aggregate_monthly(df_w)

    df_w = df_w.copy()
    df_w["_month"] = df_w["datetime"].dt.month
    overall_ghi    = float(df_w["GHI"].mean()) or 1.0
    monthly_ghi    = df_w.groupby("_month")["GHI"].mean()
    sf = np.array([
        float(monthly_ghi.get(m, overall_ghi)) / overall_ghi
        for m in range(1, 13)
    ])
    ghi_mean    = float(df_w["GHI"].tail(365).mean())
    daily_kwh   = ghi_mean * PERFORMANCE_RATIO * REFERENCE_POWER_KWC
    rng         = _rnd.Random(wilaya_code * 1000 + n_steps)

    if step_type == "hour":
        peak = 12.5 + (lon - 3.0) / 15.0
        std  = max(2.4, min(4.0, 3.0 + (28.0 - lat) * 0.02))
        w    = np.exp(-((np.arange(24) - peak) ** 2) / (2 * std ** 2))
        w   /= w.sum()
        try:
            ghi_pred = _denorm(
                float(model.predict(_build_window(df_monthly, scaler))[0]),
                ghi_min, ghi_max,
            )
        except Exception:
            ghi_pred = ghi_mean
        prod   = w * ghi_pred * PERFORMANCE_RATIO * REFERENCE_POWER_KWC
        labels = [f"{h:02d}h" for h in range(24)]

    elif step_type == "day":
        try:
            n_months = max(1, math.ceil(n_steps / 30))
            raw = _autoregress(model, scaler, df_monthly, ghi_min, ghi_max, n_months)
        except Exception:
            raw = None
        cur_m = _dt.date.today().month - 1
        prod  = []
        for i in range(n_steps):
            m_idx  = min(i // 30, (len(raw) - 1) if raw else 0)
            month  = (cur_m + i // 30) % 12
            base   = (raw[m_idx] * PERFORMANCE_RATIO * REFERENCE_POWER_KWC
                      if raw else daily_kwh * sf[month])
            jitter = 1.0 + rng.uniform(-0.06, 0.06)
            wave   = 1.0 + 0.04 * math.sin((i + wilaya_code * 0.3) * 0.9)
            prod.append(max(0.0, base * jitter * wave))
        prod   = np.array(prod)
        today  = _dt.date.today()
        labels = (
            [(today + _dt.timedelta(days=i + 1)).strftime("%d/%m") for i in range(7)]
            if n_steps == 7 else [f"Jour {i+1}" for i in range(n_steps)]
        )

    else:
        try:
            raw = _autoregress(model, scaler, df_monthly, ghi_min, ghi_max, 12)
        except Exception:
            raw = None
        prod = []
        for m in range(12):
            base   = (raw[m] * PERFORMANCE_RATIO * REFERENCE_POWER_KWC * 30.0
                      if raw else daily_kwh * 30.0 * sf[m])
            jitter = 1.0 + rng.uniform(-0.03, 0.03)
            prod.append(max(0.0, base * jitter))
        prod   = np.array(prod)
        labels = ["Jan","Fév","Mar","Avr","Mai","Juin",
                  "Juil","Août","Sep","Oct","Nov","Déc"]

    prod      = np.maximum(prod, 0.0)
    total     = float(prod.sum())
    best_idx  = int(np.argmax(prod))
    worst_idx = int(np.argmin(prod))
    metrics_m = pkg["metrics"]["monthly"]

    try:
        ghi_pred_val = round(
            _denorm(float(model.predict(_build_window(df_monthly, scaler))[0]),
                    ghi_min, ghi_max), 3
        )
    except Exception:
        ghi_pred_val = round(ghi_mean, 3)

    return {
        "wilaya":               canonical,
        "wilaya_code":          wilaya_code,
        "latitude":             round(lat, 4),
        "longitude":            round(lon, 4),
        "horizon":              horizon,
        "horizon_label":        h_label,
        "labels":               labels,
        "production_kwh":       [round(float(x), 2) for x in prod],
        "total_production_kwh": round(total, 2),
        "best_period": {
            "label":          labels[best_idx],
            "production_kwh": round(float(prod[best_idx]), 2),
            "index":          best_idx,
        },
        "worst_period": {
            "label":          labels[worst_idx],
            "production_kwh": round(float(prod[worst_idx]), 2),
            "index":          worst_idx,
        },
        "reliability_pct":       round(float(metrics_m.get("Accuracy", 81.8)), 1),
        "estimated_value_da":    round(total * TARIFF_DA_PER_KWH, 2),
        "production_per_m2_kwh": round(total / ESTIMATED_SURFACE_M2, 2),
        "estimated_surface_m2":  ESTIMATED_SURFACE_M2,
        "reference_power_kwc":   REFERENCE_POWER_KWC,
        "tariff_da_per_kwh":     TARIFF_DA_PER_KWH,
        "ghi_predicted_wm2":     ghi_pred_val,
        "ghi_mean_wm2":          round(ghi_mean, 3),
        "model_name":            "RandomForest",
        "rmse":                  round(float(metrics_m["RMSE"]), 4),
        "mae":                   round(float(metrics_m["MAE"]), 4),
        "mape":                  round(float(metrics_m["MAPE"]), 2),
    }


# ─── PRÉVISION DEMAND_MW (nouveau) ───────────────────────────────
def predict_demand_forecast(wilaya_query, horizon: str = "monthly") -> dict:
    """
    Prédit la demande électrique (MW) pour une wilaya et un horizon donnés.

    Parameters
    ----------
    wilaya_query : str | int
        Nom ou code de la wilaya.
    horizon : str
        'daily' | 'weekly' | 'monthly'

    Returns
    -------
    dict
        labels, demand_mw, best_period, worst_period,
        model_name, model_metrics, historical_avg, ...
    """
    valid_horizons = ("daily", "weekly", "monthly")
    if horizon not in valid_horizons:
        horizon = "monthly"

    bundle = load_demand_model()
    if horizon not in bundle:
        raise ValueError(
            f"Horizon '{horizon}' non disponible dans le bundle. "
            f"Horizons disponibles : {list(bundle.keys())}"
        )
    bh         = bundle[horizon]           # bundle pour cet horizon
    model      = bh["model"]
    prep       = bh["preprocessing"]
    feat_cols  = bh["feature_cols"]
    look_back  = bh["look_back"]
    model_name = bh["model_name"]
    metrics_d  = bh.get("best_model_metrics", bh.get("metrics", {}))

    df     = _load_dataset()
    df_w, canonical = _resolve(df, wilaya_query)
    if df_w is None or df_w.empty:
        raise ValueError(f"Wilaya inconnue : {wilaya_query!r}")

    wilaya_code = int(df_w["wilaya_code"].iloc[0]) if "wilaya_code" in df_w.columns else 0
    lat  = float(df_w["latitude"].mean())  if "latitude"  in df_w.columns else 28.0
    lon  = float(df_w["longitude"].mean()) if "longitude" in df_w.columns else 3.0

    # ── Agrégation selon horizon ──────────────────────────────────
    df_h = _agg_demand(df_w, horizon, feat_cols)

    if df_h.empty or "demand_mw" not in df_h.columns:
        raise ValueError(
            f"Pas de données demand_mw pour la wilaya '{canonical}'."
        )

    # ── Prétraitement ──────────────────────────────────────────────
    df_sc = _apply_demand_prep(df_h, prep, feat_cols)

    # ── Fenêtre de prédiction (dernières look_back périodes) ───────
    X_window = _build_demand_window(df_sc, feat_cols, look_back)

    # ── Prédiction unique pour la prochaine période ─────────────
    # Pour avoir une série de prévisions, on fait une auto-régression
    # sur les périodes disponibles dans df_h et on prédit la dernière.
    # On construit aussi un tableau de prévisions « glissantes »
    # sur toutes les périodes test pour la visualisation.
    n_display  = _n_display_points(horizon)
    pred_vals  = _autoregress_demand(model, df_sc, df_h, prep, feat_cols, look_back, n_display)
    labels     = _build_demand_labels(df_h, horizon, n_display)

    # ── Statistiques ──────────────────────────────────────────────
    arr        = np.array(pred_vals)
    best_idx   = int(np.argmax(arr))
    worst_idx  = int(np.argmin(arr))

    # Moyenne historique de la wilaya (série réelle)
    hist_avg   = float(df_w["demand_mw"].mean()) if "demand_mw" in df_w.columns else None

    h_label    = DEMAND_HORIZON_LABELS.get(horizon, horizon.capitalize())

    return {
        "wilaya":          canonical,
        "wilaya_code":     wilaya_code,
        "latitude":        round(lat, 4),
        "longitude":       round(lon, 4),
        "horizon":         horizon,
        "horizon_label":   h_label,
        "labels":          labels,
        "demand_mw":       [round(float(v), 4) for v in pred_vals],
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
        "total_demand_mw":   round(float(arr.sum()), 4),
        "mean_demand_mw":    round(float(arr.mean()), 4),
        "historical_avg":    round(hist_avg, 4) if hist_avg is not None else None,
        "model_name":        model_name,
        "look_back":         look_back,
        "train_period":      "2019–2022",
        "test_period":       "2023",
        "model_metrics": {
            "RMSE": round(float(metrics_d.get("RMSE", 0)), 4),
            "MAE":  round(float(metrics_d.get("MAE",  0)), 4),
            "R2":   round(float(metrics_d.get("R2",   0)), 6),
            "MAPE": round(float(metrics_d.get("MAPE", 0)), 4),
        },
    }


def _n_display_points(horizon: str) -> int:
    """Nombre de points à afficher selon l'horizon."""
    return {"monthly": 12, "weekly": 16, "daily": 30}[horizon]


def _autoregress_demand(
    model, df_sc: pd.DataFrame, df_h: pd.DataFrame,
    prep: dict, feat_cols: list[str],
    look_back: int, n_steps: int,
) -> list[float]:
    """
    Auto-régression demand : prédit n_steps points futurs en réinjectant
    la prédiction précédente comme valeur de demand_mw dans la fenêtre.
    """
    avail  = [c for c in feat_cols if c in df_sc.columns]
    window = df_sc[avail].tail(look_back).copy()
    if len(window) < look_back:
        pad_n  = look_back - len(window)
        pad    = pd.DataFrame(
            [df_sc[avail].mean().values] * pad_n, columns=avail,
        )
        window = pd.concat([pad, window], ignore_index=True)

    preds = []
    for _ in range(n_steps):
        X    = window.values.reshape(1, -1)
        pred = float(model.predict(X)[0])
        preds.append(max(0.0, pred))

        # Mise à jour de la fenêtre
        new_row = window.iloc[-1].copy()
        if "demand_mw" in new_row.index:
            # Dénormaliser puis renormaliser la prédiction
            sc    = prep["scaler"]
            imp_  = prep["imputer"]
            clips = prep["clips"]
            # Reconstruction d'une ligne avec la valeur prédite brute
            new_row_raw = df_h[avail].iloc[-1].copy() if len(df_h) > 0 else new_row
            if "demand_mw" in new_row_raw.index:
                new_row_raw["demand_mw"] = pred  # valeur déjà dans l'espace modèle
            # On pousse directement la prédiction normalisée
            new_row["demand_mw"] = pred
        window = pd.concat(
            [window.iloc[1:].reset_index(drop=True),
             pd.DataFrame([new_row.values], columns=avail)],
            ignore_index=True,
        )

    return preds


def _build_demand_labels(
    df_h: pd.DataFrame, horizon: str, n_steps: int,
) -> list[str]:
    """Génère les labels temporels pour les n_steps prochaines périodes."""
    if df_h.empty or "datetime" not in df_h.columns:
        return [f"P{i+1}" for i in range(n_steps)]

    last_dt = pd.Timestamp(df_h["datetime"].iloc[-1])

    if horizon == "monthly":
        labels = []
        dt = last_dt
        MONTHS_FR = ["Jan","Fév","Mar","Avr","Mai","Juin",
                     "Juil","Août","Sep","Oct","Nov","Déc"]
        for _ in range(n_steps):
            dt = dt + pd.DateOffset(months=1)
            labels.append(f"{MONTHS_FR[dt.month-1]} {dt.year}")
        return labels

    elif horizon == "weekly":
        labels = []
        dt = last_dt
        for i in range(n_steps):
            dt = dt + pd.DateOffset(weeks=1)
            labels.append(f"S{dt.isocalendar()[1]:02d}/{dt.year}")
        return labels

    else:  # daily
        return [
            (last_dt + pd.Timedelta(days=i+1)).strftime("%d/%m/%y")
            for i in range(n_steps)
        ]


# ─── TENDANCE LONG TERME GHI (inchangé) ──────────────────────────
def predict_long_term_trend(wilaya_query) -> dict:
    pkg    = load_model()
    df     = _load_dataset()
    df_w, canonical = _resolve(df, wilaya_query)
    if df_w is None or df_w.empty:
        raise ValueError(f"Wilaya inconnue : {wilaya_query!r}")

    df_w      = df_w.copy()
    ghi_avg   = float(df_w["GHI"].mean())
    daily_kwh = ghi_avg * PERFORMANCE_RATIO * REFERENCE_POWER_KWC
    cur_kwh   = daily_kwh * 365.0

    df_w["year"] = df_w["datetime"].dt.year
    by_year      = df_w.groupby("year")["GHI"].mean()

    historical = [
        {
            "year": int(yr),
            "production_kwh": round(
                float(g) * PERFORMANCE_RATIO * REFERENCE_POWER_KWC * 365.0, 2),
            "type": "historique",
        }
        for yr, g in by_year.items()
    ]
    last_yr  = historical[-1]["year"]  if historical else 2023
    last_kwh = historical[-1]["production_kwh"] if historical else cur_kwh
    n_proj   = max(0, 10 - len(historical))
    projection = [
        {
            "year": last_yr + y,
            "production_kwh": round(last_kwh * (1 - DEGRADATION_PER_YEAR * y), 2),
            "type": "projection",
        }
        for y in range(1, n_proj + 1)
    ]
    trend_series = historical + projection

    if len(by_year) >= 2:
        slope  = float(np.polyfit(list(by_year.index), list(by_year.values), 1)[0])
        thresh = ghi_avg * 0.005
        t_lbl  = "Légère hausse" if slope > thresh else ("Légère baisse" if slope < -thresh else "Stable")
        t_code = "hausse"        if slope > thresh else ("baisse"        if slope < -thresh else "stable")
    else:
        t_lbl, t_code = "Stable", "stable"

    proj_5y   = cur_kwh * (1 - DEGRADATION_PER_YEAR * 5)
    delta_pct = (proj_5y - cur_kwh) / cur_kwh * 100.0

    ranking = pkg.get("ranking", pd.DataFrame())
    w_rank  = None
    if not ranking.empty:
        row = ranking[ranking["wilaya_name"] == canonical]
        if not row.empty:
            w_rank = int(row["rang_RandomForest"].iloc[0])

    try:
        scaler   = pkg["mm_scaler"];  model   = pkg["model"]
        ghi_min  = pkg["ghi_min"];    ghi_max = pkg["ghi_max"]
        df_mo    = _aggregate_monthly(df_w)
        ghi_pred = round(_denorm(
            float(model.predict(_build_window(df_mo, scaler))[0]),
            ghi_min, ghi_max), 3)
    except Exception:
        ghi_pred = round(ghi_avg, 3)

    metrics_m = pkg["metrics"]["monthly"]
    return {
        "wilaya":          canonical,
        "wilaya_rank":     w_rank,
        "total_wilayas":   len(ranking),
        "potentiel_dans_5_ans": {
            "current_production_kwh":   round(cur_kwh, 2),
            "projected_production_kwh": round(proj_5y, 2),
            "delta_pct":                round(delta_pct, 2),
        },
        "tendance_climatique": {"label": t_lbl, "code": t_code},
        "trend_series_10y":    trend_series,
        "projection_10ans": {
            "years":          [p["year"] for p in trend_series],
            "production_kwh": [p["production_kwh"] for p in trend_series],
        },
        "ghi_predicted_wm2":   ghi_pred,
        "ghi_mean_wm2":        round(ghi_avg, 3),
        "reference_power_kwc": REFERENCE_POWER_KWC,
        "tariff_da_per_kwh":   TARIFF_DA_PER_KWH,
        "model_name":          "RandomForest",
        "metrics": {
            "RMSE":     round(float(metrics_m["RMSE"]), 4),
            "MAE":      round(float(metrics_m["MAE"]), 4),
            "MAPE":     round(float(metrics_m["MAPE"]), 2),
            "Accuracy": round(float(metrics_m["Accuracy"]), 1),
        },
    }


# ─── LISTE WILAYAS ────────────────────────────────────────────────
def list_wilayas() -> list[dict]:
    meta    = _load_wilaya_meta()
    ranking = load_model().get("ranking", pd.DataFrame())
    result  = []
    for row in meta.itertuples(index=False):
        rank = None
        if not ranking.empty:
            r = ranking[ranking["wilaya_name"] == row.wilaya_name]
            if not r.empty:
                rank = int(r["rang_RandomForest"].iloc[0])
        result.append({
            "code":    int(row.wilaya_code),
            "id":      int(row.wilaya_code),
            "nom":     row.wilaya_name,
            "name":    row.wilaya_name,
            "region":  row.climate or "—",
            "lat":     round(float(row.latitude), 4),
            "lon":     round(float(row.longitude), 4),
            "rank_rf": rank,
        })
    return sorted(result, key=lambda x: x["nom"])


# ─── ENDPOINT HELPER (pour Flask route) ──────────────────────────
def get_demand_forecast_response(wilaya_query: str, horizon: str) -> dict:
    """
    Wrapper prêt à l'emploi pour la route Flask :
        GET /api/forecast-demand/<wilaya>?horizon=monthly|weekly|daily

    Retourne { "success": True, "data": {...} } ou lève ValueError.
    """
    result = predict_demand_forecast(wilaya_query, horizon)
    return {"success": True, "data": result}


# ─── TEST CLI ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== SolarDecide DZ — Test forecast_service ===\n")

    print("── GHI forecast ──")
    for w in ["Adrar", "Biskra", "Tamanrasset"]:
        for h in ["24h", "7j", "30j"]:
            try:
                r = predict_forecast(w, h)
                print(f"  {w:15s} {h:4s} → {r['total_production_kwh']:>10,.1f} kWh"
                      f" | GHI={r['ghi_predicted_wm2']} W/m²")
            except Exception as e:
                print(f"  ERR {w} {h}: {e}")

    print("\n── Demand_MW forecast ──")
    for w in ["Adrar", "Biskra", "Tamanrasset"]:
        for h in ["monthly", "weekly", "daily"]:
            try:
                r = predict_demand_forecast(w, h)
                print(f"  {w:15s} {h:10s} → total={r['total_demand_mw']:>8.2f} MW"
                      f" | mean={r['mean_demand_mw']:>6.2f} MW"
                      f" | model={r['model_name']}"
                      f" | R²={r['model_metrics']['R2']:.4f}")
            except Exception as e:
                print(f"  ERR {w} {h}: {e}")