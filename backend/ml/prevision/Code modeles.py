
from __future__ import annotations

import os
import json
import math
import random
import warnings
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

warnings.filterwarnings("ignore")

import joblib
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from xgboost import XGBRegressor

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader


# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(BASE_DIR, "dataset.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs_patchtst_revin")
os.makedirs(OUTPUT_DIR, exist_ok=True)

RANDOM_STATE = 42
TRAIN_END_YEAR = 2022
TEST_YEAR = 2023
TARGET_COL = "GHI"
TARGET_RAW_COL = "GHI_RAW_TARGET"
WILAYA_COL = "wilaya_name"
DATETIME_COL = "datetime"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

FEATURE_COLS = [
    "GHI", "DNI", "DHI",
    "T2M", "T2M_MAX", "T2M_MIN",
    "WS10M", "RH2M",
    "CLRSKY_GHI", "CLEARNESS_KT", "PRECIP_MM",
]

HORIZON_CONFIGS = {
    "monthly": {
        "label": "Mensuel",
        "look_back": 12,
    },
    "weekly": {
        "label": "Hebdomadaire",
        "look_back": 16,
    },
    "daily": {
        "label": "Journalier",
        "look_back": 30,
    },
}

MODEL_NAMES = ["PatchTST", "XGBoost", "RandomForest"]
SEP = "═" * 86


def set_seed(seed: int = RANDOM_STATE) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


set_seed(RANDOM_STATE)


# ══════════════════════════════════════════════════════════════════════
# MÉTRIQUES / UTILITAIRES
# ══════════════════════════════════════════════════════════════════════
def mape_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    # Exclude near-zero actuals to avoid division explosion
    mask = np.abs(y_true) > 1e-6
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100.0)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))
    mape = float(mape_score(y_true, y_pred))
    return {"RMSE": rmse, "MAE": mae, "R2": r2, "MAPE": mape}


def save_json(obj: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def validate_columns(df: pd.DataFrame) -> None:
    required = {DATETIME_COL, WILAYA_COL, *FEATURE_COLS}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(
            f"Colonnes manquantes dans dataset.csv : {missing}. "
            f"Colonnes trouvées : {list(df.columns)}"
        )


# ══════════════════════════════════════════════════════════════════════
# DATASET PYTORCH
# ══════════════════════════════════════════════════════════════════════
class SequenceDataset(Dataset):
    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx: int):
        return self.X[idx], self.y[idx]


# ══════════════════════════════════════════════════════════════════════
# PATCHTST + REVIN
# ══════════════════════════════════════════════════════════════════════
class RevIN(nn.Module):
    """
    Reversible Instance Normalization (Kim et al. 2022).
    Normalizes input during forward pass and reverses it after prediction
    to handle non-stationary time series without distribution shift.
    Input shape: [B, L, C]
    """

    def __init__(self, num_features: int, eps: float = 1e-5, affine: bool = True, subtract_last: bool = False):
        super().__init__()
        self.num_features = num_features
        self.eps = eps
        self.affine = affine
        self.subtract_last = subtract_last

        if affine:
            self.affine_weight = nn.Parameter(torch.ones(1, 1, num_features))
            self.affine_bias = nn.Parameter(torch.zeros(1, 1, num_features))
        else:
            self.register_parameter("affine_weight", None)
            self.register_parameter("affine_bias", None)

        self._cached_mean = None
        self._cached_stdev = None
        self._cached_last = None

    def _get_statistics(self, x: torch.Tensor) -> None:
        # subtract_last uses the final timestep as reference instead of the mean
        # (better for non-stationary series with strong trends)
        if self.subtract_last:
            self._cached_last = x[:, -1:, :].detach()
            centered = x - self._cached_last
            self._cached_mean = None
        else:
            self._cached_mean = x.mean(dim=1, keepdim=True).detach()
            centered = x - self._cached_mean
            self._cached_last = None

        var = torch.var(centered, dim=1, keepdim=True, unbiased=False)
        self._cached_stdev = torch.sqrt(var + self.eps).detach()

    def _normalize(self, x: torch.Tensor) -> torch.Tensor:
        self._get_statistics(x)
        if self.subtract_last:
            x = x - self._cached_last
        else:
            x = x - self._cached_mean
        x = x / self._cached_stdev
        if self.affine:
            x = x * self.affine_weight + self.affine_bias
        return x

    def _denormalize(self, x: torch.Tensor) -> torch.Tensor:
        if self.affine:
            x = (x - self.affine_bias) / (self.affine_weight + self.eps)
        x = x * self._cached_stdev
        if self.subtract_last:
            x = x + self._cached_last
        else:
            x = x + self._cached_mean
        return x

    def forward(self, x: torch.Tensor, mode: str) -> torch.Tensor:
        if mode == "norm":
            return self._normalize(x)
        if mode == "denorm":
            return self._denormalize(x)
        raise ValueError(f"Mode RevIN inconnu : {mode}")


class PatchTSTRegressor(nn.Module):
    """
    PatchTST (Nie et al. 2023) adapted for regression.
    Splits each channel into overlapping patches, projects them to d_model,
    then runs a shared Transformer encoder (channel-independent strategy).

    Input  : [B, L, C]
    Output : [B]
    """

    def __init__(
        self,
        context_length: int,
        input_dim: int,
        patch_len: int = 8,
        stride: int = 4,
        d_model: int = 128,
        n_heads: int = 8,
        n_layers: int = 4,
        d_ff: int = 256,
        dropout: float = 0.1,
        fc_dropout: float = 0.1,
        revin: bool = True,
        revin_affine: bool = True,
        subtract_last: bool = False,
        padding_patch: str = "end",
    ):
        super().__init__()
        self.context_length = context_length
        self.input_dim = input_dim
        self.patch_len = min(patch_len, context_length)
        self.stride = max(1, min(stride, self.patch_len))
        self.d_model = d_model
        self.padding_patch = padding_patch

        if revin:
            self.revin = RevIN(
                num_features=input_dim,
                affine=revin_affine,
                subtract_last=subtract_last,
            )
        else:
            self.revin = None

        self.pad_len = self.stride if padding_patch == "end" else 0

        self.patch_num = ((context_length + self.pad_len - self.patch_len) // self.stride) + 1
        if self.patch_num <= 0:
            raise ValueError("Configuration PatchTST invalide : nombre de patches <= 0")

        self.patch_proj = nn.Linear(self.patch_len, d_model)
        self.pos_embedding = nn.Parameter(torch.randn(1, self.patch_num, d_model) * 0.02)
        self.input_dropout = nn.Dropout(dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_ff,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,  # Pre-LN for training stability
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

        self.flatten_dim = input_dim * self.patch_num * d_model
        self.head = nn.Sequential(
            nn.LayerNorm(self.flatten_dim),
            nn.Dropout(fc_dropout),
            nn.Linear(self.flatten_dim, d_ff),
            nn.GELU(),
            nn.Dropout(fc_dropout),
            nn.Linear(d_ff, 1),
        )

    def _patchify(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, C, L]
        if self.pad_len > 0:
            x = F.pad(x, (0, self.pad_len), mode="replicate")
        x = x.unfold(dimension=-1, size=self.patch_len, step=self.stride)
        return x

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        bsz, seq_len, n_feat = x.shape
        if seq_len != self.context_length:
            raise ValueError(f"context_length attendu={self.context_length}, reçu={seq_len}")
        if n_feat != self.input_dim:
            raise ValueError(f"input_dim attendu={self.input_dim}, reçu={n_feat}")

        if self.revin is not None:
            x = self.revin(x, mode="norm")

        x = x.transpose(1, 2)          # [B, L, C] -> [B, C, L]
        x = self._patchify(x)          # [B, C, patch_num, patch_len]
        if x.size(2) != self.patch_num:
            raise RuntimeError(
                f"Nombre de patches inattendu : attendu={self.patch_num}, obtenu={x.size(2)}"
            )

        # Channel-independent: each channel processed separately through the same encoder
        x = self.patch_proj(x)                                    # [B, C, patch_num, d_model]
        x = x.reshape(bsz * n_feat, self.patch_num, self.d_model)
        x = self.input_dropout(x + self.pos_embedding)
        x = self.encoder(x)

        x = x.reshape(bsz, n_feat, self.patch_num, self.d_model)
        x = x.reshape(bsz, n_feat * self.patch_num * self.d_model)

        out = self.head(x).squeeze(-1)
        return out


# ══════════════════════════════════════════════════════════════════════
# AGRÉGATION PAR HORIZON
# ══════════════════════════════════════════════════════════════════════
def load_dataset(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Fichier introuvable : {path}\n"
            f"Place dataset.csv dans le même dossier que le script."
        )
    df = pd.read_csv(path)
    validate_columns(df)
    df[DATETIME_COL] = pd.to_datetime(df[DATETIME_COL])
    df = df.sort_values([WILAYA_COL, DATETIME_COL]).reset_index(drop=True)
    return df


def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    out = (
        df.assign(
            year=df[DATETIME_COL].dt.year,
            month=df[DATETIME_COL].dt.month,
        )
        .groupby([WILAYA_COL, "year", "month"], as_index=False)[FEATURE_COLS]
        .mean()
    )
    out[DATETIME_COL] = pd.to_datetime(out[["year", "month"]].assign(day=1))
    out = out.sort_values([WILAYA_COL, DATETIME_COL]).reset_index(drop=True)
    return out


def aggregate_weekly(df: pd.DataFrame) -> pd.DataFrame:
    iso = df[DATETIME_COL].dt.isocalendar()
    tmp = df.copy()
    tmp["iso_year"] = iso.year.astype(int)
    tmp["iso_week"] = iso.week.astype(int)

    out = (
        tmp.groupby([WILAYA_COL, "iso_year", "iso_week"], as_index=False)[FEATURE_COLS]
        .mean()
    )
    # ISO week string format required by strptime %G-W%V-%u
    out[DATETIME_COL] = pd.to_datetime(
        out["iso_year"].astype(str)
        + "-W"
        + out["iso_week"].astype(str).str.zfill(2)
        + "-1",
        format="%G-W%V-%u",
    )
    out["year"] = out[DATETIME_COL].dt.year
    out = out.sort_values([WILAYA_COL, DATETIME_COL]).reset_index(drop=True)
    return out


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy()
    tmp[DATETIME_COL] = tmp[DATETIME_COL].dt.floor("D")
    out = (
        tmp.groupby([WILAYA_COL, DATETIME_COL], as_index=False)[FEATURE_COLS]
        .mean()
    )
    out["year"] = out[DATETIME_COL].dt.year
    out = out.sort_values([WILAYA_COL, DATETIME_COL]).reset_index(drop=True)
    return out


def build_horizon_dataframe(df_raw: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if horizon == "monthly":
        out = aggregate_monthly(df_raw)
    elif horizon == "weekly":
        out = aggregate_weekly(df_raw)
    elif horizon == "daily":
        out = aggregate_daily(df_raw)
    else:
        raise ValueError(f"Horizon inconnu : {horizon}")

    out["year"] = out[DATETIME_COL].dt.year
    out[TARGET_RAW_COL] = out[TARGET_COL].astype(float)
    return out


# ══════════════════════════════════════════════════════════════════════
# PRÉTRAITEMENT SANS FUITE
# ══════════════════════════════════════════════════════════════════════
@dataclass
class PreprocessorArtifacts:
    imputer: SimpleImputer
    scaler: StandardScaler
    clip_bounds: Dict[str, Tuple[float, float]]


def fit_preprocessor(train_df: pd.DataFrame, feature_cols: List[str]) -> PreprocessorArtifacts:
    """Fits imputer, IQR clip bounds, and scaler on training data only (no leakage)."""
    imputer = SimpleImputer(strategy="median")
    train_imp = pd.DataFrame(
        imputer.fit_transform(train_df[feature_cols]),
        columns=feature_cols,
        index=train_df.index,
    )

    clip_bounds = {}
    for col in feature_cols:
        q1 = train_imp[col].quantile(0.25)
        q3 = train_imp[col].quantile(0.75)
        iqr = q3 - q1
        if pd.isna(iqr) or iqr == 0:
            lower, upper = float(train_imp[col].min()), float(train_imp[col].max())
        else:
            lower = float(q1 - 3.0 * iqr)
            upper = float(q3 + 3.0 * iqr)
        clip_bounds[col] = (lower, upper)
        train_imp[col] = train_imp[col].clip(lower=lower, upper=upper)

    scaler = StandardScaler()
    scaler.fit(train_imp[feature_cols])

    return PreprocessorArtifacts(
        imputer=imputer,
        scaler=scaler,
        clip_bounds=clip_bounds,
    )


def apply_preprocessor(
    df: pd.DataFrame,
    artifacts: PreprocessorArtifacts,
    feature_cols: List[str],
) -> pd.DataFrame:
    out = df.copy()
    out[feature_cols] = artifacts.imputer.transform(out[feature_cols])
    for col in feature_cols:
        lower, upper = artifacts.clip_bounds[col]
        out[col] = out[col].clip(lower=lower, upper=upper)
    out[feature_cols] = artifacts.scaler.transform(out[feature_cols])
    return out


# ══════════════════════════════════════════════════════════════════════
# SÉQUENCES
# ══════════════════════════════════════════════════════════════════════
def build_sequences(
    df_scaled: pd.DataFrame,
    df_raw_target: pd.DataFrame,
    feature_cols: List[str],
    target_raw_col: str,
    look_back: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """
    Builds sliding-window sequences per wilaya.
    X_seq: (N, look_back, F) for PatchTST
    X_flat: (N, look_back*F) for tree models
    y: raw (unscaled) GHI targets
    """
    X_seq, X_flat, y, meta = [], [], [], []

    wilayas = df_scaled[WILAYA_COL].dropna().unique().tolist()
    for wilaya in wilayas:
        s = df_scaled[df_scaled[WILAYA_COL] == wilaya].sort_values(DATETIME_COL).reset_index(drop=True)
        r = df_raw_target[df_raw_target[WILAYA_COL] == wilaya].sort_values(DATETIME_COL).reset_index(drop=True)
        if len(s) != len(r):
            raise ValueError(f"Incohérence après prétraitement pour la wilaya {wilaya}")
        if len(s) <= look_back:
            continue

        values = s[feature_cols].values.astype(np.float32)
        y_raw = r[target_raw_col].values.astype(np.float32)
        dates = r[DATETIME_COL].values

        for i in range(look_back, len(s)):
            window = values[i - look_back : i, :]
            X_seq.append(window)
            X_flat.append(window.reshape(-1))
            y.append(y_raw[i])
            meta.append(
                {
                    WILAYA_COL: wilaya,
                    DATETIME_COL: pd.Timestamp(dates[i]),
                    "year": int(pd.Timestamp(dates[i]).year),
                }
            )

    X_seq = np.asarray(X_seq, dtype=np.float32)
    X_flat = np.asarray(X_flat, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    meta = pd.DataFrame(meta)
    return X_seq, X_flat, y, meta


def temporal_split(
    X_seq: np.ndarray,
    X_flat: np.ndarray,
    y: np.ndarray,
    meta: pd.DataFrame,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """Strict temporal split: train <= TRAIN_END_YEAR, test == TEST_YEAR."""
    train_mask = meta["year"] <= TRAIN_END_YEAR
    test_mask = meta["year"] == TEST_YEAR
    return (
        X_seq[train_mask.values],
        X_flat[train_mask.values],
        y[train_mask.values],
        X_seq[test_mask.values],
        X_flat[test_mask.values],
        y[test_mask.values],
        meta.loc[test_mask].reset_index(drop=True),
    )


def make_temporal_val_split(X: np.ndarray, y: np.ndarray, val_ratio: float = 0.1):
    """Takes the last val_ratio% of sequences as validation (preserves temporal order)."""
    n_val = max(1, int(len(X) * val_ratio))
    if len(X) <= n_val:
        raise ValueError("Pas assez de séquences pour créer un split de validation.")
    return X[:-n_val], y[:-n_val], X[-n_val:], y[-n_val:]


# ══════════════════════════════════════════════════════════════════════
# PATCHTST : ENTRAÎNEMENT / PRÉDICTION
# ══════════════════════════════════════════════════════════════════════
@dataclass
class PatchTSTArtifacts:
    state_dict: dict
    config: dict
    target_scaler: StandardScaler
    train_history: List[dict]


def train_patchtst(
    X_train: np.ndarray,
    y_train: np.ndarray,
    look_back: int,
    input_dim: int,
    max_epochs: int = 100,
    batch_size: int = 128,
    lr: float = 1e-3,
    patience: int = 15,
) -> Tuple[PatchTSTRegressor, PatchTSTArtifacts]:
    X_tr, y_tr, X_va, y_va = make_temporal_val_split(X_train, y_train, val_ratio=0.1)

    y_scaler = StandardScaler()
    y_tr_scaled = y_scaler.fit_transform(y_tr.reshape(-1, 1)).ravel().astype(np.float32)
    y_va_scaled = y_scaler.transform(y_va.reshape(-1, 1)).ravel().astype(np.float32)

    train_ds = SequenceDataset(X_tr, y_tr_scaled)
    val_ds = SequenceDataset(X_va, y_va_scaled)
    # shuffle=False preserves temporal order within each epoch
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    patch_len = min(max(4, look_back // 3), look_back)
    stride = max(1, patch_len // 2)

    model = PatchTSTRegressor(
        context_length=look_back,
        input_dim=input_dim,
        patch_len=patch_len,
        stride=stride,
        d_model=128,
        n_heads=8,
        n_layers=4,
        d_ff=256,
        dropout=0.1,
        fc_dropout=0.1,
        revin=True,
        revin_affine=True,
        subtract_last=False,
        padding_patch="end",
    ).to(DEVICE)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=4
    )
    criterion = nn.SmoothL1Loss(beta=0.5)  # Less sensitive to outliers than MSE

    best_val = float("inf")
    best_state = None
    bad_epochs = 0
    history = []

    for epoch in range(1, max_epochs + 1):
        model.train()
        train_losses = []
        for xb, yb in train_loader:
            xb = xb.to(DEVICE)
            yb = yb.to(DEVICE)

            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(DEVICE)
                yb = yb.to(DEVICE)
                pred = model(xb)
                loss = criterion(pred, yb)
                val_losses.append(loss.item())

        train_loss = float(np.mean(train_losses)) if train_losses else np.nan
        val_loss = float(np.mean(val_losses)) if val_losses else np.nan
        scheduler.step(val_loss)

        lr_current = float(optimizer.param_groups[0]["lr"])
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
                "lr": lr_current,
            }
        )

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1

        if epoch == 1 or epoch % 10 == 0:
            print(
                f"      Epoch {epoch:03d} | train={train_loss:.5f} | val={val_loss:.5f} | lr={lr_current:.6f}"
            )

        if bad_epochs >= patience:
            print(f"      Early stopping à l'epoch {epoch}")
            break

    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)

    artifacts = PatchTSTArtifacts(
        state_dict=best_state,
        config={
            "context_length": look_back,
            "input_dim": input_dim,
            "patch_len": patch_len,
            "stride": stride,
            "d_model": 128,
            "n_heads": 8,
            "n_layers": 4,
            "d_ff": 256,
            "dropout": 0.1,
            "fc_dropout": 0.1,
            "revin": True,
            "revin_affine": True,
            "subtract_last": False,
            "padding_patch": "end",
        },
        target_scaler=y_scaler,
        train_history=history,
    )
    return model, artifacts


def predict_patchtst(
    model: PatchTSTRegressor,
    artifacts: PatchTSTArtifacts,
    X: np.ndarray,
    batch_size: int = 256,
) -> np.ndarray:
    # Dummy y required by SequenceDataset interface
    ds = SequenceDataset(X, np.zeros(len(X), dtype=np.float32))
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False)
    preds = []
    model.eval()
    with torch.no_grad():
        for xb, _ in loader:
            xb = xb.to(DEVICE)
            pred = model(xb).detach().cpu().numpy().reshape(-1, 1)
            pred = artifacts.target_scaler.inverse_transform(pred).ravel()
            preds.append(pred)
    return np.concatenate(preds) if preds else np.array([], dtype=float)


# ══════════════════════════════════════════════════════════════════════
# ENTRAÎNEMENT PAR HORIZON
# ══════════════════════════════════════════════════════════════════════
def train_models_for_horizon(
    horizon: str,
    df_raw: pd.DataFrame,
) -> dict:
    cfg = HORIZON_CONFIGS[horizon]
    look_back = cfg["look_back"]

    print("\n" + SEP)
    print(f"HORIZON {cfg['label'].upper()}  |  look_back={look_back}")
    print(SEP)

    df_h = build_horizon_dataframe(df_raw, horizon)
    train_rows = df_h[df_h["year"] <= TRAIN_END_YEAR].copy()
    test_rows = df_h[df_h["year"] == TEST_YEAR].copy()

    print(f"  Lignes agrégées : {len(df_h):,}")
    print(f"  Train rows      : {len(train_rows):,}")
    print(f"  Test rows       : {len(test_rows):,}")

    if len(train_rows) == 0 or len(test_rows) == 0:
        raise ValueError(f"Pas assez de données pour l'horizon {horizon}")

    prep = fit_preprocessor(train_rows, FEATURE_COLS)
    df_scaled = apply_preprocessor(df_h, prep, FEATURE_COLS)

    X_seq, X_flat, y, meta = build_sequences(
        df_scaled=df_scaled,
        df_raw_target=df_h,
        feature_cols=FEATURE_COLS,
        target_raw_col=TARGET_RAW_COL,
        look_back=look_back,
    )

    Xtr_seq, Xtr_flat, ytr, Xte_seq, Xte_flat, yte, meta_te = temporal_split(X_seq, X_flat, y, meta)

    print(f"  Séquences train : {len(ytr):,}")
    print(f"  Séquences test  : {len(yte):,}")
    if len(ytr) < 20 or len(yte) < 5:
        raise ValueError(f"Pas assez de séquences utiles pour l'horizon {horizon}")

    print("\n  [1/3] Entraînement PatchTST (RevIN)...")
    patch_model, patch_artifacts = train_patchtst(
        X_train=Xtr_seq,
        y_train=ytr,
        look_back=look_back,
        input_dim=Xtr_seq.shape[-1],
        max_epochs=100,
        batch_size=128,
        lr=1e-3,
        patience=15,
    )
    yhat_patch = predict_patchtst(patch_model, patch_artifacts, Xte_seq)
    met_patch = compute_metrics(yte, yhat_patch)
    print(
        f"      PatchTST  RMSE={met_patch['RMSE']:.3f} | "
        f"MAE={met_patch['MAE']:.3f} | R2={met_patch['R2']:.4f} | MAPE={met_patch['MAPE']:.2f}%"
    )

    print("\n  [2/3] Entraînement XGBoost...")
    Xtr_x, ytr_x, Xva_x, yva_x = make_temporal_val_split(Xtr_flat, ytr, val_ratio=0.1)
    xgb = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=1200,
        max_depth=5,
        learning_rate=0.03,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_alpha=0.0,
        reg_lambda=1.0,
        min_child_weight=3,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        early_stopping_rounds=50,
        eval_metric="rmse",
        verbosity=0,
    )
    xgb.fit(Xtr_x, ytr_x, eval_set=[(Xva_x, yva_x)], verbose=False)
    yhat_xgb = xgb.predict(Xte_flat)
    met_xgb = compute_metrics(yte, yhat_xgb)
    print(
        f"      XGBoost   RMSE={met_xgb['RMSE']:.3f} | "
        f"MAE={met_xgb['MAE']:.3f} | R2={met_xgb['R2']:.4f} | MAPE={met_xgb['MAPE']:.2f}%"
    )

    print("\n  [3/3] Entraînement RandomForest...")
    rf = RandomForestRegressor(
        n_estimators=600,
        max_depth=20,
        min_samples_leaf=2,
        max_features="sqrt",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    rf.fit(Xtr_flat, ytr)
    yhat_rf = rf.predict(Xte_flat)
    met_rf = compute_metrics(yte, yhat_rf)
    print(
        f"      RandomForest RMSE={met_rf['RMSE']:.3f} | "
        f"MAE={met_rf['MAE']:.3f} | R2={met_rf['R2']:.4f} | MAPE={met_rf['MAPE']:.2f}%"
    )

    metrics = {
        "PatchTST": met_patch,
        "XGBoost": met_xgb,
        "RandomForest": met_rf,
    }
    preds = {
        "PatchTST": yhat_patch,
        "XGBoost": yhat_xgb,
        "RandomForest": yhat_rf,
    }

    ranking_metrics = pd.DataFrame(metrics).T.sort_values(["R2", "RMSE"], ascending=[False, True])
    best_model_name = ranking_metrics.index[0]
    print(f"\n  Meilleur modèle {cfg['label']} : {best_model_name}")

    pred_df = meta_te.copy()
    pred_df["y_true"] = yte
    for model_name in MODEL_NAMES:
        pred_df[f"y_pred_{model_name}"] = preds[model_name]
        pred_df[f"abs_err_{model_name}"] = np.abs(pred_df["y_true"] - pred_df[f"y_pred_{model_name}"])

    return {
        "horizon": horizon,
        "label": cfg["label"],
        "look_back": look_back,
        "df_agg": df_h,
        "preprocessor": prep,
        "X_train_seq_shape": tuple(Xtr_seq.shape),
        "X_test_seq_shape": tuple(Xte_seq.shape),
        "metrics": metrics,
        "pred_df": pred_df,
        "best_model_name": best_model_name,
        "models": {
            "PatchTST": patch_model,
            "XGBoost": xgb,
            "RandomForest": rf,
        },
        "artifacts": {
            "PatchTST": patch_artifacts,
            "XGBoost": None,
            "RandomForest": None,
        },
    }


# ══════════════════════════════════════════════════════════════════════
# EXPORTS / VISUALISATIONS
# ══════════════════════════════════════════════════════════════════════
def export_predictions(all_results: Dict[str, dict]) -> None:
    metrics_rows = []
    for horizon, pack in all_results.items():
        pred_path = os.path.join(OUTPUT_DIR, f"predictions_{horizon}.csv")
        pack["pred_df"].to_csv(pred_path, index=False)

        for model_name, met in pack["metrics"].items():
            metrics_rows.append(
                {
                    "horizon": horizon,
                    "label": pack["label"],
                    "model": model_name,
                    **met,
                    "look_back": pack["look_back"],
                }
            )

    metrics_df = pd.DataFrame(metrics_rows)
    metrics_df = metrics_df.sort_values(["horizon", "R2", "RMSE"], ascending=[True, False, True])
    metrics_df.to_csv(os.path.join(OUTPUT_DIR, "metrics_summary.csv"), index=False)


def export_ranking_monthly(all_results: Dict[str, dict]) -> pd.DataFrame:
    pack = all_results["monthly"]
    best_model = pack["best_model_name"]
    pred_df = pack["pred_df"].copy()
    pred_col = f"y_pred_{best_model}"

    ranking = (
        pred_df.groupby(WILAYA_COL)
        .agg(
            ghi_reel=("y_true", "mean"),
            ghi_predit=(pred_col, "mean"),
        )
        .reset_index()
        .sort_values("ghi_predit", ascending=False)
        .reset_index(drop=True)
    )
    ranking.insert(0, "rang", np.arange(1, len(ranking) + 1))
    ranking.to_csv(os.path.join(OUTPUT_DIR, "wilaya_ranking_monthly.csv"), index=False)
    return ranking


def plot_summary(all_results: Dict[str, dict], ranking_monthly: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.patch.set_facecolor("white")

    horizons = [HORIZON_CONFIGS[h]["label"] for h in ["monthly", "weekly", "daily"]]
    x = np.arange(len(horizons))
    w = 0.25
    colors = {"PatchTST": "#2563EB", "XGBoost": "#059669", "RandomForest": "#D97706"}

    ax = axes[0, 0]
    rows = []
    for horizon, pack in all_results.items():
        for model_name, met in pack["metrics"].items():
            rows.append({"horizon": pack["label"], "model": model_name, "R2": met["R2"]})
    df_r2 = pd.DataFrame(rows)
    for i, model_name in enumerate(MODEL_NAMES):
        vals = [df_r2[(df_r2["horizon"] == h) & (df_r2["model"] == model_name)]["R2"].iloc[0] for h in horizons]
        ax.bar(x + (i - 1) * w, vals, width=w, label=model_name, color=colors[model_name])
    ax.axhline(0, color="black", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(horizons)
    ax.set_title("R² par horizon et par modèle")
    ax.set_ylabel("R²")
    ax.legend()

    ax = axes[0, 1]
    rows = []
    for horizon, pack in all_results.items():
        for model_name, met in pack["metrics"].items():
            rows.append({"horizon": pack["label"], "model": model_name, "RMSE": met["RMSE"]})
    df_rmse = pd.DataFrame(rows)
    for i, model_name in enumerate(MODEL_NAMES):
        vals = [df_rmse[(df_rmse["horizon"] == h) & (df_rmse["model"] == model_name)]["RMSE"].iloc[0] for h in horizons]
        ax.bar(x + (i - 1) * w, vals, width=w, label=model_name, color=colors[model_name])
    ax.set_xticks(x)
    ax.set_xticklabels(horizons)
    ax.set_title("RMSE par horizon et par modèle")
    ax.set_ylabel("RMSE (W/m²)")
    ax.legend()

    ax = axes[1, 0]
    monthly_pack = all_results["monthly"]
    best_monthly = monthly_pack["best_model_name"]
    pred_df = monthly_pack["pred_df"].copy()
    top_wilaya = pred_df[WILAYA_COL].value_counts().index[0]
    temp = pred_df[pred_df[WILAYA_COL] == top_wilaya].sort_values(DATETIME_COL)
    ax.plot(temp[DATETIME_COL], temp["y_true"], marker="o", label="Réel", color="black")
    ax.plot(
        temp[DATETIME_COL],
        temp[f"y_pred_{best_monthly}"],
        marker="o",
        linestyle="--",
        label=best_monthly,
        color="#2563EB",
    )
    ax.set_title(f"Mensuel 2023 — {top_wilaya} — Réel vs {best_monthly}")
    ax.set_ylabel("GHI (W/m²)")
    ax.tick_params(axis="x", rotation=30)
    ax.legend()

    ax = axes[1, 1]
    top10 = ranking_monthly.head(10).sort_values("ghi_predit", ascending=True)
    ax.barh(top10[WILAYA_COL], top10["ghi_predit"], color="#2563EB", alpha=0.85, label="Prédit")
    ax.scatter(top10["ghi_reel"], top10[WILAYA_COL], color="black", s=35, label="Réel")
    ax.set_title("Top 10 wilayas — horizon mensuel")
    ax.set_xlabel("GHI moyen 2023 (W/m²)")
    ax.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "resume_modeles_patchtst_revin.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)


def save_best_model_bundles(all_results: Dict[str, dict]) -> None:
    all_best_models = {}

    for horizon, pack in all_results.items():
        prep = pack["preprocessor"]
        best_model_name = pack["best_model_name"]

        bundle = {
            "horizon": horizon,
            "label": pack["label"],
            "look_back": pack["look_back"],
            "feature_cols": FEATURE_COLS,
            "target_col": TARGET_COL,
            "datetime_col": DATETIME_COL,
            "wilaya_col": WILAYA_COL,
            "train_end_year": TRAIN_END_YEAR,
            "test_year": TEST_YEAR,
            "model_name": best_model_name,
            "best_model_name": best_model_name,
            "model_type": best_model_name.lower().replace(" ", "_"),
            "all_model_metrics": pack["metrics"],
            "best_model_metrics": pack["metrics"][best_model_name],
            "metrics": pack["metrics"],
            "preprocessing": {
                "imputer": prep.imputer,
                "scaler": prep.scaler,
                "clip_bounds": prep.clip_bounds,
            },
            "X_train_seq_shape": pack["X_train_seq_shape"],
            "X_test_seq_shape": pack["X_test_seq_shape"],
        }

        if best_model_name == "PatchTST":
            patch_art = pack["artifacts"]["PatchTST"]
            # Move tensors to CPU before pickling (avoids CUDA device mismatch on reload)
            state_dict_cpu = {
                k: v.detach().cpu()
                for k, v in patch_art.state_dict.items()
            }
            bundle.update(
                {
                    "model": None,
                    "serialization_format": "state_dict",
                    "model_config": patch_art.config,
                    "model_state_dict": state_dict_cpu,
                    "target_scaler": patch_art.target_scaler,
                    "train_history": patch_art.train_history,
                }
            )
        else:
            bundle.update(
                {
                    "model": pack["models"][best_model_name],
                    "serialization_format": "sklearn_object",
                }
            )

        all_best_models[horizon] = bundle

    # Filename kept as RandomForest for historical reasons; bundle contains the actual best model per horizon
    save_path = os.path.join(OUTPUT_DIR, "best_model_RandomForest.pkl")
    joblib.dump(all_best_models, save_path)
    print(f"\nModèles sauvegardés : {save_path}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
def main() -> None:
    print(SEP)
    print("SolarDecide DZ — Prédiction GHI corrigée avec vrai PatchTST + RevIN")
    print(SEP)
    print(f"Device          : {DEVICE}")
    print(f"Dataset         : {DATASET_PATH}")
    print(f"Sorties         : {OUTPUT_DIR}")
    print(f"Train           : <= {TRAIN_END_YEAR}")
    print(f"Test            : {TEST_YEAR}")

    df_raw = load_dataset(DATASET_PATH)
    print(f"Lignes brutes   : {len(df_raw):,}")
    print(f"Wilayas         : {df_raw[WILAYA_COL].nunique()}")
    print(f"Période         : {df_raw[DATETIME_COL].min()} -> {df_raw[DATETIME_COL].max()}")

    all_results = {}
    for horizon in ["monthly", "weekly", "daily"]:
        all_results[horizon] = train_models_for_horizon(horizon, df_raw)

    print("\n" + SEP)
    print("RÉSUMÉ GLOBAL")
    print(SEP)

    rows = []
    for horizon, pack in all_results.items():
        for model_name, met in pack["metrics"].items():
            rows.append(
                {
                    "Horizon": pack["label"],
                    "Modèle": model_name,
                    "RMSE": met["RMSE"],
                    "MAE": met["MAE"],
                    "R2": met["R2"],
                    "MAPE": met["MAPE"],
                }
            )
    summary_df = pd.DataFrame(rows).sort_values(["Horizon", "R2", "RMSE"], ascending=[True, False, True])
    print(summary_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    export_predictions(all_results)
    ranking_monthly = export_ranking_monthly(all_results)
    plot_summary(all_results, ranking_monthly)
    save_best_model_bundles(all_results)

    best_map = {pack["label"]: pack["best_model_name"] for pack in all_results.values()}
    save_json(best_map, os.path.join(OUTPUT_DIR, "best_models_by_horizon.json"))

    print("\nTop 10 wilayas mensuelles :")
    print(ranking_monthly.head(10).to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\nFichiers générés :")
    for name in sorted(os.listdir(OUTPUT_DIR)):
        print(f"  - {name}")

    print("\nTerminé avec succès.")


if __name__ == "__main__":
    main()