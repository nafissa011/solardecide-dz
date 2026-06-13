"""
Pipeline de prétraitement
Extrait directement du notebook preproc_models.ipynb.
Séparation fit() (entraînement) / transform() (inférence).
"""

import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import KNNImputer
from sklearn.preprocessing import MinMaxScaler

try:
    from vmdpy import VMD
    HAS_VMD = True
except ImportError:
    HAS_VMD = False
    logging.warning("vmdpy non installé — décomposition VMD désactivée")

try:
    import pywt
    HAS_WAVELET = True
except ImportError:
    HAS_WAVELET = False
    logging.warning("PyWavelets non installé — wavelet désactivée")

from config import FEAT_COLS, VMD_K

logger = logging.getLogger(__name__)

VMD_ALPHA = 2000
VMD_TAU = 0
VMD_DC = 0
VMD_INIT = 1
VMD_TOL = 1e-7
VMD_CHUNK = 24 * 60   # 60 jours par chunk


class SolarPreprocessor:
    """
    Pipeline KNN → IQR → IsoForest → MinMax → VMD, identique au notebook.

    fit_transform() : entraînement — apprend les scalers + VMD
    transform()     : inférence   — applique les scalers appris, sans re-fit
    """

    def __init__(self, feat_cols: list[str] = FEAT_COLS, vmd_k: int = VMD_K):
        self.feat_cols = feat_cols
        self.vmd_k = vmd_k
        self.scaler: MinMaxScaler | None = None
        self._fitted = False

    def knn_impute(self, df: pd.DataFrame) -> pd.DataFrame:
        miss = df[self.feat_cols].isnull().sum().sum()
        if miss > 0:
            df = df.copy()
            df[self.feat_cols] = KNNImputer(n_neighbors=5).fit_transform(df[self.feat_cols])
            logger.debug(f"KNN : {miss} valeurs imputées")
        return df

    def iqr_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Facteur 3× (au lieu du 1.5× standard) pour tolérer la variabilité solaire."""
        df = df.copy()
        flagged = 0
        for col in self.feat_cols:
            q1, q3 = df[col].quantile([0.25, 0.75])
            lo, hi = q1 - 3 * (q3 - q1), q3 + 3 * (q3 - q1)
            m = (df[col] < lo) | (df[col] > hi)
            df.loc[m, col] = np.nan
            flagged += int(m.sum())
        df[self.feat_cols] = df[self.feat_cols].ffill().bfill()
        logger.debug(f"IQR : {flagged} outliers remplacés")
        return df

    def isolation_forest(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        preds = IsolationForest(contamination=0.01, random_state=42).fit_predict(
            df[self.feat_cols].fillna(0).values
        )
        anoms = preds == -1
        df.loc[anoms, self.feat_cols] = np.nan
        df[self.feat_cols] = df[self.feat_cols].ffill().bfill()
        logger.debug(f"IsoForest : {int(anoms.sum())} anomalies supprimées")
        return df

    def minmax_normalize(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        df = df.copy()
        if fit:
            self.scaler = MinMaxScaler()
            df[self.feat_cols] = self.scaler.fit_transform(df[self.feat_cols])
        else:
            if self.scaler is None:
                raise RuntimeError("Scaler non initialisé — appeler fit_transform() d'abord")
            df[self.feat_cols] = self.scaler.transform(df[self.feat_cols])
        return df

    def vmd_decompose(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Décompose GHI en K modes via VMD et les ajoute comme colonnes VMD_M1…VMD_Mk.
        Mode 1 → tendance basse fréquence
        Mode 2 → arc journalier
        Mode 3 → résidu nuageux haute fréquence

        Traitement par chunks de VMD_CHUNK points pour éviter les OOM sur de longues séries.
        Si vmdpy est absent, duplique GHI comme fallback.
        """
        if not HAS_VMD:
            for k in range(self.vmd_k):
                df[f"VMD_M{k+1}"] = df.get("GHI", pd.Series(0, index=df.index))
            return df

        df = df.copy()
        sig = df["GHI"].values
        modes = [np.zeros(len(sig)) for _ in range(self.vmd_k)]

        for s in range(0, len(sig), VMD_CHUNK):
            chunk = sig[s: s + VMD_CHUNK]
            if len(chunk) < 48:
                continue
            # VMD exige une longueur paire
            if len(chunk) % 2:
                chunk = chunk[:-1]
            try:
                u, _, _ = VMD(chunk, VMD_ALPHA, VMD_TAU, self.vmd_k, VMD_DC, VMD_INIT, VMD_TOL)
                for k in range(self.vmd_k):
                    modes[k][s: s + u.shape[1]] = u[k]
            except Exception as e:
                logger.warning(f"VMD chunk {s} échoué : {e}")

        for k in range(self.vmd_k):
            df[f"VMD_M{k+1}"] = modes[k]

        vmd_cols = [f"VMD_M{k+1}" for k in range(self.vmd_k)]
        df[vmd_cols] = df[vmd_cols].ffill().bfill().fillna(0)
        return df

    def vmd_decompose_series(self, ghi: np.ndarray, n_modes: int = None) -> np.ndarray:
        """
        Décompose un vecteur GHI 1D en array (K, N) de modes.
        Utilisé à l'inférence par VMD-PatchTST.
        Retourne np.tile(ghi, (k, 1)) si vmdpy absent ou série trop courte (<48 pts).
        """
        k = n_modes if n_modes is not None else self.vmd_k
        if not HAS_VMD or len(ghi) < 48:
            return np.tile(ghi, (k, 1))

        sig = ghi.copy()
        if len(sig) % 2:
            sig = sig[:-1]
        try:
            u, _, _ = VMD(sig, VMD_ALPHA, VMD_TAU, k, VMD_DC, VMD_INIT, VMD_TOL)
            # VMD peut retourner u.shape[1] < len(ghi) si la série a été tronquée
            if u.shape[1] < len(ghi):
                pad = np.zeros((k, len(ghi) - u.shape[1]))
                u = np.concatenate([u, pad], axis=1)
            return u[:, : len(ghi)]
        except Exception as e:
            logger.warning(f"VMD inférence échoué : {e}")
            return np.tile(ghi, (k, 1))

    def fit(self, X, y=None) -> "SolarPreprocessor":
        """Apprend les scalers sur X. VMD non appliqué ici (pas de colonnes cibles)."""
        if isinstance(X, pd.DataFrame):
            df = X.copy()
        else:
            df = pd.DataFrame(X, columns=self.feat_cols)
        df = self.knn_impute(df)
        df = self.iqr_filter(df)
        df = self.isolation_forest(df)
        df = self.minmax_normalize(df, fit=True)
        self._fitted = True
        return self

    def fit_transform(self, X, y=None) -> np.ndarray:
        self.fit(X)
        return self.transform(X)

    def transform(self, X) -> np.ndarray:
        """IsoForest non ré-appliqué à l'inférence pour éviter le re-fit sur données live."""
        if isinstance(X, pd.DataFrame):
            df = X.copy()
        else:
            df = pd.DataFrame(X, columns=self.feat_cols)
        df = self.knn_impute(df)
        df = self.iqr_filter(df)
        df = self.minmax_normalize(df, fit=False)
        df = self.vmd_decompose(df)
        return df[self.feat_cols].values

    def transform_array(self, arr: np.ndarray) -> np.ndarray:
        """Raccourci inférence : applique uniquement MinMax sur un array (N, F) déjà propre."""
        if self.scaler is None:
            return arr
        return self.scaler.transform(arr)

    def save(self, path: str) -> None:
        state = {
            "scaler": self.scaler,
            "feat_cols": self.feat_cols,
            "vmd_k": self.vmd_k,
            "_fitted": self._fitted,
        }
        with open(path, "wb") as f:
            pickle.dump(state, f)
        logger.info(f"Preprocessor sauvegardé → {path}")

    @classmethod
    def load(cls, path: str) -> "SolarPreprocessor":
        with open(path, "rb") as f:
            state = pickle.load(f)
        p = cls(feat_cols=state["feat_cols"], vmd_k=state["vmd_k"])
        p.scaler = state["scaler"]
        p._fitted = state["_fitted"]
        logger.info(f"Preprocessor chargé ← {path}")
        return p