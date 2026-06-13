"""SolarDZ — Package models (ModelLoader registry).

Distinct du package `ml/`:
  - `ml/`     contient les NOUVEAUX modèles entraînés (Hybride N-HiTS+LSTM,
              Hybrid_Ridge_MLP) chargés directement via joblib.
  - `models/` est le loader-registry historique attendu par
              `ai_forecasting.py` et `services/forecasting_service.py`.
              Restauré durant l'audit (le fichier source manquait).
"""
from .loader import ModelLoader

__all__ = ["ModelLoader"]
