import json
import logging
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional
import threading

import duckdb
import numpy as np
import pandas as pd

from config import (
    PARQUET_PATH, CACHE_DIR, SCORE_WEIGHTS, GHI_THRESH,
    CLIMATE_REGIONS, FEAT_COLS, TARGET_COL, SEQ_LEN,
    ZONE_AVERAGE_AREA_KM2, CAPACITY_FACTOR
)

logger = logging.getLogger(__name__)


def _norm01(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    return (series - mn) / (mx - mn + 1e-9)  # 1e-9 avoids division by zero on flat series


def _season_months(season: str) -> list[int]:
    return {
        "summer": [6, 7, 8],
        "winter": [12, 1, 2],
        "spring": [3, 4, 5],
        "autumn": [9, 10, 11],
    }.get(season, [6, 7, 8])  # default to summer


class DataEngine:
    """
    Single instance created at Flask startup — do not instantiate per-request.
    All heavy aggregations go through DuckDB; thread-safe via internal RLock.
    """

    def __init__(self, parquet_path: str = PARQUET_PATH):
        self.path = parquet_path
        self.demo_mode = False
        self.conn = duckdb.connect(":memory:", read_only=False)
        self._lock = threading.RLock()

        if Path(parquet_path).exists():
            with self._lock:
                safe_path = parquet_path.replace("'", "''")  # basic SQL injection guard
                self.conn.execute(
                    f"CREATE OR REPLACE VIEW solar AS SELECT * FROM read_parquet('{safe_path}')"
                )
            logger.info(f"DataEngine initialisé — {parquet_path}")
        else:
            self.demo_mode = True
            demo_df = self._build_demo_dataframe()
            with self._lock:
                self.conn.register("solar_df", demo_df)
                self.conn.execute("CREATE OR REPLACE VIEW solar AS SELECT * FROM solar_df")
            logger.warning(
                "Fichier Parquet introuvable — démarrage en mode démo avec dataset synthétique"
            )

    def _build_demo_dataframe(self) -> pd.DataFrame:
        """Synthetic dataset covering 3 wilayas × 2 communes × 120 days — enough to exercise the full app."""
        rng = np.random.default_rng(42)
        dates = pd.date_range("2025-01-01", periods=24 * 120, freq="h")

        wilayas = [
            {
                "wilaya_code": 9,  "wilaya_name": "Tamanrasset", "climate": "Saharan",
                "latitude": 22.78, "longitude": 5.52,
                "base_ghi": 0.285, "base_dni": 0.325, "base_dhi": 0.055,
                "t2m": 28.0, "rh2m": 20.0, "ws10m": 4.8, "clearness": 0.74,
                "demand_mw": 68.0, "communes": ["Tamanrasset Centre", "In Amguel"],
            },
            {
                "wilaya_code": 30, "wilaya_name": "Ouargla", "climate": "Arid",
                "latitude": 31.95, "longitude": 5.32,
                "base_ghi": 0.255, "base_dni": 0.295, "base_dhi": 0.050,
                "t2m": 24.0, "rh2m": 24.0, "ws10m": 4.0, "clearness": 0.69,
                "demand_mw": 410.0, "communes": ["Ouargla Centre", "Hassi Messaoud"],
            },
            {
                "wilaya_code": 16, "wilaya_name": "Alger", "climate": "Coastal",
                "latitude": 36.74, "longitude": 3.06,
                "base_ghi": 0.190, "base_dni": 0.220, "base_dhi": 0.045,
                "t2m": 18.0, "rh2m": 62.0, "ws10m": 3.2, "clearness": 0.54,
                "demand_mw": 4280.0, "communes": ["Bab Ezzouar", "Rouiba"],
            },
        ]

        records = []
        hours_arr   = dates.hour.to_numpy()
        day_of_year = dates.dayofyear.to_numpy()
        solar_shape = np.clip(np.sin(np.pi * (hours_arr - 6) / 12), 0, None)
        seasonal    = 1.0 + 0.12 * np.sin(2 * np.pi * day_of_year / 365.25)

        for w in wilayas:
            for idx, commune in enumerate(w["communes"]):
                lat_shift      = (idx - 0.5) * 0.18
                lon_shift      = (idx - 0.5) * 0.18
                commune_scale  = 1.0 + (idx * 0.018)

                ghi = np.clip(
                    w["base_ghi"] * seasonal * (0.30 + 0.85 * solar_shape) * commune_scale
                    + rng.normal(0, 0.008, len(dates)), 0, None,
                )
                dni      = np.clip(ghi * 1.12 + w["base_dni"] * 0.10 + rng.normal(0, 0.006, len(dates)), 0, None)
                dhi      = np.clip(w["base_dhi"] * (0.35 + 0.65 * solar_shape) + rng.normal(0, 0.003, len(dates)), 0, None)
                t2m      = w["t2m"] + 8 * np.sin(2 * np.pi * (hours_arr - 8) / 24) + 3 * np.sin(2 * np.pi * day_of_year / 365.25)
                rh2m     = np.clip(w["rh2m"] + 12 * (1 - solar_shape) + rng.normal(0, 2.5, len(dates)), 8, 95)
                ws10m    = np.clip(w["ws10m"] + 1.3 * np.sin(2 * np.pi * hours_arr / 24) + rng.normal(0, 0.35, len(dates)), 0.2, None)
                clearness = np.clip(w["clearness"] + 0.05 * solar_shape + rng.normal(0, 0.015, len(dates)), 0.25, 0.9)
                demand   = np.clip(
                    w["demand_mw"] * (0.85 + 0.20 * np.sin(2 * np.pi * (hours_arr - 13) / 24) ** 2)
                    + rng.normal(0, max(5.0, w["demand_mw"] * 0.025), len(dates)), 0, None,
                )

                for i, dt in enumerate(dates):
                    records.append({
                        "datetime":     dt,
                        "wilaya_code":  w["wilaya_code"],
                        "wilaya_name":  w["wilaya_name"],
                        "commune_name": commune,
                        "climate":      w["climate"],
                        "latitude":     round(w["latitude"] + lat_shift, 5),
                        "longitude":    round(w["longitude"] + lon_shift, 5),
                        "GHI":          float(round(ghi[i], 5)),
                        "DNI":          float(round(dni[i], 5)),
                        "DHI":          float(round(dhi[i], 5)),
                        "T2M":          float(round(t2m[i], 4)),
                        "RH2M":         float(round(rh2m[i], 4)),
                        "WS10M":        float(round(ws10m[i], 4)),
                        "CLEARNESS_KT": float(round(clearness[i], 5)),
                        "demand_mw":    float(round(demand[i], 4)),
                    })

        df = pd.DataFrame.from_records(records)
        os.makedirs(CACHE_DIR, exist_ok=True)
        return df

    def _q(self, sql: str, params=None) -> pd.DataFrame:
        """Thread-safe DuckDB query execution."""
        try:
            with self._lock:
                if params:
                    return self.conn.execute(sql, params).df()
                return self.conn.execute(sql).df()
        except Exception as e:
            logger.error(f"Erreur DuckDB: {e}\nSQL: {sql}")
            raise

    @lru_cache(maxsize=8)
    def get_wilayas_summary(self, filters_json: str = "{}") -> list[dict]:
        """
        Full-dataset wilaya aggregation. Cached because the query takes ~500 ms on 12M rows.
        filters_json must be a JSON string (not dict) so lru_cache can hash it.
        """
        filters = json.loads(filters_json)

        sql = """
        SELECT
            wilaya_code,
            ANY_VALUE(wilaya_name)            AS wilaya_name,
            ANY_VALUE(climate)                AS climate,
            ANY_VALUE(latitude)               AS latitude,
            ANY_VALUE(longitude)              AS longitude,
            AVG(GHI)                          AS mean_ghi,
            PERCENTILE_CONT(0.95)
                WITHIN GROUP (ORDER BY GHI)   AS peak_ghi,
            AVG(CASE WHEN GHI > ?
                THEN 1.0 ELSE 0.0 END)        AS sunshine_frac,
            AVG(CLEARNESS_KT)                 AS mean_clearness,
            STDDEV(GHI)                       AS variability,
            AVG(DNI)                          AS mean_dni,
            AVG(DHI)                          AS mean_dhi,
            AVG(T2M)                          AS mean_t2m,
            AVG(demand_mw)                    AS mean_demand,
            COUNT(DISTINCT commune_name)      AS n_communes,
            COUNT(*)                          AS n_rows
        FROM solar
        GROUP BY wilaya_code
        """
        df = self._q(sql, [GHI_THRESH])

        # Normalized scores — computed cross-wilaya so rankings are comparable
        df["s_mean_ghi"]        = _norm01(df["mean_ghi"])
        df["s_peak_ghi"]        = _norm01(df["peak_ghi"])
        df["s_sunshine_hours"]  = _norm01(df["sunshine_frac"])
        df["s_clearness"]       = _norm01(df["mean_clearness"])
        df["s_low_variability"] = _norm01(-df["variability"])

        df["score"] = (
            df["s_mean_ghi"]        * SCORE_WEIGHTS["mean_ghi"]       +
            df["s_peak_ghi"]        * SCORE_WEIGHTS["peak_ghi"]       +
            df["s_sunshine_hours"]  * SCORE_WEIGHTS["sunshine_hours"] +
            df["s_clearness"]       * SCORE_WEIGHTS["clearness"]      +
            df["s_low_variability"] * SCORE_WEIGHTS["low_variability"]
        ) * 100
        df["score"] = df["score"].round(1)
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
        df.insert(0, "rank", df.index + 1)

        df["region"]      = df["climate"].map(CLIMATE_REGIONS).fillna("Inconnu")
        df["potential_mw"] = (df["mean_ghi"] * 8760 * 0.18 * 100).round(0)  # 100 km² reference area

        if filters.get("region"):
            df = df[df["region"] == filters["region"]]
        if filters.get("climate"):
            df = df[df["climate"] == filters["climate"]]
        if filters.get("minScore"):
            df = df[df["score"] >= float(filters["minScore"])]
        if filters.get("search"):
            q = filters["search"].lower()
            df = df[df["wilaya_name"].str.lower().str.contains(q, na=False)]
        if filters.get("sort") == "ghi":
            df = df.sort_values("mean_ghi", ascending=False)
        elif filters.get("sort") == "potential":
            df = df.sort_values("potential_mw", ascending=False)

        return df.to_dict(orient="records")

    def get_wilaya_detail(self, code: int | str) -> Optional[dict]:
        wilayas = self.get_wilayas_summary()
        code_int = int(code)
        matches = [w for w in wilayas if int(w["wilaya_code"]) == code_int]
        return matches[0] if matches else None

    def get_zones(self, wilaya_name: Optional[str] = None) -> list[dict]:
        where  = ""
        params = [GHI_THRESH]
        if wilaya_name:
            where = "WHERE wilaya_name = ?"
            params.append(wilaya_name)

        sql = f"""
        SELECT
            wilaya_code,
            ANY_VALUE(wilaya_name)   AS wilaya_name,
            commune_name,
            ANY_VALUE(latitude)      AS latitude,
            ANY_VALUE(longitude)     AS longitude,
            ANY_VALUE(climate)       AS climate,
            AVG(GHI)                 AS mean_ghi,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY GHI) AS peak_ghi,
            AVG(CASE WHEN GHI > ? THEN 1.0 ELSE 0.0 END) AS sunshine_frac,
            AVG(CLEARNESS_KT)        AS mean_clearness,
            STDDEV(GHI)              AS variability,
            AVG(T2M)                 AS mean_t2m,
            AVG(DHI)                 AS mean_dhi,
            AVG(WS10M)               AS mean_ws10m,
            AVG(DNI)                 AS mean_dni,
            AVG(demand_mw)           AS mean_demand
        FROM solar
        {where}
        GROUP BY wilaya_code, commune_name
        """
        df = self._q(sql, params)

        # Cross-zone normalization so scores are relative within the wilaya
        df["s_mean_ghi"]        = _norm01(df["mean_ghi"])
        df["s_peak_ghi"]        = _norm01(df["peak_ghi"])
        df["s_sunshine_hours"]  = _norm01(df["sunshine_frac"])
        df["s_clearness"]       = _norm01(df["mean_clearness"])
        df["s_low_variability"] = _norm01(-df["variability"])
        df["score"] = (
            df["s_mean_ghi"]        * SCORE_WEIGHTS["mean_ghi"]       +
            df["s_peak_ghi"]        * SCORE_WEIGHTS["peak_ghi"]       +
            df["s_sunshine_hours"]  * SCORE_WEIGHTS["sunshine_hours"] +
            df["s_clearness"]       * SCORE_WEIGHTS["clearness"]      +
            df["s_low_variability"] * SCORE_WEIGHTS["low_variability"]
        ) * 100
        df["score"] = df["score"].round(1)
        df = df.sort_values("score", ascending=False).reset_index(drop=True)

        df["capacity_factor"] = (df["mean_ghi"] * CAPACITY_FACTOR).round(3)
        df["id"] = (
            df["wilaya_code"].astype(str) + "_" +
            df["commune_name"].str.lower().str.replace(" ", "_", regex=False)
        )
        df["region"]         = df["climate"].map(CLIMATE_REGIONS).fillna("Inconnu")
        df["recommendation"] = df["score"].apply(lambda s: "build" if s >= 80 else ("study" if s >= 60 else "wait"))
        df["risk_sand"]      = df["climate"].apply(lambda c: "high" if c == "Saharan" else ("medium" if c == "Arid" else "low"))
        df["grid_dist_km"]   = (df["latitude"].abs() * 3.5).round(0)
        df["area_km2"]       = ZONE_AVERAGE_AREA_KM2

        return df.to_dict(orient="records")

    def get_zone_by_id(self, zone_id: str) -> Optional[dict]:
        parts = zone_id.split("_", 1)
        if len(parts) < 2:
            return None
        wilaya_code  = parts[0]
        commune_slug = parts[1]
        zones = self.get_zones()
        for z in zones:
            if str(z["wilaya_code"]) == wilaya_code:
                if z["commune_name"].lower().replace(" ", "_") == commune_slug:
                    return z
        return None

    def get_monthly_timeseries(self, wilaya_code: int, variable: str = "GHI") -> dict:
        valid_vars = ["GHI", "DNI", "DHI", "T2M", "CLEARNESS_KT", "demand_mw", "WS10M", "RH2M"]
        if variable.upper() not in [v.upper() for v in valid_vars]:
            variable = "GHI"
        col = next((v for v in valid_vars if v.upper() == variable.upper()), "GHI")

        sql = f"""
        SELECT
            strftime(CAST(datetime AS TIMESTAMP), '%Y-%m') AS month,
            AVG({col}) AS value
        FROM solar
        WHERE wilaya_code = ?
        GROUP BY month
        ORDER BY month
        """
        df = self._q(sql, [int(wilaya_code)])
        unit_map = {
            "GHI": "kWh/m²/mois", "DNI": "kWh/m²/mois", "DHI": "kWh/m²/mois",
            "T2M": "°C", "CLEARNESS_KT": "sans unité", "demand_mw": "MW",
            "WS10M": "m/s", "RH2M": "%",
        }
        return {
            "labels":   df["month"].tolist(),
            "values":   df["value"].round(2).tolist(),
            "variable": col,
            "unit":     unit_map.get(col, ""),
        }

    def get_hourly_profile(self, wilaya_code: int, season: str = "summer") -> dict:
        months = _season_months(season)
        # DuckDB doesn't support list params natively — build placeholders manually
        placeholders = ", ".join(["?"] * len(months))

        sql = f"""
        SELECT
            EXTRACT(hour FROM CAST(datetime AS TIMESTAMP)) AS hour,
            AVG(GHI) AS value
        FROM solar
        WHERE wilaya_code = ?
          AND EXTRACT(month FROM CAST(datetime AS TIMESTAMP)) IN ({placeholders})
        GROUP BY hour
        ORDER BY hour
        """
        params = [int(wilaya_code)] + [int(m) for m in months]
        df = self._q(sql, params)
        labels = [f"{int(h):02d}:00" for h in df["hour"].tolist()]
        return {"labels": labels, "values": df["value"].round(3).tolist(), "season": season}

    def get_inference_window(self, wilaya_code: int, n: int = SEQ_LEN) -> pd.DataFrame:
        """Returns the n most recent timesteps for model inference, ordered ascending."""
        sql = f"""
        SELECT {', '.join(FEAT_COLS)}, datetime
        FROM solar
        WHERE wilaya_code = ?
        ORDER BY datetime DESC
        LIMIT ?
        """
        df = self._q(sql, [int(wilaya_code), n])
        df = df.sort_values("datetime").drop(columns=["datetime"])
        return df[FEAT_COLS].fillna(0).astype("float32")

    def get_vmd_window(self, wilaya_code: int, n: int = SEQ_LEN) -> pd.Series:
        """Raw GHI series for VMD decomposition at inference time."""
        sql = """
        SELECT GHI, datetime FROM solar
        WHERE wilaya_code = ?
        ORDER BY datetime DESC LIMIT ?
        """
        df = self._q(sql, [int(wilaya_code), n])
        return df.sort_values("datetime")["GHI"].fillna(0).astype("float32")

    def get_recent_actual(self, wilaya_code: int, days: int = 30, variable: str = "GHI") -> dict:
        valid = {"GHI", "DNI", "DHI", "T2M", "WS10M", "CLEARNESS_KT"}
        v = variable.upper() if variable.upper() in valid else "GHI"

        sql = f"""
        SELECT
            strftime(CAST(datetime AS TIMESTAMP), '%Y-%m-%d') AS day,
            AVG({v}) AS value
        FROM solar
        WHERE wilaya_code = ?
        GROUP BY day
        ORDER BY day DESC
        LIMIT ?
        """
        df = self._q(sql, [int(wilaya_code), days])
        df = df.sort_values("day")
        return {"labels": df["day"].tolist(), "values": df["value"].round(3).tolist()}

    def get_recent_hourly(self, wilaya_code: int, hours: int = 24, variable: str = "GHI") -> list[float]:
        """
        Returns raw hourly values DESC (most recent first) — callers expecting
        chronological order must reverse the list themselves.
        """
        valid = {"GHI", "DNI", "DHI", "T2M", "WS10M", "CLEARNESS_KT"}
        v = variable.upper() if variable.upper() in valid else "GHI"

        sql = f"""
        SELECT {v} AS value
        FROM solar
        WHERE wilaya_code = ?
        ORDER BY datetime DESC
        LIMIT ?
        """
        df = self._q(sql, [int(wilaya_code), hours])
        return df["value"].fillna(0).astype(float).tolist()

    def get_search_data(self) -> tuple[list, list]:
        wilayas = self.get_wilayas_summary()
        zones   = self.get_zones()
        return wilayas, zones