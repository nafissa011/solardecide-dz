"""Zone recommendation model service — loads and runs PyTorch and sklearn models."""

import pickle
import logging
from typing import Dict, List, Any, Optional

import numpy as np
import torch
import torch.nn as nn
from pathlib import Path

logger = logging.getLogger(__name__)


class ZoneModelService:

    def __init__(self, models_root: str = None):
        if models_root is None:
            base_dir = Path(__file__).parent.parent
            models_root = base_dir / "zone recommendation" / "data"

        self.models_root = Path(models_root)
        self.loaded_models = {}
        self.loaded_scalers = {}
        logger.info(f"ZoneModelService initialized with models root: {self.models_root}")

    def _get_model_path(self, approach: str, model_name: str) -> Optional[Path]:
        """Tries .pt then .pkl under <approach>/models/."""
        model_dir = self.models_root / approach / "models"
        for ext in ['.pt', '.pkl']:
            model_path = model_dir / f"{model_name}{ext}"
            if model_path.exists():
                return model_path
        return None

    def _get_scaler_path(self, approach: str) -> Optional[Path]:
        scaler_path = self.models_root / approach / "scaler.pkl"
        return scaler_path if scaler_path.exists() else None

    def load_model(self, approach: str, model_name: str) -> Any:
        cache_key = f"{approach}/{model_name}"
        if cache_key in self.loaded_models:
            return self.loaded_models[cache_key]

        model_path = self._get_model_path(approach, model_name)
        if model_path is None:
            raise FileNotFoundError(f"Model not found: {approach}/{model_name}")

        try:
            if model_path.suffix == '.pt':
                model = torch.load(model_path, map_location='cpu')
                model.eval()
            else:
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)

            self.loaded_models[cache_key] = model
            logger.info(f"Loaded model: {cache_key}")
            return model
        except Exception as e:
            logger.error(f"Failed to load model {cache_key}: {e}")
            raise

    def load_scaler(self, approach: str) -> Any:
        if approach in self.loaded_scalers:
            return self.loaded_scalers[approach]

        scaler_path = self._get_scaler_path(approach)
        if scaler_path is None:
            raise FileNotFoundError(f"Scaler not found for approach: {approach}")

        try:
            with open(scaler_path, 'rb') as f:
                scaler = pickle.load(f)
            self.loaded_scalers[approach] = scaler
            logger.info(f"Loaded scaler for approach: {approach}")
            return scaler
        except Exception as e:
            logger.error(f"Failed to load scaler for {approach}: {e}")
            raise

    def predict_zone_score(self, approach: str, model_name: str, zone_features: Dict[str, float]) -> float:
        model = self.load_model(approach, model_name)
        scaler = self.load_scaler(approach)

        # Feature order must match training. new_approach may include VMD features —
        # load feature list from model metadata when that's available.
        feature_order = [
            "mean_ghi", "peak_ghi", "sunshine_frac", "mean_clearness",
            "variability", "mean_t2m", "mean_ws10m", "mean_dni", "mean_dhi"
        ]

        X = np.array([[zone_features.get(f, 0.0) for f in feature_order]], dtype=np.float32)
        X_scaled = scaler.transform(X)

        try:
            if isinstance(model, nn.Module):
                with torch.no_grad():
                    prediction = model(torch.FloatTensor(X_scaled)).item()
            else:
                prediction = model.predict(X_scaled)[0]
        except Exception as e:
            logger.error(f"Prediction failed for {approach}/{model_name}: {e}")
            prediction = 50.0

        return float(prediction)

    def get_available_models(self) -> Dict[str, List[str]]:
        approaches = ["old_approach", "new_approach"]
        available = {}
        for approach in approaches:
            model_dir = self.models_root / approach / "models"
            if not model_dir.exists():
                available[approach] = []
                continue
            # Deduplicate names that exist in both .pt and .pkl
            names = {f.stem for ext in ['.pt', '.pkl'] for f in model_dir.glob(f"*{ext}")}
            available[approach] = sorted(names)
        return available