"""
Central data service — single source of truth for wilaya/commune solar statistics.

Parquet is opened once via DuckDB in-memory view; all aggregations are @lru_cache'd.

Formulas (per spec):
  ghi_annuel_kwh_m2  = mean(GHI) × 8760 / 1000
  potentiel_mw       = ghi_annuel_kwh_m2 × area_km² × 0.20
  stabilite_clim     = 1 − std(GHI) / mean(GHI)
  score_composite    = 100 × (0.40·GHI + 0.20·DNI + 0.20·KT + 0.10·stab_temp + 0.10·WS10M)
                       where each term is min-max normalised across all 58 wilayas.

Unit note: GHI in this dataset is clipped to [0, 1.5] (hourly mean ≈ 0.72),
  yielding ~6.3 kWh/m²/yr. Expected for Algeria is 1800-2400. Formula is applied
  as-is per spec; downstream pages may apply a correction if NASA ingestion is fixed.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Parquet search order: PARQUET_PATH env var → backend/data/ → project root
_DEFAULT_NAMES = ["algeria_solar_communes_REAL.parquet"]
_BACKEND_DIR   = Path(__file__).resolve().parent.parent
_PROJECT_ROOT  = _BACKEND_DIR.parent


def _resolve_parquet_path() -> Path:
    env = os.environ.get("PARQUET_PATH")
    if env:
        p = Path(env)
        if p.exists():
            return p
    candidates = [
        _BACKEND_DIR / "data" / _DEFAULT_NAMES[0],
        _BACKEND_DIR / _DEFAULT_NAMES[0],
        _PROJECT_ROOT / _DEFAULT_NAMES[0],
        _PROJECT_ROOT / "backend" / "data" / _DEFAULT_NAMES[0],
    ]
    for p in candidates:
        if p.exists():
            return p
    # Return canonical path so FileNotFoundError is readable
    return _BACKEND_DIR / "data" / _DEFAULT_NAMES[0]


PARQUET_PATH: Path = _resolve_parquet_path()

DEFAULT_AREA_KM2 = 10.0  # fallback per commune — dataset has no surface column

REGIONS = {
    "Centre": [
        "Algiers", "Blida", "Boumerdès", "Tipaza", "Médéa",
        "Aïn Defla", "Chlef", "Tissemsilt",
    ],
    "Est": [
        "Sétif", "Batna", "Constantine", "Annaba", "Skikda", "Jijel",
        "Béjaïa", "Tizi Ouzou", "Bouira", "Bordj Bou Arréridj", "M'Sila",
        "Oum El Bouaghi", "Khenchela", "Souk Ahras", "El Tarf", "Guelma",
        "Mila", "Tébessa",
    ],
    "Ouest": [
        "Oran", "Tlemcen", "Sidi Bel Abbès", "Mascara", "Mostaganem",
        "Relizane", "Tiaret", "Saïda", "Aïn Témouchent", "Naâma",
    ],
    "Sud-Est": [
        "Biskra", "El Oued", "Ouargla", "Illizi", "Tamanrasset",
        "Touggourt", "El M'Ghair", "Djanet", "Ouled Djellal",
    ],
    "Sud-Ouest": [
        "Béchar", "Adrar", "Tindouf", "Naâma",
        "Béni Abbès", "Timimoun", "El Bayadh", "Laghouat",
        "Djelfa", "Ghardâïa", "El Meniaa",
    ],
    "Grand Sud": [
        "Tamanrasset", "Illizi", "Adrar", "Tindouf",
        "In Salah", "In Guezzam", "Bordj Badji Mokhtar", "Djanet",
    ],
}

# Some wilayas appear in multiple regions above.
# PRIMARY_REGION picks the first match for one-shot aggregations.
def _build_primary_region_map() -> dict:
    out: dict[str, str] = {}
    for region, names in REGIONS.items():
        for n in names:
            if n not in out:
                out[n] = region
    return out

PRIMARY_REGION = _build_primary_region_map()

CLIMATE_LABEL = {
    "Saharan":   "Grand Sud",
    "Arid":      "Sud",
    "Semi-Arid": "Hauts Plateaux",
    "Coastal":   "Nord Côtier",
    "Highland":  "Montagne",
}

# Score composite weights — must sum to 1.00
WEIGHTS = {
    "ghi":       0.40,
    "dni":       0.20,
    "kt":        0.20,
    "stab_temp": 0.10,
    "ws10m":     0.10,
}

WEATHER_COLS = [
    "GHI", "DNI", "DHI",
    "T2M", "T2M_MAX", "T2M_MIN",
    "WS10M", "RH2M",
    "CLEARNESS_KT", "PRECIP_MM",
]

# ─── DuckDB singleton (thread-safe, lazy) ────────────────────────────────────

_CON: Optional[duckdb.DuckDBPyConnection] = None
_CON_LOCK = threading.RLock()
_READY = False
_SCHEMA_OK = False
_MISSING_COLS: list[str] = []


def _con() -> duckdb.DuckDBPyConnection:
    """Return the process-wide DuckDB connection, initialising it on first call."""
    global _CON, _READY, _SCHEMA_OK, _MISSING_COLS
    with _CON_LOCK:
        if _CON is not None:
            return _CON

        if not PARQUET_PATH.exists():
            raise FileNotFoundError(
                f"Parquet dataset introuvable : {PARQUET_PATH}\n"
                f"Place le fichier algeria_solar_communes_REAL.parquet dans "
                f"{_BACKEND_DIR / 'data'} ou définis la variable d'environnement "
                f"PARQUET_PATH=/chemin/vers/le.parquet"
            )

        _CON = duckdb.connect(database=":memory:", read_only=False)
        safe = str(PARQUET_PATH).replace("'", "''")
        _CON.execute(f"CREATE OR REPLACE VIEW solar AS SELECT * FROM read_parquet('{safe}')")

        schema_df = _CON.execute("DESCRIBE SELECT * FROM solar").fetchdf()
        present = set(schema_df["column_name"].tolist())
        required = {"datetime", "wilaya_code", "wilaya_name", "commune_name",
                    "latitude", "longitude", "climate", *WEATHER_COLS}
        _MISSING_COLS = sorted(required - present)
        _SCHEMA_OK = not _MISSING_COLS
        _READY = True
        if _MISSING_COLS:
            logger.warning("data_service: columns missing from parquet → %s", _MISSING_COLS)
        logger.info("data_service: parquet loaded ✓  (%s)  schema_ok=%s", PARQUET_PATH, _SCHEMA_OK)
        return _CON


def _q(sql: str, params: Optional[list] = None) -> pd.DataFrame:
    """Execute SQL against the DuckDB view (thread-serialised)."""
    with _CON_LOCK:
        return _con().execute(sql, params or []).fetchdf()


# ─── Name normalisation (accent-insensitive, alias-aware) ────────────────────

_NAME_ALIASES = {
    "alger": "algiers",
    "tipasa": "tipaza",
}


def _normalize(name: str) -> str:
    if name is None:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "", s.lower())
    return _NAME_ALIASES.get(s, s)


@lru_cache(maxsize=1)
def _wilaya_name_index() -> dict[str, str]:
    """normalized → canonical wilaya_name, built once from the parquet."""
    df = _q("SELECT DISTINCT wilaya_name FROM solar ORDER BY wilaya_name")
    return {_normalize(n): n for n in df["wilaya_name"].tolist()}


@lru_cache(maxsize=64)
def _commune_name_index(wilaya_canonical: str) -> dict[str, str]:
    df = _q(
        "SELECT DISTINCT commune_name FROM solar WHERE wilaya_name = ? ORDER BY commune_name",
        [wilaya_canonical],
    )
    return {_normalize(n): n for n in df["commune_name"].tolist()}


def _resolve_wilaya(name_or_code) -> Optional[str]:
    """User-supplied wilaya name or code → canonical wilaya_name, or None."""
    if name_or_code is None:
        return None
    s = str(name_or_code).strip()
    if not s:
        return None
    if s.isdigit():
        df = _q("SELECT wilaya_name FROM solar WHERE wilaya_code = ? LIMIT 1", [int(s)])
        return None if df.empty else str(df.iloc[0]["wilaya_name"])
    return _wilaya_name_index().get(_normalize(s))


def _resolve_commune(wilaya_canonical: str, commune: str) -> Optional[str]:
    return _commune_name_index(wilaya_canonical).get(_normalize(commune))


# ─── Core aggregations (cached for process lifetime) ─────────────────────────

@lru_cache(maxsize=1)
def _wilaya_agg_df() -> pd.DataFrame:
    """
    One row per wilaya with all derived metrics and the composite score.
    Composite score uses national min-max normalisation across all 58 wilayas —
    recomputed here so it's always consistent regardless of call order.
    """
    sql = """
    SELECT
        wilaya_code,
        wilaya_name,
        ANY_VALUE(climate)                AS climate,
        COUNT(DISTINCT commune_name)      AS n_communes,
        AVG(latitude)                     AS latitude,
        AVG(longitude)                    AS longitude,
        AVG(GHI)                          AS ghi_mean_hourly,
        STDDEV(GHI)                       AS ghi_stddev,
        AVG(DNI)                          AS dni_mean,
        AVG(DHI)                          AS dhi_mean,
        AVG(T2M)                          AS t2m_mean,
        AVG(T2M_MAX)                      AS t2m_max_mean,
        AVG(T2M_MIN)                      AS t2m_min_mean,
        STDDEV(T2M)                       AS t2m_stddev,
        AVG(WS10M)                        AS ws10m_mean,
        AVG(RH2M)                         AS rh2m_mean,
        AVG(CLEARNESS_KT)                 AS kt_mean,
        AVG(PRECIP_MM)                    AS precip_mm_mean,
        AVG(CASE WHEN GHI > 0.05 THEN 1.0 ELSE 0.0 END) AS sunshine_frac
    FROM solar
    GROUP BY wilaya_code, wilaya_name
    ORDER BY wilaya_code
    """
    df = _q(sql)

    df["ghi_annuel_kwh_m2"]    = df["ghi_mean_hourly"] * 8760.0 / 1000.0
    df["ensoleillement_h_an"]  = df["sunshine_frac"] * 8760.0
    df["stabilite_climatique"] = (
        1.0 - df["ghi_stddev"] / df["ghi_mean_hourly"].replace(0, np.nan)
    ).fillna(0.0).clip(-1.0, 1.0)
    df["stab_temp"] = (
        1.0 - df["t2m_stddev"] / df["t2m_mean"].abs().replace(0, np.nan)
    ).fillna(0.0).clip(-1.0, 1.0)

    # area_km² estimated from commune count — dataset has no surface column
    df["area_km2"]    = df["n_communes"].astype(float) * DEFAULT_AREA_KM2
    df["potentiel_mw"] = (df["ghi_annuel_kwh_m2"] * df["area_km2"] * 0.20).round(2)

    def _norm(s: pd.Series) -> pd.Series:
        lo, hi = float(s.min()), float(s.max())
        rng = hi - lo
        return ((s - lo) / rng).clip(0.0, 1.0) if rng > 0 else s * 0.0 + 0.5

    df["score_composite"] = (
        WEIGHTS["ghi"]       * _norm(df["ghi_annuel_kwh_m2"]) +
        WEIGHTS["dni"]       * _norm(df["dni_mean"]) +
        WEIGHTS["kt"]        * _norm(df["kt_mean"]) +
        WEIGHTS["stab_temp"] * _norm(df["stab_temp"]) +
        WEIGHTS["ws10m"]     * _norm(df["ws10m_mean"])
    ) * 100.0
    df["score_composite"] = df["score_composite"].round(2)

    df = df.sort_values("score_composite", ascending=False).reset_index(drop=True)
    df["rang_national"] = df.index + 1
    return df


@lru_cache(maxsize=1)
def _monthly_ghi_df() -> pd.DataFrame:
    """One row per (wilaya, month) with mean hourly GHI for that calendar month."""
    return _q("""
    SELECT
        wilaya_name,
        EXTRACT(MONTH FROM datetime)::INTEGER AS month,
        AVG(GHI) AS ghi_mean_hourly
    FROM solar
    GROUP BY wilaya_name, EXTRACT(MONTH FROM datetime)
    ORDER BY wilaya_name, month
    """)


@lru_cache(maxsize=1)
def _monthly_multi_df() -> pd.DataFrame:
    """One row per (wilaya, month) — GHI, DNI, T2M, WS10M, KT, CLRSKY_GHI, demand_mw."""
    return _q("""
    SELECT
        wilaya_name,
        EXTRACT(MONTH FROM datetime)::INTEGER AS month,
        AVG(GHI)          AS ghi_mean,
        AVG(DNI)          AS dni_mean,
        AVG(T2M)          AS t2m_mean,
        AVG(WS10M)        AS ws10m_mean,
        AVG(CLEARNESS_KT) AS kt_mean,
        AVG(CLRSKY_GHI)   AS clrsky_mean,
        AVG(demand_mw)    AS demand_mean
    FROM solar
    GROUP BY wilaya_name, EXTRACT(MONTH FROM datetime)
    ORDER BY wilaya_name, month
    """)


@lru_cache(maxsize=1)
def _wilaya_advanced_df() -> pd.DataFrame:
    """
    Full advanced wilaya aggregates: cloudy/sunny days per year, GHI instability,
    performance ratio, T2M amplitude, demand load factor.
    Entirely derived from the parquet — no hard-coded values.
    """
    df_cloud = _q("""
    WITH daily AS (
        SELECT wilaya_name,
               CAST(datetime AS DATE) AS day,
               AVG(CLEARNESS_KT)      AS kt_day
        FROM solar
        GROUP BY wilaya_name, CAST(datetime AS DATE)
    )
    SELECT
        wilaya_name,
        SUM(CASE WHEN kt_day < 0.40  THEN 1.0 ELSE 0.0 END) AS cloudy_days_total,
        SUM(CASE WHEN kt_day >= 0.65 THEN 1.0 ELSE 0.0 END) AS sunny_days_total,
        COUNT(DISTINCT day)                                   AS days_total
    FROM daily
    GROUP BY wilaya_name
    """)
    df_cloud["years"]            = df_cloud["days_total"] / 365.25
    df_cloud["cloudy_days_year"] = (df_cloud["cloudy_days_total"] / df_cloud["years"]).round(1)
    df_cloud["sunny_days_year"]  = (df_cloud["sunny_days_total"]  / df_cloud["years"]).round(1)

    df_other = _q("""
    SELECT
        wilaya_name,
        AVG(GHI)               AS ghi_mean,
        STDDEV(GHI)            AS ghi_std,
        AVG(PRECIP_MM)         AS precip_mean,
        AVG(CLRSKY_GHI)        AS clrsky_mean,
        AVG(T2M_MAX)           AS t2m_max_mean,
        AVG(T2M_MIN)           AS t2m_min_mean,
        AVG(RH2M)              AS rh2m_mean,
        AVG(demand_mw)         AS demand_avg,
        MAX(demand_mw)         AS demand_peak,
        MODE() WITHIN GROUP (ORDER BY climate) AS dominant_climate
    FROM solar
    GROUP BY wilaya_name
    """)
    df_other["ghi_instability_pct"]     = (df_other["ghi_std"] / df_other["ghi_mean"] * 100.0).round(2)
    df_other["precip_annual_mm"]        = (df_other["precip_mean"] * 8760.0).round(2)
    df_other["performance_ratio"]       = (df_other["ghi_mean"] / df_other["clrsky_mean"].replace(0, np.nan)).round(4)
    df_other["coverage_efficiency_pct"] = (df_other["performance_ratio"] * 100.0).round(2)
    df_other["t2m_amplitude_c"]         = (df_other["t2m_max_mean"] - df_other["t2m_min_mean"]).round(2)
    df_other["load_factor"]             = (df_other["demand_avg"] / df_other["demand_peak"].replace(0, np.nan)).round(4)

    return df_cloud.merge(df_other, on="wilaya_name", how="outer")


@lru_cache(maxsize=512)
def _commune_agg(wilaya_canonical: str, commune_canonical: str) -> Optional[pd.Series]:
    """Aggregate all hourly rows for a single commune into one Series."""
    df = _q("""
    SELECT
        ANY_VALUE(wilaya_code)  AS wilaya_code,
        ANY_VALUE(wilaya_name)  AS wilaya_name,
        commune_name,
        ANY_VALUE(climate)      AS climate,
        AVG(latitude)           AS latitude,
        AVG(longitude)          AS longitude,
        AVG(GHI)                AS ghi_mean_hourly,
        STDDEV(GHI)             AS ghi_stddev,
        AVG(DNI)                AS dni_mean,
        AVG(DHI)                AS dhi_mean,
        AVG(T2M)                AS t2m_mean,
        AVG(T2M_MAX)            AS t2m_max_mean,
        AVG(T2M_MIN)            AS t2m_min_mean,
        AVG(WS10M)              AS ws10m_mean,
        AVG(RH2M)               AS rh2m_mean,
        AVG(CLEARNESS_KT)       AS kt_mean,
        AVG(PRECIP_MM)          AS precip_mm_mean,
        AVG(CASE WHEN GHI > 0.05 THEN 1.0 ELSE 0.0 END) AS sunshine_frac
    FROM solar
    WHERE wilaya_name = ? AND commune_name = ?
    GROUP BY commune_name
    """, [wilaya_canonical, commune_canonical])
    return None if df.empty else df.iloc[0]


# ─── NaN-safe cast helpers ────────────────────────────────────────────────────

def _f(value, ndigits: int = 2, default: Optional[float] = None) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(x):
        return default
    return round(x, ndigits) if ndigits is not None else x


def _i(value, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ─── Public API ───────────────────────────────────────────────────────────────

def get_wilaya_stats(wilaya_name: str) -> Optional[dict]:
    """Full statistics block for one wilaya. Returns None if unknown."""
    canonical = _resolve_wilaya(wilaya_name)
    if canonical is None:
        return None
    df = _wilaya_agg_df()
    row = df[df["wilaya_name"] == canonical]
    if row.empty:
        return None
    r = row.iloc[0]
    canonical_name = str(r["wilaya_name"])
    return {
        "wilaya_code":         _i(r["wilaya_code"]),
        "wilaya_name":         canonical_name,
        "climate":             str(r["climate"]),
        "climate_label":       CLIMATE_LABEL.get(str(r["climate"]), ""),
        "region":              PRIMARY_REGION.get(canonical_name, ""),
        "latitude":            _f(r["latitude"], 4),
        "longitude":           _f(r["longitude"], 4),
        "n_communes":          _i(r["n_communes"]),
        "area_km2":            _f(r["area_km2"], 1),
        "ghi_annuel_kwh_m2":   _f(r["ghi_annuel_kwh_m2"], 2),
        "dni_moyen":           _f(r["dni_mean"], 4),
        "dhi_moyen":           _f(r["dhi_mean"], 4),
        "clearness_kt_moyen":  _f(r["kt_mean"], 4),
        "ensoleillement_h_an": _f(r["ensoleillement_h_an"], 0),
        "t2m_moyen":           _f(r["t2m_mean"], 2),
        "t2m_max":             _f(r["t2m_max_mean"], 2),
        "t2m_min":             _f(r["t2m_min_mean"], 2),
        "rh2m_moyen":          _f(r["rh2m_mean"], 2),
        "vent_moyen_m_s":      _f(r["ws10m_mean"], 2),
        "precip_mm_moyen":     _f(r["precip_mm_mean"], 3),
        "stabilite_climatique": _f(r["stabilite_climatique"], 4),
        "score_composite":      _f(r["score_composite"], 2),
        "rang_national":        _i(r["rang_national"]),
        "potentiel_mw":         _f(r["potentiel_mw"], 1),
        # Formula audit trail — lets callers verify the derivation
        "formules_used": {
            "ghi_annuel":   "mean(GHI) * 8760 / 1000",
            "potentiel_mw": "ghi_annuel × area_km² × 1000 × 0.20 / 1000",
            "stabilite":    "1 - std(GHI)/mean(GHI)",
            "score":        "100 * ( 0.40·GHI + 0.20·DNI + 0.20·KT + 0.10·stab_temp + 0.10·WS10M ) [min-max normalised]",
            "area_default_km2_per_commune": DEFAULT_AREA_KM2,
        },
    }


def get_commune_stats(wilaya_name: str, commune_name: str) -> Optional[dict]:
    """
    Same shape as get_wilaya_stats for a single commune.
    score_composite and rang_national are inherited from the parent wilaya —
    the composite is defined at national level, not recomputed per commune.
    Returns None if the (wilaya, commune) pair is unknown.
    """
    canon_w = _resolve_wilaya(wilaya_name)
    if canon_w is None:
        return None
    canon_c = _resolve_commune(canon_w, commune_name)
    if canon_c is None:
        return None
    row = _commune_agg(canon_w, canon_c)
    if row is None:
        return None

    ghi_annual  = float(row["ghi_mean_hourly"]) * 8760.0 / 1000.0
    sunshine_h  = float(row["sunshine_frac"]) * 8760.0
    ghi_std     = float(row["ghi_stddev"] or 0.0)
    ghi_mean    = float(row["ghi_mean_hourly"] or 0.0)
    stab_clim   = max(-1.0, min(1.0, 1.0 - (ghi_std / ghi_mean) if ghi_mean else 0.0))
    potentiel_mw = ghi_annual * DEFAULT_AREA_KM2 * 0.20
    parent = get_wilaya_stats(canon_w) or {}

    return {
        "wilaya_code":         _i(row["wilaya_code"]),
        "wilaya_name":         str(row["wilaya_name"]),
        "commune_name":        str(row["commune_name"]),
        "climate":             str(row["climate"]),
        "latitude":            _f(row["latitude"], 4),
        "longitude":           _f(row["longitude"], 4),
        "area_km2":            _f(DEFAULT_AREA_KM2, 1),
        "ghi_annuel_kwh_m2":   _f(ghi_annual, 2),
        "dni_moyen":           _f(row["dni_mean"], 4),
        "dhi_moyen":           _f(row["dhi_mean"], 4),
        "clearness_kt_moyen":  _f(row["kt_mean"], 4),
        "ensoleillement_h_an": _f(sunshine_h, 0),
        "t2m_moyen":           _f(row["t2m_mean"], 2),
        "t2m_max":             _f(row["t2m_max_mean"], 2),
        "t2m_min":             _f(row["t2m_min_mean"], 2),
        "rh2m_moyen":          _f(row["rh2m_mean"], 2),
        "vent_moyen_m_s":      _f(row["ws10m_mean"], 2),
        "precip_mm_moyen":     _f(row["precip_mm_mean"], 3),
        "stabilite_climatique": _f(stab_clim, 4),
        "score_composite":      parent.get("score_composite"),
        "rang_national":        parent.get("rang_national"),
        "potentiel_mw":         _f(potentiel_mw, 1),
        "formules_used": {
            "ghi_annuel":   "mean(GHI) * 8760 / 1000",
            "potentiel_mw": f"ghi_annuel × {DEFAULT_AREA_KM2} × 1000 × 0.20 / 1000",
            "stabilite":    "1 - std(GHI)/mean(GHI)",
            "note":         "score_composite inherited from parent wilaya",
        },
    }


def get_national_stats() -> dict:
    """Country-wide aggregates: TWh potential, dataset temporal range, mean GHI."""
    df = _wilaya_agg_df()

    # Annual energy estimate: potentiel_mw (MW) × ghi_annuel (kWh/m²/yr) → MWh → TWh
    twh_total = float((df["potentiel_mw"] * df["ghi_annuel_kwh_m2"]).sum()) / 1_000_000.0

    span = _q("""
        SELECT MIN(datetime) AS dt_min, MAX(datetime) AS dt_max,
               (DATE_DIFF('year', MIN(datetime), MAX(datetime)) + 1)::INTEGER AS years_calendar
        FROM solar
    """).iloc[0]

    return {
        "n_wilayas":                  _i(df["wilaya_name"].nunique()),
        "n_communes":                 _i(df["n_communes"].sum()),
        "annees_de_donnees":          _i(span["years_calendar"]),
        "date_debut":                 str(pd.Timestamp(span["dt_min"]).date()),
        "date_fin":                   str(pd.Timestamp(span["dt_max"]).date()),
        "ghi_moyen_national_kwh_m2":  _f(df["ghi_annuel_kwh_m2"].mean(), 2),
        "potentiel_mw_total":         _f(df["potentiel_mw"].sum(), 0),
        "twh_potentiel_total":        _f(twh_total, 2),
        "source": "algeria_solar_communes_REAL.parquet (NASA POWER)",
    }


def get_ranking(metric: str = "score_composite",
                limit: int = 58,
                region: Optional[str] = None,
                climate: Optional[str] = None,
                search: Optional[str] = None) -> list[dict]:
    """
    National ranking with optional region/climate/search filters.
    delta_vs_national is signed % deviation from national mean GHI.
    """
    df = _wilaya_agg_df().copy()
    alias = {
        "ghi": "ghi_annuel_kwh_m2", "ghi_annuel": "ghi_annuel_kwh_m2",
        "ghi_annuel_kwh_m2": "ghi_annuel_kwh_m2",
        "potentiel": "potentiel_mw", "potentiel_mw": "potentiel_mw",
        "score": "score_composite",  "score_composite": "score_composite",
    }
    col = alias.get((metric or "score_composite").strip().lower(), "score_composite")
    national_mean_ghi = float(df["ghi_annuel_kwh_m2"].mean()) if not df.empty else 0.0

    if region:
        region_canon = next((k for k in REGIONS if _normalize(k) == _normalize(region)), None)
        if region_canon:
            members = {_normalize(n) for n in REGIONS[region_canon]}
            df = df[df["wilaya_name"].apply(lambda n: _normalize(n) in members)]
    if climate:
        df = df[df["climate"].str.lower() == climate.lower()]
    if search:
        s = _normalize(search)
        if s:
            df = df[df["wilaya_name"].apply(lambda n: s in _normalize(n))]

    df = df.sort_values(col, ascending=False).reset_index(drop=True)
    if limit:
        df = df.head(int(limit))

    out = []
    for i, r in df.iterrows():
        ghi_val = float(r["ghi_annuel_kwh_m2"])
        delta = (ghi_val - national_mean_ghi) / national_mean_ghi * 100.0 if national_mean_ghi else 0.0
        canonical_name = str(r["wilaya_name"])
        out.append({
            "rank":              int(r["rang_national"]),
            "position":          i + 1,
            "wilaya_code":       _i(r["wilaya_code"]),
            "wilaya_name":       canonical_name,
            "climate":           str(r["climate"]),
            "climate_label":     CLIMATE_LABEL.get(str(r["climate"]), ""),
            "region":            PRIMARY_REGION.get(canonical_name, ""),
            "latitude":          _f(r["latitude"], 4),
            "longitude":         _f(r["longitude"], 4),
            "n_communes":        _i(r["n_communes"]),
            "ghi_annuel_kwh_m2": _f(ghi_val, 2),
            "potentiel_mw":      _f(r["potentiel_mw"], 1),
            "score_composite":   _f(r["score_composite"], 2),
            "delta_vs_national": _f(delta, 2),
        })
    return out


def get_regions_breakdown() -> list[dict]:
    """Per-region aggregates using PRIMARY_REGION (each wilaya counted once)."""
    df = _wilaya_agg_df().copy()
    df["_region"] = df["wilaya_name"].map(PRIMARY_REGION).fillna("")
    grouped = (
        df[df["_region"] != ""].groupby("_region").agg(
            n_wilayas=("wilaya_code", "count"),
            n_communes=("n_communes", "sum"),
            ghi_mean=("ghi_annuel_kwh_m2", "mean"),
            ghi_max=("ghi_annuel_kwh_m2", "max"),
            ghi_min=("ghi_annuel_kwh_m2", "min"),
            potentiel_mw_total=("potentiel_mw", "sum"),
            score_mean=("score_composite", "mean"),
        )
        .reset_index()
        .rename(columns={"_region": "region"})
        .sort_values("ghi_mean", ascending=False)
    )
    return [
        {
            "region":             str(r["region"]),
            "n_wilayas":          _i(r["n_wilayas"]),
            "n_communes":         _i(r["n_communes"]),
            "ghi_moyen_kwh_m2":   _f(r["ghi_mean"], 2),
            "ghi_max_kwh_m2":     _f(r["ghi_max"], 2),
            "ghi_min_kwh_m2":     _f(r["ghi_min"], 2),
            "potentiel_mw_total": _f(r["potentiel_mw_total"], 0),
            "score_moyen":        _f(r["score_mean"], 2),
        }
        for _, r in grouped.iterrows()
    ]


def get_top_wilayas(metric: str = "score_composite", n: int = 10) -> list[dict]:
    """Top-n wilayas by metric. Accepts aliases: ghi, potentiel, score."""
    df = _wilaya_agg_df().copy()
    alias = {
        "ghi": "ghi_annuel_kwh_m2", "ghi_annuel": "ghi_annuel_kwh_m2",
        "ghi_annuel_kwh_m2": "ghi_annuel_kwh_m2",
        "potentiel": "potentiel_mw", "potentiel_mw": "potentiel_mw",
        "score": "score_composite",  "score_composite": "score_composite",
    }
    col = alias.get((metric or "score_composite").strip().lower(), "score_composite")
    n = max(1, min(int(n or 10), len(df)))
    df_top = df.sort_values(col, ascending=False).head(n).reset_index(drop=True)
    return [
        {
            "rank":              i + 1,
            "wilaya_code":       _i(r["wilaya_code"]),
            "wilaya_name":       str(r["wilaya_name"]),
            "climate":           str(r["climate"]),
            "latitude":          _f(r["latitude"], 4),
            "longitude":         _f(r["longitude"], 4),
            "ghi_annuel_kwh_m2": _f(r["ghi_annuel_kwh_m2"], 2),
            "potentiel_mw":      _f(r["potentiel_mw"], 1),
            "score_composite":   _f(r["score_composite"], 2),
            "metric":            col,
            "metric_value":      _f(r[col], 4),
        }
        for i, r in df_top.iterrows()
    ]


def get_monthly_ghi(wilaya_name: str) -> Optional[dict]:
    """12 monthly GHI values (Jan→Dec) in kWh/m²/month. Returns None if unknown."""
    canonical = _resolve_wilaya(wilaya_name)
    if canonical is None:
        return None

    df = _monthly_ghi_df()
    rows = df[df["wilaya_name"] == canonical].set_index("month")
    HRS_PER_MONTH = 730.5  # 8760 / 12
    values = [
        round(float(rows.loc[m, "ghi_mean_hourly"]) * HRS_PER_MONTH, 2) if m in rows.index else 0.0
        for m in range(1, 13)
    ]
    return {
        "wilaya_name": canonical,
        "labels":  ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Aoû","Sep","Oct","Nov","Déc"],
        "values":  values,
        "unit":    "kWh/m²/mois",
        "formula": "mean(GHI per month) × 730.5  (8760/12)",
    }


def list_wilayas() -> list[dict]:
    """Lightweight list for UI selectors (code, name, climate)."""
    df = _wilaya_agg_df()
    return [
        {
            "code":    _i(r["wilaya_code"]),
            "id":      _i(r["wilaya_code"]),
            "name":    str(r["wilaya_name"]),
            "nom":     str(r["wilaya_name"]),
            "climate": str(r["climate"]),
        }
        for _, r in df.sort_values("wilaya_code").iterrows()
    ]


def list_communes(wilaya_name: str) -> Optional[list[str]]:
    canonical = _resolve_wilaya(wilaya_name)
    if canonical is None:
        return None
    return _q(
        "SELECT DISTINCT commune_name FROM solar WHERE wilaya_name = ? ORDER BY commune_name",
        [canonical],
    )["commune_name"].tolist()


@lru_cache(maxsize=1)
def _climate_zones_df() -> pd.DataFrame:
    return _q("""
    SELECT
        climate,
        COUNT(DISTINCT wilaya_name)      AS n_wilayas,
        COUNT(DISTINCT commune_name)     AS n_communes,
        AVG(GHI)                         AS ghi_mean_hourly,
        AVG(GHI) * 8760 / 1000.0        AS ghi_annuel_kwh_m2,
        AVG(DNI)                         AS dni_mean,
        AVG(CLEARNESS_KT)                AS kt_mean,
        AVG(latitude)                    AS lat,
        AVG(longitude)                   AS lon
    FROM solar
    WHERE climate IS NOT NULL
    GROUP BY climate
    ORDER BY ghi_annuel_kwh_m2 DESC
    """)


def get_climate_zones() -> list[dict]:
    """
    One entry per climate zone with mean GHI and the highest-GHI wilaya
    as a representative for navigation.
    """
    df = _climate_zones_df().copy()
    if df.empty:
        return []

    # Pick the highest-GHI wilaya per climate as the representative
    repr_map = (
        _q("""
        SELECT climate, wilaya_name, AVG(GHI) AS gm
        FROM solar WHERE climate IS NOT NULL
        GROUP BY climate, wilaya_name
        ORDER BY climate, gm DESC
        """)
        .sort_values("gm", ascending=False)
        .drop_duplicates("climate")
        .set_index("climate")["wilaya_name"]
        .to_dict()
    )

    return [
        {
            "climate":               str(r["climate"]),
            "label":                 str(r["climate"]),
            "ghi_annuel_kwh_m2":     _f(r["ghi_annuel_kwh_m2"], 4),
            "ghi_mean_hourly":       _f(r["ghi_mean_hourly"], 6),
            "dni_moyen":             _f(r["dni_mean"], 4),
            "clearness_kt_moyen":    _f(r["kt_mean"], 4),
            "n_wilayas":             _i(r["n_wilayas"]),
            "n_communes":            _i(r["n_communes"]),
            "latitude":              _f(r["lat"], 4),
            "longitude":             _f(r["lon"], 4),
            "representative_wilaya": repr_map.get(str(r["climate"])),
        }
        for _, r in df.iterrows()
    ]


def get_wilaya_monthly(wilaya_name: str) -> Optional[dict]:
    """Monthly profiles (GHI, DNI, T2M, WS10M, KT, PR, demand) for the wilaya dashboard."""
    canon = _resolve_wilaya(wilaya_name)
    if canon is None:
        return None
    df = _monthly_multi_df()
    rows = df[df["wilaya_name"] == canon].set_index("month")
    if rows.empty:
        return None

    HRS_PER_MONTH = 730.5  # 8760 / 12
    months = list(range(1, 13))

    def _g(m, col):
        return float(rows.loc[m, col]) if m in rows.index and col in rows.columns else 0.0

    def _pr(m):
        g = _g(m, "ghi_mean"); c = _g(m, "clrsky_mean")
        return round(g / c, 4) if c > 0 else 0.0

    def _mean(arr):
        vals = [x for x in arr if x is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    ghi_series    = [round(_g(m, "ghi_mean") * HRS_PER_MONTH, 2) for m in months]
    dni_series    = [round(_g(m, "dni_mean") * 1000.0, 2)        for m in months]
    t2m_series    = [round(_g(m, "t2m_mean"),   2)               for m in months]
    ws10m_series  = [round(_g(m, "ws10m_mean"), 3)               for m in months]
    kt_series     = [round(_g(m, "kt_mean"),    3)               for m in months]
    pr_series     = [_pr(m)                                      for m in months]
    demand_series = [round(_g(m, "demand_mean"), 2)              for m in months]

    return {
        "wilaya_name": canon,
        "labels":   ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Aoû","Sep","Oct","Nov","Déc"],
        "ghi":      ghi_series,
        "dni":      dni_series,
        "t2m":      t2m_series,
        "ws10m":    ws10m_series,
        "kt":       kt_series,
        "pr":       pr_series,
        "demand_mw": demand_series,
        "annual_avg": {
            "ghi":       _mean(ghi_series),
            "dni":       _mean(dni_series),
            "t2m":       _mean(t2m_series),
            "ws10m":     _mean(ws10m_series),
            "kt":        _mean(kt_series),
            "pr":        round(_mean(pr_series), 4),
            "demand_mw": _mean(demand_series),
        },
        "units": {
            "ghi": "kWh/m²/mois", "dni": "W/m²", "t2m": "°C",
            "ws10m": "m/s", "kt": "sans unité", "pr": "ratio (0-1)", "demand_mw": "MW",
        },
        "formulas": {
            "ghi":       "mean(GHI per month) × 730.5",
            "dni":       "mean(DNI per month) × 1000",
            "pr":        "mean(GHI) / mean(CLRSKY_GHI)",
            "demand_mw": "mean(demand_mw per month)",
        },
    }


def get_wilaya_extras(wilaya_name: str) -> Optional[dict]:
    """Full infrastructure + climate indicators from _wilaya_advanced_df."""
    canon = _resolve_wilaya(wilaya_name)
    if canon is None:
        return None
    df = _wilaya_advanced_df()
    r = df[df["wilaya_name"] == canon]
    if r.empty:
        return None
    r = r.iloc[0]
    return {
        "wilaya_name":             canon,
        "cloudy_days_year":        _f(r["cloudy_days_year"], 1),
        "sunny_days_year":         _f(r.get("sunny_days_year"), 1),
        "ghi_instability_pct":     _f(r["ghi_instability_pct"], 2),
        "precip_annual_mm":        _f(r["precip_annual_mm"], 2),
        "dominant_climate":        str(r["dominant_climate"]),
        "performance_ratio":       _f(r.get("performance_ratio"), 4),
        "coverage_efficiency_pct": _f(r.get("coverage_efficiency_pct"), 2),
        "t2m_amplitude_c":         _f(r.get("t2m_amplitude_c"), 2),
        "rh2m_mean":               _f(r.get("rh2m_mean"), 2),
        "demand_avg_mw":           _f(r.get("demand_avg"), 2),
        "demand_peak_mw":          _f(r.get("demand_peak"), 2),
        "load_factor":             _f(r.get("load_factor"), 4),
        "clrsky_ghi_mean":         _f(r.get("clrsky_mean"), 4),
        "formulas": {
            "performance_ratio":       "mean(GHI) / mean(CLRSKY_GHI)",
            "coverage_efficiency_pct": "performance_ratio × 100",
            "t2m_amplitude_c":         "mean(T2M_MAX) - mean(T2M_MIN)",
            "load_factor":             "AVG(demand_mw) / MAX(demand_mw)",
            "cloudy_days_year":        "count(day where mean(CLEARNESS_KT) < 0.4) per year",
            "sunny_days_year":         "count(day where mean(CLEARNESS_KT) >= 0.65) per year",
            "ghi_instability_pct":     "std(GHI) / mean(GHI) × 100",
            "precip_annual_mm":        "mean(PRECIP_MM) × 8760",
        },
    }


def get_wilaya_radar(wilaya_name: str) -> Optional[dict]:
    """
    5-axis radar normalised 0-100 on national min/max.
    Axes: GHI, DNI, CLEARNESS_KT, Stabilité T2M, WS10M.
    """
    canon = _resolve_wilaya(wilaya_name)
    if canon is None:
        return None
    df = _wilaya_agg_df().copy()
    row = df[df["wilaya_name"] == canon]
    if row.empty:
        return None
    r = row.iloc[0]

    def _norm(value, series):
        lo, hi = float(series.min()), float(series.max())
        rng = hi - lo
        return max(0.0, min(100.0, (float(value) - lo) / rng * 100.0)) if rng > 0 else 50.0

    axes = {
        "GHI":           _norm(r["ghi_annuel_kwh_m2"], df["ghi_annuel_kwh_m2"]),
        "DNI":           _norm(r["dni_mean"],           df["dni_mean"]),
        "CLEARNESS_KT":  _norm(r["kt_mean"],            df["kt_mean"]),
        "Stabilité T2M": _norm(r["stab_temp"],          df["stab_temp"]),
        "WS10M":         _norm(r["ws10m_mean"],         df["ws10m_mean"]),
    }
    return {
        "wilaya_name": canon,
        "labels": list(axes.keys()),
        "values": [round(v, 2) for v in axes.values()],
        "unit":   "normalisé 0-100",
    }


def get_wilaya_of_the_week() -> Optional[dict]:
    """
    Wilaya with the highest mean GHI over the last 7 days of the dataset.
    Dataset ends at 2023-12-31, so the result is deterministic.
    """
    max_row = _q("SELECT MAX(datetime) AS max_dt FROM solar")
    if max_row.empty or max_row.iloc[0]["max_dt"] is None:
        return None
    max_dt = pd.Timestamp(max_row.iloc[0]["max_dt"])
    lo = max_dt - pd.Timedelta(days=7)

    df = _q("""
    SELECT wilaya_name,
           AVG(GHI)                    AS ghi_mean_hourly,
           AVG(GHI) * 8760 / 1000.0   AS ghi_annuel_kwh_m2,
           AVG(DNI)                    AS dni_mean,
           AVG(T2M)                    AS t2m_mean
    FROM solar WHERE datetime > ? AND datetime <= ?
    GROUP BY wilaya_name ORDER BY ghi_mean_hourly DESC LIMIT 1
    """, [lo.to_pydatetime(), max_dt.to_pydatetime()])
    if df.empty:
        return None
    r = df.iloc[0]

    agg = _wilaya_agg_df()
    s = agg[agg["wilaya_name"] == r["wilaya_name"]]
    return {
        "wilaya_name":       str(r["wilaya_name"]),
        "wilaya_code":       int(s.iloc[0]["wilaya_code"]) if not s.empty else None,
        "climate":           str(s.iloc[0]["climate"])     if not s.empty else None,
        "ghi_week_kwh_m2_h": _f(r["ghi_mean_hourly"], 4),
        "ghi_annuel_kwh_m2": _f(r["ghi_annuel_kwh_m2"], 2),
        "dni_moyen":         _f(r["dni_mean"], 4),
        "t2m_moyen":         _f(r["t2m_mean"], 2),
        "score_composite":   _f(float(s.iloc[0]["score_composite"]), 2) if not s.empty else None,
        "rang_national":     int(s.iloc[0]["rang_national"]) if not s.empty else None,
        "window_start":      lo.date().isoformat(),
        "window_end":        max_dt.date().isoformat(),
    }


def is_ready() -> dict:
    """Health-check for /api/data-service/health."""
    try:
        _con()
    except Exception as exc:
        return {"ready": False, "error": str(exc), "parquet_path": str(PARQUET_PATH)}
    return {
        "ready":            _READY,
        "schema_ok":        _SCHEMA_OK,
        "missing_cols":     _MISSING_COLS,
        "parquet_path":     str(PARQUET_PATH),
        "parquet_exists":   PARQUET_PATH.exists(),
        "weights":          WEIGHTS,
        "default_area_km2": DEFAULT_AREA_KM2,
    }


CLIMATE_DESCRIPTION = {
    "Saharan":   "Zone désertique avec ensoleillement maximal toute l'année, idéale pour installations industrielles à grande échelle.",
    "Arid":      "Zone aride avec fort potentiel solaire et faible humidité, excellente pour projets résidentiels et commerciaux.",
    "Semi-Arid": "Zone semi-aride offrant un bon compromis entre production solaire et conditions d'installation.",
    "Coastal":   "Zone côtière avec humidité plus élevée, privilégier les panneaux bifaciaux résistants à la corrosion saline.",
    "Highland":  "Zone montagneuse avec ensoleillement variable selon la saison, adapter le dimensionnement en conséquence.",
}

PANEL_RECOMMENDATION = {
    "Saharan":   "Panneaux monocristallins haute température recommandés (rendement stable jusqu'à 85°C)",
    "Coastal":   "Panneaux bifaciaux avec traitement anti-corrosion saline",
    "Arid":      "Panneaux monocristallins standard, prévoir nettoyage mensuel",
    "Semi-Arid": "Panneaux polycristallins ou monocristallins selon budget",
    "Highland":  "Panneaux avec bon rendement en diffus recommandés",
}


def _risk_label(cv: float) -> str:
    """Climatic risk from daily GHI coefficient of variation (std/mean)."""
    if cv is None:    return "Inconnu"
    if cv < 0.15:     return "Faible"
    if cv < 0.30:     return "Modéré"
    return "Élevé"


def _clarity_label(kt: float) -> str:
    if kt is None:  return "Inconnu"
    if kt > 0.6:    return "Excellent"
    if kt >= 0.4:   return "Bon"
    return "Faible"


def get_commune_analysis(wilaya_name: str, commune_name: str) -> Optional[dict]:
    """
    Full per-commune payload for the Zone Analysis page.
    Includes a LOCAL composite score (recomputed for this commune against national
    ranges), risk indicators, and climate-specific text and panel recommendation.
    Returns None if the (wilaya, commune) pair is unknown.
    """
    base = get_commune_stats(wilaya_name, commune_name)
    if base is None:
        return None

    canon_w = _resolve_wilaya(wilaya_name)
    canon_c = _resolve_commune(canon_w, commune_name) if canon_w else None
    row = _commune_agg(canon_w, canon_c) if canon_c else None
    if row is None:
        return None

    # Use daily-aggregate variability for risk — hourly CV is dominated by the
    # day/night cycle and gives CV ≈ 1 for every location.
    daily = _q("""
    SELECT AVG(daily_ghi) AS mean_d, STDDEV(daily_ghi) AS std_d
    FROM (
      SELECT DATE(datetime) AS d, SUM(GHI) AS daily_ghi
      FROM solar WHERE wilaya_name = ? AND commune_name = ?
      GROUP BY DATE(datetime)
    )
    """, [canon_w, canon_c])
    cv = None
    if not daily.empty:
        m_d = float(daily.iloc[0]["mean_d"] or 0.0)
        s_d = float(daily.iloc[0]["std_d"]  or 0.0)
        cv = (s_d / m_d) if m_d else None
    stability_pct = max(0.0, min(100.0, (1.0 - (cv or 0.0)) * 100.0))

    agg_df = _wilaya_agg_df()
    def _nrm(v, col):
        try:
            mn = float(agg_df[col].min()); mx = float(agg_df[col].max())
            return max(0.0, min(1.0, (float(v) - mn) / (mx - mn))) if mx != mn else 0.0
        except Exception:
            return 0.0

    stab_local = float(base["stabilite_climatique"] or 0.0)
    score_local = round(max(0.0, min(100.0, 100.0 * (
        WEIGHTS["ghi"]       * _nrm(float(base["ghi_annuel_kwh_m2"] or 0.0), "ghi_annuel_kwh_m2") +
        WEIGHTS["dni"]       * _nrm(float(base["dni_moyen"] or 0.0),         "dni_mean") +
        WEIGHTS["kt"]        * _nrm(float(base["clearness_kt_moyen"] or 0.0),"kt_mean") +
        WEIGHTS["stab_temp"] * max(0.0, min(1.0, (stab_local + 1.0) / 2.0)) +
        WEIGHTS["ws10m"]     * _nrm(float(base["vent_moyen_m_s"] or 0.0),    "ws10m_mean")
    ))), 2)

    climate = base.get("climate") or ""
    return {
        **base,
        "score_commune":         score_local,
        "score_composite_local": score_local,
        "risque_climatique":     _risk_label(cv),
        "risque_cv":             round(cv, 4) if cv is not None else None,
        "stabilite_pct":         round(stability_pct, 1),
        "indice_clarte_label":   _clarity_label(float(base["clearness_kt_moyen"] or 0.0)),
        "accessibilite":         "Données non disponibles",
        "why_this_zone":         CLIMATE_DESCRIPTION.get(climate, ""),
        "panel_recommendation":  PANEL_RECOMMENDATION.get(climate, ""),
    }


def get_commune_monthly_vs_national(wilaya_name: str, commune_name: str) -> Optional[dict]:
    """
    Monthly GHI of the commune vs national average, plus estimated production.
    Production assumes 10 000 m² at 20% efficiency.
    """
    canon_w = _resolve_wilaya(wilaya_name)
    if canon_w is None:
        return None
    canon_c = _resolve_commune(canon_w, commune_name)
    if canon_c is None:
        return None

    HRS_PER_MONTH = 730.5
    SURFACE_M2    = 10_000
    RENDEMENT     = 0.20

    by_m_c = {
        int(r["month"]): float(r["ghi_h"])
        for _, r in _q("""
            SELECT MONTH(datetime) AS month, AVG(GHI) AS ghi_h
            FROM solar WHERE wilaya_name = ? AND commune_name = ?
            GROUP BY MONTH(datetime) ORDER BY month
        """, [canon_w, canon_c]).iterrows()
    }
    by_m_n = {
        int(r["month"]): float(r["ghi_h"])
        for _, r in _q("""
            SELECT MONTH(datetime) AS month, AVG(GHI) AS ghi_h
            FROM solar GROUP BY MONTH(datetime) ORDER BY month
        """).iterrows()
    }

    months       = list(range(1, 13))
    ghi_commune  = [round(by_m_c.get(m, 0.0) * HRS_PER_MONTH, 2) for m in months]
    ghi_national = [round(by_m_n.get(m, 0.0) * HRS_PER_MONTH, 2) for m in months]
    production_mwh = [round(v * SURFACE_M2 * RENDEMENT / 1000.0, 2) for v in ghi_commune]

    return {
        "wilaya_name":  canon_w,
        "commune_name": canon_c,
        "labels":       ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Aoû","Sep","Oct","Nov","Déc"],
        "ghi_commune":  ghi_commune,
        "ghi_national": ghi_national,
        "production_mwh": production_mwh,
        "hypothesis": {
            "surface_m2": SURFACE_M2,
            "rendement":  RENDEMENT,
            "unit_ghi":   "kWh/m²/mois",
            "unit_prod":  "MWh/mois",
        },
    }


def _warmup() -> None:
    """Open the parquet and prime the aggregation cache on first import."""
    try:
        _con()
        _wilaya_agg_df()
    except Exception as exc:
        logger.warning("data_service warm-up skipped: %s", exc)


_warmup()