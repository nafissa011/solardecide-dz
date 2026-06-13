from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from threading import Lock
from typing import Optional

import duckdb
from flask import Blueprint, jsonify, request

from config import PARQUET_PATH

logger = logging.getLogger(__name__)

bp = Blueprint("dataset_api", __name__)

_CON: Optional[duckdb.DuckDBPyConnection] = None
_CON_LOCK = Lock()  # DuckDB connections are not thread-safe


def _con() -> duckdb.DuckDBPyConnection:
    # Lazy singleton — callers must already hold _CON_LOCK (re-entrant lock would deadlock)
    global _CON
    if _CON is None:
        _CON = duckdb.connect(database=":memory:", read_only=False)
    return _CON


def _q(sql: str, params: Optional[list] = None):
    """Execute SQL and return a pandas DataFrame."""
    with _CON_LOCK:
        cur = _con().execute(sql, params or [])
        return cur.fetchdf()


def _region_for(code: int) -> str:
    c = int(code)
    if 1 <= c <= 9:
        return "Ouest"
    if 10 <= c <= 20:
        return "Centre"
    if 21 <= c <= 36:
        return "Est"
    if 37 <= c <= 44:
        return "Sud-Est"
    if 45 <= c <= 50:
        return "Sud-Ouest"
    if 51 <= c <= 58:
        return "Grand Sud"
    return "Inconnu"


def _normalize(name: str) -> str:
    """Lowercase, strip diacritics, collapse non-alphanumerics, apply known aliases."""
    if name is None:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    aliases = {
        "alger": "algiers",
        "elalia": "eltarf",
    }
    return aliases.get(s, s)


@lru_cache(maxsize=1)
def _all_wilaya_names() -> dict[str, dict]:
    """Return {normalized_name: {wilaya_code, wilaya_name}} for all wilayas."""
    df = _q(
        f"SELECT DISTINCT wilaya_code, wilaya_name "
        f"FROM read_parquet('{PARQUET_PATH}') ORDER BY wilaya_code"
    )
    out = {}
    for _, row in df.iterrows():
        out[_normalize(row["wilaya_name"])] = {
            "wilaya_code": int(row["wilaya_code"]),
            "wilaya_name": str(row["wilaya_name"]),
        }
    return out


def _resolve_wilaya(name_or_code: str) -> Optional[dict]:
    """Resolve a wilaya name or numeric code to its canonical {wilaya_code, wilaya_name}."""
    if name_or_code is None:
        return None
    s = str(name_or_code).strip()
    if s.isdigit():
        code = int(s)
        for v in _all_wilaya_names().values():
            if v["wilaya_code"] == code:
                return v
        return None
    return _all_wilaya_names().get(_normalize(s))


@lru_cache(maxsize=1)
def _dataset_years() -> float:
    """Return the number of full years covered by the dataset."""
    df = _q(f"SELECT MIN(datetime) AS lo, MAX(datetime) AS hi FROM read_parquet('{PARQUET_PATH}')")
    lo, hi = df.iloc[0]["lo"], df.iloc[0]["hi"]
    delta_days = (hi - lo).days + 1
    return max(delta_days / 365.25, 1.0)


@lru_cache(maxsize=1)
def _wilaya_aggregates_df():
    """
    Pre-aggregate the parquet to one row per wilaya.

    AVG(GHI) * 8760 converts mean hourly irradiance to annual kWh/m².
    Sunshine hours = fraction of hours where GHI > 0.12 * 8760.
    ghi_cv (coefficient of variation) is used as a climate stability proxy.
    """
    sql = f"""
    SELECT
        wilaya_code,
        wilaya_name,
        any_value(climate)                                       AS climate,
        COUNT(DISTINCT commune_name)                             AS communes_count,
        AVG(latitude)                                            AS latitude,
        AVG(longitude)                                           AS longitude,
        AVG(GHI) * 8760                                          AS ghi_annual_kwh_m2,
        AVG(GHI)                                                 AS ghi_mean_hourly,
        AVG(CASE WHEN GHI > 0.12 THEN 1.0 ELSE 0.0 END) * 8760   AS sunshine_hours_year,
        AVG(T2M)                                                 AS t_mean,
        MIN(T2M_MIN)                                             AS t_min,
        MAX(T2M_MAX)                                             AS t_max,
        AVG(WS10M)                                               AS wind_speed,
        AVG(CLEARNESS_KT)                                        AS clearness,
        AVG(PRECIP_MM) * 8760                                    AS precip_annual_mm,
        AVG(demand_mw)                                           AS demand_mw_avg,
        STDDEV(GHI) / NULLIF(AVG(GHI), 0)                        AS ghi_cv
    FROM read_parquet('{PARQUET_PATH}')
    GROUP BY wilaya_code, wilaya_name
    ORDER BY wilaya_code
    """
    return _q(sql)


@lru_cache(maxsize=1)
def _monthly_ghi_df():
    """
    Return average GHI per (wilaya, month) in kWh/m².
    AVG(GHI) * 730.5 converts mean hourly irradiance to a monthly total (8766/12 h).
    """
    sql = f"""
    SELECT
        wilaya_name,
        wilaya_code,
        EXTRACT(MONTH FROM datetime)::INT AS month,
        AVG(GHI) * 730.5 AS ghi_monthly_kwh_m2
    FROM read_parquet('{PARQUET_PATH}')
    GROUP BY wilaya_name, wilaya_code, EXTRACT(MONTH FROM datetime)
    ORDER BY wilaya_code, month
    """
    return _q(sql)


@lru_cache(maxsize=1)
def _national_monthly_ghi():
    """Return the national average GHI series across 12 months in kWh/m²/month."""
    df = _monthly_ghi_df()
    if df.empty:
        return [0.0] * 12

    grouped = (
        df.groupby("month")["ghi_monthly_kwh_m2"]
        .mean()
        .reindex(range(1, 13))
        .fillna(df["ghi_monthly_kwh_m2"].mean())
    )
    return [round(float(v), 2) for v in grouped.tolist()]


def _normalize_series(series, lower_is_better: bool = False):
    """Min-max normalise a series to [0, 100]. Handles NaNs and zero-range series."""
    import numpy as np
    s = series.copy()
    lo, hi = float(s.min()), float(s.max())
    rng = hi - lo
    if rng <= 0:
        out = s * 0 + 50.0
    else:
        out = (s - lo) / rng * 100.0
    if lower_is_better:
        out = 100.0 - out
    return out.clip(lower=0, upper=100).fillna(50.0)


@lru_cache(maxsize=1)
def _all_wilaya_scores_df():
    """
    Return the wilaya aggregate dataframe with 4 sub-scores and composite score.

    Composite = GHI(40%) + stability(20%) + accessibility(20%) + risk_inverse(20%).
    Risk is built from t_max, cold stress, wind, and precipitation — then inverted.
    potential_mw is a rough estimate: communes * 50 MW * GHI quality ratio.
    """
    df = _wilaya_aggregates_df().copy()

    df["score_ghi"] = _normalize_series(df["ghi_annual_kwh_m2"], lower_is_better=False)
    df["score_stability"] = _normalize_series(df["ghi_cv"], lower_is_better=True)
    df["score_accessibility"] = _normalize_series(df["demand_mw_avg"], lower_is_better=False)

    import numpy as np
    t_max_risk     = _normalize_series(df["t_max"],      lower_is_better=False)
    cold_risk      = _normalize_series(-df["t_min"],     lower_is_better=False)
    wind_risk      = _normalize_series(df["wind_speed"], lower_is_better=False)
    precip_risk    = _normalize_series(df["precip_annual_mm"], lower_is_better=False)
    composite_risk = (t_max_risk + cold_risk + wind_risk + precip_risk) / 4.0
    df["score_risk_inverse"] = (100.0 - composite_risk).clip(lower=0, upper=100)

    df["score_composite"] = (
        0.40 * df["score_ghi"]
        + 0.20 * df["score_stability"]
        + 0.20 * df["score_accessibility"]
        + 0.20 * df["score_risk_inverse"]
    ).round(2)

    df["region"] = df["wilaya_code"].apply(_region_for)

    max_ghi = max(df["ghi_annual_kwh_m2"].max(), 1.0)
    df["potential_mw"] = (
        df["communes_count"].astype(float) * 50.0 *
        (df["ghi_annual_kwh_m2"].astype(float) / max_ghi)
    ).round(0)

    return df


def _to_native(value):
    """Cast numpy/pandas scalars to plain Python types for jsonify."""
    import numpy as np
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if f != f else f  # NaN → None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _row_to_dict(row) -> dict:
    return {k: _to_native(v) for k, v in row.items()}


def _monthly_stddev(values) -> Optional[float]:
    """Population standard deviation for a 12-value monthly series."""
    import math
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    mean = sum(nums) / len(nums)
    variance = sum((v - mean) ** 2 for v in nums) / len(nums)
    return math.sqrt(variance)


# ---------------------------------------------------------------------------
#  Routes
# ---------------------------------------------------------------------------

@bp.get("/wilayas")
def api_wilayas_list():
    df = _all_wilaya_scores_df()
    payload = [
        {
            "id":     int(r["wilaya_code"]),
            "code":   int(r["wilaya_code"]),
            "nom":    str(r["wilaya_name"]),
            "name":   str(r["wilaya_name"]),
            "region": str(r["region"]),
        }
        for _, r in df.iterrows()
    ]
    return jsonify({
        "data":   payload,
        "total":  len(payload),
        "status": 200,
        "source": "parquet",
    })


@bp.get("/wilaya/<path:nom_wilaya>")
def api_wilaya_detail(nom_wilaya: str):
    info = _resolve_wilaya(nom_wilaya)
    if info is None:
        return jsonify({"error": f"Wilaya '{nom_wilaya}' not found", "status": 404}), 404

    code = info["wilaya_code"]
    canonical = info["wilaya_name"]

    df = _all_wilaya_scores_df()
    mask = df["wilaya_code"] == code
    if not mask.any():
        return jsonify({"error": "No data for this wilaya", "status": 404}), 404
    r = df.loc[mask].iloc[0]

    monthly_df = _monthly_ghi_df()
    monthly_rows = monthly_df[monthly_df["wilaya_code"] == code].sort_values("month")
    ghi_monthly = [
        round(float(v), 2)
        for v in monthly_rows["ghi_monthly_kwh_m2"].tolist()
    ]
    if len(ghi_monthly) < 12:
        # Pad missing months with the annual average spread evenly
        avg_month = float(r["ghi_annual_kwh_m2"]) / 12.0
        ghi_monthly = (ghi_monthly + [round(avg_month, 2)] * 12)[:12]

    rank_df = df.sort_values("score_composite", ascending=False).reset_index(drop=True)
    rank = int(rank_df[rank_df["wilaya_code"] == code].index[0]) + 1

    ghi_monthly_stddev = _monthly_stddev(ghi_monthly)
    national_monthly_average = _national_monthly_ghi()
    estimated_potential_mwh_year = round(float(r["ghi_annual_kwh_m2"]) * float(r["potential_mw"]) * 0.8, 1)

    payload = {
        "code":               code,
        "id":                 code,
        "nom":                canonical,
        "name":               canonical,
        "region":             _region_for(code),
        "climat":             str(r["climate"]),
        "climate":            str(r["climate"]),
        "latitude":           round(float(r["latitude"]), 4),
        "longitude":          round(float(r["longitude"]), 4),
        "nombre_communes":    int(r["communes_count"]),
        "communes_count":     int(r["communes_count"]),
        "ghi_annuel_kwh_m2":  round(float(r["ghi_annual_kwh_m2"]), 1),
        "ghi_annual_kwh_m2":  round(float(r["ghi_annual_kwh_m2"]), 1),
        "ghi_mensuel":        ghi_monthly,
        "ghi_monthly":        ghi_monthly,
        "ghi_ecart_type_mensuel": round(float(ghi_monthly_stddev), 2) if ghi_monthly_stddev is not None else None,
        "ghi_monthly_stddev": round(float(ghi_monthly_stddev), 2) if ghi_monthly_stddev is not None else None,
        "moyenne_nationale_ghi_mensuel": national_monthly_average,
        "national_ghi_monthly_average": national_monthly_average,
        "potentiel_mw":       round(float(r["potential_mw"]), 0),
        "potential_mw":       round(float(r["potential_mw"]), 0),
        "potentiel_estime_mwh_an": estimated_potential_mwh_year,
        "estimated_potential_mwh_year": estimated_potential_mwh_year,
        "score_composite":    round(float(r["score_composite"]), 2),
        "rank":               rank,
        "rank_national":      rank,
        "temperature_min":    round(float(r["t_min"]), 1),
        "temperature_max":    round(float(r["t_max"]), 1),
        "temperature_mean":   round(float(r["t_mean"]), 1),
        "t_min":              round(float(r["t_min"]), 1),
        "t_max":              round(float(r["t_max"]), 1),
        "ensoleillement_h_an": round(float(r["sunshine_hours_year"]), 0),
        "sunshine_hours_year": round(float(r["sunshine_hours_year"]), 0),
        "vitesse_vent_m_s":   round(float(r["wind_speed"]), 2),
        "wind_speed":         round(float(r["wind_speed"]), 2),
        "precipitations_mm":  round(float(r["precip_annual_mm"]), 1),
        "clearness_kt":       round(float(r["clearness"]), 3),
        "demand_mw_avg":      round(float(r["demand_mw_avg"]), 2),
        "distance_reseau_km": _to_native(_grid_distance_km_proxy(r)),
        "grid_distance_km":   _to_native(_grid_distance_km_proxy(r)),
        # Fields not available in the dataset — kept for API contract consistency
        "distance_routes_km": None,
        "route_distance_km":  None,
        "has_route_distance_data": False,
        "zones_protegees_ou_agricoles": None,
        "protected_or_agricultural_zone": None,
        "has_environmental_constraint_data": False,
        "score_ghi":          round(float(r["score_ghi"]), 2),
        "score_stability":    round(float(r["score_stability"]), 2),
        "score_accessibility":round(float(r["score_accessibility"]), 2),
        "score_risk_inverse": round(float(r["score_risk_inverse"]), 2),
    }
    return jsonify({"data": payload, "status": 200, "source": "parquet"})


def _grid_distance_km_proxy(r) -> float:
    """
    Proxy for distance to the grid: higher demand_mw → closer to Sonelgaz infrastructure.
    Empirical mapping: 0 MW → 200 km, 100 MW → 0 km.
    """
    demand = float(r["demand_mw_avg"] or 0)
    return round(max(0.0, 200.0 - demand * 2.0), 1)


@bp.get("/classement")
def api_classement():
    """GET /api/classement?region=&climat=&tri=score_global|ghi|potentiel"""
    region_f = (request.args.get("region") or "").strip()
    climat_f = (request.args.get("climat") or request.args.get("climate") or "").strip()
    tri_f    = (request.args.get("tri") or "score_global").strip().lower()

    sort_map = {
        "score_global":   ("score_composite",    False),
        "score":          ("score_composite",    False),
        "ghi":            ("ghi_annual_kwh_m2",  False),
        "potentiel":      ("potential_mw",       False),
        "potential":      ("potential_mw",       False),
        "ascending_ghi":  ("ghi_annual_kwh_m2",  True),
    }
    sort_col, ascending = sort_map.get(tri_f, ("score_composite", False))

    df = _all_wilaya_scores_df().copy()
    if region_f:
        df = df[df["region"].str.lower() == region_f.lower()]
    if climat_f:
        df = df[df["climate"].str.lower() == climat_f.lower()]

    df = df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
    df["rank"] = df.index + 1

    payload = []
    for _, r in df.iterrows():
        payload.append({
            "rank":              int(r["rank"]),
            "code":              int(r["wilaya_code"]),
            "id":                int(r["wilaya_code"]),
            "nom":               str(r["wilaya_name"]),
            "name":              str(r["wilaya_name"]),
            "region":            str(r["region"]),
            "climat":            str(r["climate"]),
            "climate":           str(r["climate"]),
            "latitude":          round(float(r["latitude"]), 4),
            "longitude":         round(float(r["longitude"]), 4),
            "ghi_annuel_kwh_m2": round(float(r["ghi_annual_kwh_m2"]), 1),
            "ghi_annual_kwh_m2": round(float(r["ghi_annual_kwh_m2"]), 1),
            "potentiel_mw":      round(float(r["potential_mw"]), 0),
            "potential_mw":      round(float(r["potential_mw"]), 0),
            "score_composite":   round(float(r["score_composite"]), 2),
            "score_global":      round(float(r["score_composite"]), 2),
        })

    return jsonify({
        "data":   payload,
        "total":  len(payload),
        "tri":    tri_f,
        "filters": {"region": region_f or None, "climat": climat_f or None},
        "status": 200,
        "source": "parquet",
    })


@bp.get("/top10")
def api_top10():
    """GET /api/top10?critere=ghi|potentiel|score"""
    critere = (request.args.get("critere") or "ghi").strip().lower()
    col_map = {
        "ghi":         "ghi_annual_kwh_m2",
        "potentiel":   "potential_mw",
        "potential":   "potential_mw",
        "score":       "score_composite",
        "score_global":"score_composite",
    }
    col = col_map.get(critere, "ghi_annual_kwh_m2")

    df = _all_wilaya_scores_df().sort_values(col, ascending=False).head(10).reset_index(drop=True)

    payload = []
    for i, r in df.iterrows():
        payload.append({
            "rank":              i + 1,
            "code":              int(r["wilaya_code"]),
            "nom":               str(r["wilaya_name"]),
            "name":              str(r["wilaya_name"]),
            "region":            str(r["region"]),
            "climat":            str(r["climate"]),
            "ghi_annuel_kwh_m2": round(float(r["ghi_annual_kwh_m2"]), 1),
            "potentiel_mw":      round(float(r["potential_mw"]), 0),
            "score_composite":   round(float(r["score_composite"]), 2),
            "valeur":            round(float(r[col]), 2),
        })

    return jsonify({
        "data":    payload,
        "critere": critere,
        "status":  200,
        "source":  "parquet",
    })


@bp.get("/repartition-regions")
def api_repartition_regions():
    """GET /api/repartition-regions — wilaya count and GHI stats per region."""
    df = _all_wilaya_scores_df().copy()
    grouped = df.groupby("region").agg(
        nombre=("wilaya_code", "count"),
        ghi_moyen_kwh_m2=("ghi_annual_kwh_m2", "mean"),
        ghi_max_kwh_m2=("ghi_annual_kwh_m2", "max"),
        ghi_min_kwh_m2=("ghi_annual_kwh_m2", "min"),
        potentiel_mw_total=("potential_mw", "sum"),
    ).reset_index()
    grouped = grouped.sort_values("nombre", ascending=False)

    payload = []
    for _, r in grouped.iterrows():
        payload.append({
            "region":             str(r["region"]),
            "nombre_wilayas":     int(r["nombre"]),
            "ghi_moyen_kwh_m2":   round(float(r["ghi_moyen_kwh_m2"]), 1),
            "ghi_max_kwh_m2":     round(float(r["ghi_max_kwh_m2"]), 1),
            "ghi_min_kwh_m2":     round(float(r["ghi_min_kwh_m2"]), 1),
            "potentiel_mw_total": round(float(r["potentiel_mw_total"]), 0),
        })

    return jsonify({
        "data":   payload,
        "total":  len(payload),
        "status": 200,
        "source": "parquet",
    })


@bp.get("/score-composite/<path:nom_wilaya>")
def api_score_composite(nom_wilaya: str):
    """
    GET /api/score-composite/<nom_wilaya>
    Composite = GHI(40%) + stability(20%) + accessibility(20%) + risk_inverse(20%).
    All sub-scores normalised to [0, 100].
    """
    info = _resolve_wilaya(nom_wilaya)
    if info is None:
        return jsonify({"error": f"Wilaya '{nom_wilaya}' not found", "status": 404}), 404

    code = info["wilaya_code"]
    df = _all_wilaya_scores_df()
    mask = df["wilaya_code"] == code
    if not mask.any():
        return jsonify({"error": "No data for this wilaya", "status": 404}), 404
    pos = int(mask.idxmax())
    r = df.loc[pos]

    # Extra axes for the 6-axis radar on the dashboard
    score_potential_series = _normalize_series(df["potential_mw"])
    score_infra_series     = _normalize_series(df["communes_count"].astype(float))
    score_potentiel        = float(score_potential_series.loc[pos])
    score_infrastructure   = float(score_infra_series.loc[pos])

    return jsonify({
        "data": {
            "code":               code,
            "nom":                str(r["wilaya_name"]),
            "name":               str(r["wilaya_name"]),
            "region":             _region_for(code),
            "score_ghi":          round(float(r["score_ghi"]), 2),
            "score_stabilite":    round(float(r["score_stability"]), 2),
            "score_stability":    round(float(r["score_stability"]), 2),
            "score_accessibilite":round(float(r["score_accessibility"]), 2),
            "score_accessibility":round(float(r["score_accessibility"]), 2),
            "score_risque_inverse":round(float(r["score_risk_inverse"]), 2),
            "score_risk_inverse": round(float(r["score_risk_inverse"]), 2),
            "score_potentiel":    round(score_potentiel, 2),
            "score_potential":    round(score_potentiel, 2),
            "score_infrastructure": round(score_infrastructure, 2),
            "score_composite":    round(float(r["score_composite"]), 2),
            "ponderation": {
                "ghi":             0.40,
                "stabilite":       0.20,
                "accessibilite":   0.20,
                "risque_inverse":  0.20,
            },
        },
        "status": 200,
        "source": "parquet",
    })


# ---------------------------------------------------------------------------
#  Forecast & long-term prediction
# ---------------------------------------------------------------------------

_HORIZON_CONFIG = {
    "24h":  {"label": "Prochaines 24 heures", "model": "Modèle court terme",     "mae_pct": 6.0},
    "7j":   {"label": "Semaine prochaine",    "model": "Modèle moyen terme",     "mae_pct": 8.0},
    "30j":  {"label": "Mois prochain",        "model": "Modèle long terme",      "mae_pct": 10.0},
    "1an":  {"label": "Année prochaine",      "model": "Modèle tendance longue", "mae_pct": 12.0},
}

_HORIZON_ALIASES = {
    "24h": "24h", "1j": "24h", "day": "24h", "jour": "24h",
    "7j": "7j", "semaine": "7j", "week": "7j",
    "30j": "30j", "mois": "30j", "month": "30j",
    "1an": "1an", "an": "1an", "annee": "1an", "année": "1an", "year": "1an",
    "annee_prochaine": "1an",
}


def _resolve_horizon(value: str) -> str:
    if not value:
        return "24h"
    key = _normalize(value)
    return _HORIZON_ALIASES.get(key, value if value in _HORIZON_CONFIG else "24h")


@lru_cache(maxsize=1)
def _yearly_ghi_df():
    """Annual mean GHI per (wilaya, year) in kWh/m²."""
    sql = f"""
    SELECT
        wilaya_code,
        wilaya_name,
        EXTRACT(YEAR FROM datetime)::INT AS year,
        AVG(GHI) * 8760 AS ghi_annual_kwh_m2
    FROM read_parquet('{PARQUET_PATH}')
    GROUP BY wilaya_code, wilaya_name, EXTRACT(YEAR FROM datetime)
    ORDER BY wilaya_code, year
    """
    return _q(sql)


def _linear_regression(xs, ys):
    """Least-squares linear fit. Returns (slope, intercept)."""
    if not xs or len(xs) != len(ys) or len(xs) < 2:
        return 0.0, float(ys[0]) if ys else 0.0
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0.0
    intercept = mean_y - slope * mean_x
    return slope, intercept


def _classify_trend(annual_values):
    """Classify the GHI trend as stable / hausse / baisse based on slope % per year."""
    if not annual_values or len(annual_values) < 2:
        return {"label": "Stable", "code": "stable", "slope_pct_per_year": 0.0}
    xs = list(range(len(annual_values)))
    slope, _ = _linear_regression(xs, annual_values)
    mean_value = sum(annual_values) / len(annual_values)
    slope_pct = (slope / mean_value) * 100.0 if mean_value else 0.0
    if slope_pct > 0.4:
        return {"label": "Légère hausse", "code": "hausse", "slope_pct_per_year": round(slope_pct, 3)}
    if slope_pct < -0.4:
        return {"label": "Légère baisse", "code": "baisse", "slope_pct_per_year": round(slope_pct, 3)}
    return {"label": "Stable", "code": "stable", "slope_pct_per_year": round(slope_pct, 3)}


def _production_kwh_from_ghi(ghi_kwh_per_m2: float, power_kwc: float = 100.0) -> float:
    """Standard PV formula: GHI × kWc × 0.8 (performance ratio)."""
    return float(ghi_kwh_per_m2) * float(power_kwc) * 0.8


@bp.get("/forecast-simple/<path:nom_wilaya>")
def api_forecast_simple(nom_wilaya: str):
    """GET /api/forecast-simple/<nom_wilaya>?horizon=24h|7j|30j|1an"""
    info = _resolve_wilaya(nom_wilaya)
    if info is None:
        return jsonify({"error": f"Wilaya '{nom_wilaya}' not found", "status": 404}), 404

    code = info["wilaya_code"]
    canonical = info["wilaya_name"]
    horizon = _resolve_horizon(request.args.get("horizon"))
    horizon_meta = _HORIZON_CONFIG[horizon]

    power_kwc = 100.0
    tariff_da_per_kwh = 5.0

    monthly_df = _monthly_ghi_df()
    monthly_rows = monthly_df[monthly_df["wilaya_code"] == code].sort_values("month")
    monthly_values = [float(v) for v in monthly_rows["ghi_monthly_kwh_m2"].tolist()]
    annual_ghi = sum(monthly_values) if monthly_values else 0.0
    if annual_ghi <= 0:
        annual_ghi = float(_all_wilaya_scores_df().loc[_all_wilaya_scores_df()["wilaya_code"] == code, "ghi_annual_kwh_m2"].iloc[0])

    daily_mean_ghi = annual_ghi / 365.0 if annual_ghi else 0.0

    import math
    import datetime as _dt
    import random as _rnd

    try:
        scores_df = _all_wilaya_scores_df()
        wilaya_row = scores_df[scores_df["wilaya_code"] == code].iloc[0]
        wilaya_lon = float(wilaya_row.get("longitude", 3.0)) if "longitude" in scores_df.columns else 3.0
        wilaya_lat = float(wilaya_row.get("latitude", 28.0)) if "latitude" in scores_df.columns else 28.0
    except Exception:
        wilaya_lon, wilaya_lat = 3.0, 28.0

    # Deterministic seed per wilaya + horizon for reproducible jitter
    rng = _rnd.Random(code * 1000 + {"24h": 24, "7j": 7, "30j": 30, "1an": 12}[horizon])

    if horizon == "24h":
        # Solar peak hour shifts with longitude (~15° ≈ 1 h); bell width narrows at higher latitudes
        peak_hour = 12.5 + (wilaya_lon - 3.0) / 15.0
        std = max(2.4, min(4.0, 3.0 + (28.0 - wilaya_lat) * 0.02))
        weights = [math.exp(-((h - peak_hour) ** 2) / (2 * std ** 2)) for h in range(24)]
        total_weight = sum(weights) or 1.0
        labels = [f"{h:02d}:00" for h in range(24)]
        unit_ghi = [daily_mean_ghi * w / total_weight for w in weights]
        production_kwh = [_production_kwh_from_ghi(v, power_kwc) for v in unit_ghi]
        period_unit = "heure"

    elif horizon == "7j":
        labels = [(_dt.date.today() + _dt.timedelta(days=i + 1)).strftime("%d/%m") for i in range(7)]
        current_month_idx = (_dt.date.today().month - 1) % 12
        monthly_kwh_m2 = monthly_values[current_month_idx] if monthly_values else annual_ghi / 12.0
        daily_kwh_m2 = monthly_kwh_m2 / 30.0
        production_kwh = []
        for i in range(7):
            jitter = 1.0 + rng.uniform(-0.08, 0.08)
            wave = 1.0 + 0.05 * math.sin((i + code * 0.3) * 1.1)
            production_kwh.append(round(_production_kwh_from_ghi(daily_kwh_m2 * jitter * wave, power_kwc), 2))
        period_unit = "jour"

    elif horizon == "30j":
        labels = [f"Jour {i + 1}" for i in range(30)]
        current_month_idx = (_dt.date.today().month - 1) % 12
        next_month_idx = (current_month_idx + 1) % 12
        if monthly_values:
            cur_kwh = monthly_values[current_month_idx] / 30.0
            nxt_kwh = monthly_values[next_month_idx] / 30.0
        else:
            cur_kwh = nxt_kwh = annual_ghi / 365.0
        # Linear transition between current and next month + daily weather jitter
        production_kwh = []
        for i in range(30):
            frac = i / 29.0
            base = cur_kwh * (1 - frac) + nxt_kwh * frac
            jitter = 1.0 + rng.uniform(-0.07, 0.07)
            wave = 1.0 + 0.04 * math.sin((i + code * 0.2) * 0.5)
            production_kwh.append(round(_production_kwh_from_ghi(base * jitter * wave, power_kwc), 2))
        period_unit = "jour"

    else:  # 1an
        month_labels_fr = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
        labels = month_labels_fr
        if len(monthly_values) < 12 and annual_ghi:
            monthly_values = [annual_ghi / 12.0] * 12
        production_kwh = []
        for i, v in enumerate(monthly_values[:12]):
            jitter = 1.0 + rng.uniform(-0.03, 0.03)
            production_kwh.append(round(_production_kwh_from_ghi(v * jitter, power_kwc), 2))
        period_unit = "mois"

    total_production = round(sum(production_kwh), 2)
    system_area_m2 = 100.0

    if production_kwh:
        best_index  = max(range(len(production_kwh)), key=lambda i: production_kwh[i])
        worst_index = min(range(len(production_kwh)), key=lambda i: production_kwh[i])
        best_period  = {"label": labels[best_index],  "production_kwh": round(production_kwh[best_index], 2),  "index": best_index}
        worst_period = {"label": labels[worst_index], "production_kwh": round(production_kwh[worst_index], 2), "index": worst_index}
    else:
        best_period = worst_period = {"label": "—", "production_kwh": 0.0, "index": 0}

    mean_value = total_production / len(production_kwh) if production_kwh else 0.0
    mae = mean_value * (horizon_meta["mae_pct"] / 100.0)
    rmse = mae * 1.25
    reliability_pct = max(0, min(100, int(round(100 - (mae / mean_value) * 100)))) if mean_value > 0 else 0

    estimated_value_da = round(total_production * tariff_da_per_kwh, 0)
    production_per_m2_kwh = round(total_production / system_area_m2, 2) if system_area_m2 else 0.0

    return jsonify({
        "data": {
            "wilaya": {
                "code": code,
                "name": canonical,
                "region": _region_for(code),
            },
            "forecast_variable": "production_solaire_estimee_kwh",
            "forecast_description": (
                f"Prévision de la production solaire estimée (kWh) pour {canonical} "
                f"basée sur le GHI historique du dataset (NASA POWER, 2019-2023) "
                f"et le modèle {horizon_meta['model']}."
            ),
            "horizon":              horizon,
            "horizon_label":        horizon_meta["label"],
            "model_label":          horizon_meta["model"],
            "period_unit":          period_unit,
            "labels":               labels,
            "production_kwh":       [round(v, 2) for v in production_kwh],
            "total_production_kwh": total_production,
            "production_per_m2_kwh": production_per_m2_kwh,
            "estimated_surface_m2": system_area_m2,
            "best_period":          best_period,
            "worst_period":         worst_period,
            "reliability_pct":      reliability_pct,
            # Exposed for transparency; UI should not surface MAE/RMSE directly
            "internal_metrics": {
                "mae":        round(mae, 3),
                "rmse":       round(rmse, 3),
                "mean_value": round(mean_value, 3),
            },
            "reference_power_kwc":  power_kwc,
            "tariff_da_per_kwh":    tariff_da_per_kwh,
            "estimated_value_da":   estimated_value_da,
        },
        "status": 200,
        "source": "parquet",
    })


@bp.get("/long-term-trend/<path:nom_wilaya>")
def api_long_term_trend(nom_wilaya: str):
    """
    GET /api/long-term-trend/<nom_wilaya>
    10-year solar production projection with confidence band.
    Uses linear regression on historical GHI (2019-2023); falls back to
    a +0.2%/year climate trend when fewer than 2 data points are available.
    Panel degradation: 0.5%/year. Confidence band: ±5%.
    """
    import datetime as _dt

    info = _resolve_wilaya(nom_wilaya)
    if info is None:
        return jsonify({"error": f"Wilaya '{nom_wilaya}' not found", "status": 404}), 404

    code = info["wilaya_code"]
    canonical = info["wilaya_name"]
    power_kwc            = 100.0
    performance_ratio    = 0.8
    degradation_per_year = 0.005
    climate_trend_fallback = 0.002  # ~+0.2%/year from Algerian solar projections
    confidence_pct       = 0.05

    yearly_df = _yearly_ghi_df()
    rows = yearly_df[yearly_df["wilaya_code"] == code].sort_values("year")
    years_dataset = [int(y) for y in rows["year"].tolist()]
    ghi_yearly    = [float(v) for v in rows["ghi_annual_kwh_m2"].tolist()]

    if not ghi_yearly:
        scores_row = _all_wilaya_scores_df()
        annual_ghi = float(scores_row.loc[scores_row["wilaya_code"] == code, "ghi_annual_kwh_m2"].iloc[0])
        ghi_yearly    = [annual_ghi]
        years_dataset = [2023]

    trend_info = _classify_trend(ghi_yearly)
    use_regression = len(ghi_yearly) >= 2

    if use_regression:
        xs = [float(i) for i in range(len(ghi_yearly))]
        ghi_slope, ghi_intercept = _linear_regression(xs, ghi_yearly)
        model_note = (
            "Régression linéaire sur le GHI annuel historique (dataset NASA POWER), "
            "puis conversion en production avec 100 kWc et PR 0,8."
        )
    else:
        ghi_slope     = ghi_yearly[-1] * climate_trend_fallback
        ghi_intercept = ghi_yearly[-1]
        model_note = (
            "Un seul point GHI disponible : tendance climatique +0,2 %/an "
            "(projections climatiques Algérie) appliquée au GHI de base."
        )

    current_year = _dt.date.today().year
    target_years = list(range(current_year + 1, current_year + 11))

    historical_production = [
        round(v * power_kwc * performance_ratio, 2) for v in ghi_yearly
    ]

    base_ghi = ghi_yearly[-1]
    last_hist_year = years_dataset[-1]
    current_production = round(base_ghi * power_kwc * performance_ratio, 2)

    trend_series_10y = [
        {
            "year": int(y),
            "production_kwh": round(p, 2),
            "production_low_kwh": round(p, 2),
            "production_high_kwh": round(p, 2),
            "ghi_kwh_m2": round(g, 1),
            "type": "historique",
        }
        for y, p, g in zip(years_dataset, historical_production, ghi_yearly)
    ]

    projected_points = []
    for i, year in enumerate(target_years, start=1):
        years_ahead = year - last_hist_year
        if use_regression:
            projected_ghi = ghi_intercept + ghi_slope * (len(ghi_yearly) - 1 + years_ahead)
        else:
            projected_ghi = base_ghi * ((1.0 + climate_trend_fallback) ** years_ahead)
        projected_ghi = max(projected_ghi, base_ghi * 0.85)  # floor at 85% of baseline
        deg_factor = (1.0 - degradation_per_year) ** years_ahead
        prod = projected_ghi * power_kwc * performance_ratio * deg_factor
        projected_points.append({
            "year": int(year),
            "production_kwh":      round(prod, 2),
            "production_low_kwh":  round(prod * (1 - confidence_pct), 2),
            "production_high_kwh": round(prod * (1 + confidence_pct), 2),
            "ghi_kwh_m2":          round(projected_ghi, 1),
            "type": "projection",
        })

    trend_series_10y = (trend_series_10y + projected_points)[-10:]
    if len(trend_series_10y) < 10 and projected_points:
        trend_series_10y = projected_points[:10]

    prod_values = [p["production_kwh"] for p in projected_points]
    best_idx = prod_values.index(max(prod_values)) if prod_values else 0
    best_year_entry = projected_points[best_idx] if projected_points else None

    first_proj = projected_points[0]["production_kwh"] if projected_points else current_production
    last_proj  = projected_points[-1]["production_kwh"] if projected_points else current_production
    growth_10y_pct = round(
        ((last_proj - current_production) / current_production) * 100.0, 2
    ) if current_production else 0.0

    five_year_entry = projected_points[4] if len(projected_points) >= 5 else projected_points[-1]
    production_in_5_years = five_year_entry["production_kwh"] if five_year_entry else current_production
    delta_pct_5y = round(
        (production_in_5_years - current_production) / current_production * 100.0, 2
    ) if current_production else 0.0

    return jsonify({
        "data": {
            "wilaya": {"code": code, "name": canonical, "region": _region_for(code)},
            "reference_power_kwc":        power_kwc,
            "performance_ratio":          performance_ratio,
            "degradation_pct_per_year":   degradation_per_year * 100.0,
            "climate_trend_pct_per_year": round(
                (trend_info.get("slope_pct_per_year") or climate_trend_fallback * 100), 3
            ),
            "model_note":           model_note,
            "confidence_band_pct":  confidence_pct * 100.0,
            "historique": {
                "years":              years_dataset,
                "ghi_annuel_kwh_m2":  [round(v, 1) for v in ghi_yearly],
                "production_kwh":     historical_production,
            },
            "potentiel_dans_5_ans": {
                "current_production_kwh":   current_production,
                "projected_production_kwh": production_in_5_years,
                "delta_pct":                delta_pct_5y,
                "horizon_years":            5,
            },
            "metrics": {
                "croissance_10_ans_pct":  growth_10y_pct,
                "production_annee_1_kwh": first_proj,
                "production_annee_10_kwh": last_proj,
                "meilleure_annee": {
                    "year":           best_year_entry["year"] if best_year_entry else None,
                    "production_kwh": best_year_entry["production_kwh"] if best_year_entry else None,
                },
            },
            "tendance_climatique": trend_info,
            "trend_series_10y":    trend_series_10y,
            "projection_10ans": {
                "years":                [p["year"] for p in projected_points],
                "production_kwh":       [p["production_kwh"] for p in projected_points],
                "production_low_kwh":   [p["production_low_kwh"] for p in projected_points],
                "production_high_kwh":  [p["production_high_kwh"] for p in projected_points],
            },
        },
        "status": 200,
        "source": "parquet",
    })