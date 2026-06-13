"""
ModelLoader — registry des modèles IA.

Importé par `app.py`, `ai_forecasting.py`, `services/forecasting_service.py`.

    loader = ModelLoader()
    loader.get_all_metadata()     -> list[dict]
    loader.load(model_id)         -> objet modèle ou None
    loader.is_available(model_id) -> bool

Quand le checkpoint demandé n'existe pas, `load()` renvoie `None` et
les services tombent en mode fallback — voir `ai_forecasting.py` (~ligne 165)
et `services/forecasting_service.py`.

Checkpoints réels :
    ml/prevision/best_forecast_model.pkl
    ml/comparaison_wilaya/model_Hybrid_Ridge_MLP.pkl
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_DEFAULT_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "hybrid_nhits_lstm",
        "name": "Hybride N-HiTS + LSTM",
        "variable": "GHI",
        "horizon": "24h-1an",
        "mae": 0.8155, "rmse": 1.0971, "mape": 2.03, "r2": 0.9894,
        "fiabilite": 97.97,
        "checkpoint": "ml/prevision/best_forecast_model.pkl",
    },
    {
        "id": "nhits", "name": "N-HiTS", "variable": "GHI", "horizon": "24h",
        "mae": 0.9936, "rmse": 1.3028, "mape": 2.46, "r2": 0.9850, "fiabilite": 97.54,
    },
    {
        "id": "patchtst", "name": "PatchTST", "variable": "GHI", "horizon": "24h",
        "mae": 1.0999, "rmse": 1.4289, "mape": 2.71, "r2": 0.9820, "fiabilite": 97.29,
    },
    {
        "id": "lstm", "name": "LSTM", "variable": "GHI", "horizon": "24h",
        "mae": 1.0538, "rmse": 1.4043, "mape": 2.67, "r2": 0.9827, "fiabilite": 97.33,
    },
    {
        "id": "hybrid_ridge_mlp",
        "name": "Hybrid Ridge + MLP (comparaison wilayas)",
        "variable": "score", "horizon": "static",
        "mae": 0.00085, "rmse": 0.001405, "mape": None, "r2": 0.999991,
        "fiabilite": 99.26,
        "checkpoint": "ml/comparaison_wilaya/model_Hybrid_Ridge_MLP.pkl",
    },
]


class ModelLoader:
    """Lazy-loading model registry with in-process cache."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
        self._cache: dict[str, Any] = {}
        self._registry = self._build_registry()

    def _build_registry(self) -> list[dict[str, Any]]:
        registry: list[dict[str, Any]] = []
        for entry in _DEFAULT_REGISTRY:
            item = dict(entry)
            ckpt = entry.get("checkpoint")
            if ckpt:
                full = self.base_dir / ckpt
                item["available"] = full.exists()
                item["checkpoint_path"] = str(full)
            else:
                item["available"] = False
            registry.append(item)

        # Overwrite hardcoded metrics with averaged values from training runs if available
        summary_path = self.base_dir / "ml" / "prevision" / "final_summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                averages = summary.get("model_averages", {}) or {}
                alias = {
                    "Hybride N-HiTS+LSTM": "hybrid_nhits_lstm",
                    "N-HiTS": "nhits",
                    "PatchTST": "patchtst",
                    "LSTM": "lstm",
                }
                for label, mid in alias.items():
                    m = averages.get(label)
                    if not m:
                        continue
                    for item in registry:
                        if item["id"] == mid:
                            item.update({
                                "mae":  round(float(m.get("mae",  item["mae"])),  4),
                                "rmse": round(float(m.get("rmse", item["rmse"])), 4),
                                "mape": round(float(m.get("mape", item["mape"] or 0)), 2),
                                "r2":   round(float(m.get("r2",   item["r2"])),   4),
                                "fiabilite": round(float(m.get("fiabilite", item["fiabilite"])), 2),
                            })
            except Exception as exc:
                logger.warning("ModelLoader: lecture final_summary.json échouée: %s", exc)
        return registry

    def get_all_metadata(self) -> list[dict[str, Any]]:
        return [dict(it) for it in self._registry]

    def get_metadata(self, model_id: str) -> dict[str, Any] | None:
        for it in self._registry:
            if it["id"] == model_id:
                return dict(it)
        return None

    def is_available(self, model_id: str) -> bool:
        meta = self.get_metadata(model_id)
        return bool(meta and meta.get("available"))

    def load(self, model_id: str) -> Any | None:
        if model_id in self._cache:
            return self._cache[model_id]
        meta = self.get_metadata(model_id)
        if not meta or not meta.get("available"):
            return None
        try:
            if model_id == "hybrid_nhits_lstm":
                from ml.prevision.forecast_service import load_model as _load_hybrid
                bundle = _load_hybrid()
                self._cache[model_id] = bundle
                return bundle
            if model_id == "hybrid_ridge_mlp":
                # Side-effect import registers the class needed for joblib unpickling
                from ml.comparaison_wilaya import compare as _cmp
                import joblib
                bundle = joblib.load(meta["checkpoint_path"])
                self._cache[model_id] = bundle
                return bundle
        except Exception as exc:
            logger.warning("ModelLoader.load(%s) failed: %s", model_id, exc)
            return None
        return None