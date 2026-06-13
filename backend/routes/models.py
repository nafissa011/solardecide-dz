import json
from pathlib import Path
from flask import Blueprint, current_app, jsonify
from config import SCORE_WEIGHTS, BASE_DIR

bp = Blueprint("models", __name__)


def _load_real_metrics():
    forecasting_models = []
    zone_rec_new = []
    zone_rec_old = []

    forecasting_metrics_path = Path(BASE_DIR) / "solar factors forecasting" / "data" / "models" / "metrics.json"
    if forecasting_metrics_path.exists():
        with open(forecasting_metrics_path, 'r') as f:
            forecasting_metrics = json.load(f)

        forecasting_model_configs = {
            "patchtst": {
                "name": "PatchTST",
                "family": "Transformer",
                "description": "Patch-based self-supervised learning for time-series forecasting",
                "params": "1.2M",
                "checkpoint": "patchtst.pt",
                "type": "deep_learning",
                "role": "forecasting"
            },
            "tft": {
                "name": "TFT",
                "family": "Transformer",
                "description": "Temporal Fusion Transformer production-ready",
                "params": "2.1M",
                "checkpoint": "tft.pt",
                "type": "deep_learning",
                "role": "forecasting"
            },
            "nhits": {
                "name": "N-HiTS",
                "family": "MLP-Based",
                "description": "Neural hierarchical interpolation for time series forecasting",
                "params": "0.8M",
                "checkpoint": "nhits.pt",
                "type": "deep_learning",
                "role": "forecasting"
            }
        }

        for model_id, metrics in forecasting_metrics.items():
            if model_id in forecasting_model_configs:
                config = forecasting_model_configs[model_id]
                forecasting_models.append({
                    "id": model_id,
                    **config,
                    "mae":       round(metrics.get("mae", 0), 6),
                    "rmse":      round(metrics.get("rmse", 0), 6),
                    "mape":      round(metrics.get("mape", 0), 2),
                    "r2":        round(metrics.get("r2", 0), 6),
                    "available": True
                })

    zone_rec_new_path = Path(BASE_DIR) / "zone recommendation" / "data" / "new_approach" / "metrics.json"
    if zone_rec_new_path.exists():
        with open(zone_rec_new_path, 'r') as f:
            zone_metrics = json.load(f)

        zone_model_configs = {
            "MLP_VMD":              {"name": "MLP + VMD",              "family": "Ensemble",       "params": "0.3M"},
            "ResidualMLP_VMD":      {"name": "Residual MLP + VMD",     "family": "Ensemble",       "params": "0.4M"},
            "GCN":                  {"name": "Graph Conv Network",      "family": "Graph Neural",   "params": "5.1M"},
            "RandomForest_VMD":     {"name": "Random Forest + VMD",    "family": "Ensemble",       "params": "N/A"},
            "GradientBoosting_VMD": {"name": "Gradient Boosting + VMD","family": "Ensemble",       "params": "N/A"},
            "XGBoost":              {"name": "XGBoost",                "family": "Ensemble",       "params": "N/A"},
            "LightGBM":             {"name": "LightGBM",               "family": "Ensemble",       "params": "N/A"},
            "TabNet":               {"name": "TabNet",                 "family": "Neural Network", "params": "2.5M"},
            "StackingEnsemble":     {"name": "Stacking Ensemble",      "family": "Ensemble",       "params": "N/A"},
        }

        for model_id, config in zone_model_configs.items():
            if model_id in zone_metrics:
                metrics = zone_metrics[model_id]
                zone_rec_new.append({
                    "id":          f"zone_new_{model_id.lower()}",
                    "name":        config["name"],
                    "family":      config["family"],
                    "description": f"Zone recommendation using {config['name']} (New Approach)",
                    "params":      config["params"],
                    "type":        "zone_recommendation",
                    "approach":    "new",
                    "mae":         round(metrics.get("mae", 0), 6),
                    "rmse":        round(metrics.get("rmse", 0), 6),
                    "mape":        round(metrics.get("mape", 0), 6),
                    "r2":          round(metrics.get("r2", 0), 6),
                    "available":   True
                })

    zone_rec_old_path = Path(BASE_DIR) / "zone recommendation" / "data" / "old_approach" / "metrics.json"
    if zone_rec_old_path.exists():
        with open(zone_rec_old_path, 'r') as f:
            zone_metrics = json.load(f)

        zone_model_configs = {
            "MLP":              {"name": "MLP",                "family": "Neural Network", "params": "0.5M"},
            "RandomForest":     {"name": "Random Forest",      "family": "Ensemble",       "params": "N/A"},
            "GradientBoosting": {"name": "Gradient Boosting",  "family": "Ensemble",       "params": "N/A"},
            "LinearRegression": {"name": "Linear Regression",  "family": "Regression",     "params": "0.001M"},
            "Ridge":            {"name": "Ridge Regression",   "family": "Regression",     "params": "0.001M"},
        }

        for model_id, config in zone_model_configs.items():
            if model_id in zone_metrics:
                metrics = zone_metrics[model_id]
                zone_rec_old.append({
                    "id":          f"zone_old_{model_id.lower()}",
                    "name":        config["name"],
                    "family":      config["family"],
                    "description": f"Zone recommendation using {config['name']} (Old Approach)",
                    "params":      config["params"],
                    "type":        "zone_recommendation",
                    "approach":    "old",
                    "mae":         round(metrics.get("mae", 0), 6),
                    "rmse":        round(metrics.get("rmse", 0), 6),
                    "mape":        round(metrics.get("mape", 0), 6),
                    "r2":          round(metrics.get("r2", 0), 6),
                    "available":   True
                })

    return forecasting_models, zone_rec_new, zone_rec_old


@bp.get("/models")
def get_models():
    """GET /api/models — all AI systems: forecasting models + zone recommendation approaches."""
    forecasting_models, zone_rec_new, zone_rec_old = _load_real_metrics()

    zone_recommendation_system = {
        "id":          "zone_recommendation",
        "name":        "Zone Recommendation Engine",
        "family":      "Rule-Based Scoring",
        "type":        "rule-based",
        "description": "Weighted composite scoring system for optimal zone selection",
        "role":        "zone_recommendation",
        "use_case":    "Identifies optimal zones for solar installation based on weighted metrics",
        # Formula: composite score = 0.35×GHI + 0.15×Peak GHI + 0.20×Sunshine + 0.15×Clearness + 0.15×Low Variability
        "methodology":     "Composite score = 0.35×GHI + 0.15×Peak GHI + 0.20×Sunshine + 0.15×Clearness + 0.15×Low Variability",
        "score_weights":   SCORE_WEIGHTS,
        "metrics":         {"mae": None, "rmse": None, "mape": None, "r2": None},
        "params":          "0B",
        "available":       True,
        "checkpoint":      None,
        "training_time":   "N/A",
        "evaluation":      "Cross-validated on 4,000+ Algerian communes with climate diversity"
    }

    return jsonify({
        "data": {
            # Sorted by MAE ascending (best model first)
            "forecasting_models":                sorted(forecasting_models, key=lambda x: x["mae"]),
            "zone_recommendation":               zone_recommendation_system,
            "zone_recommendation_new_approach":  sorted(zone_rec_new, key=lambda x: x["mae"]),
            "zone_recommendation_old_approach":  sorted(zone_rec_old, key=lambda x: x["mae"]),
            "summary": {
                "total_systems":                    len(forecasting_models) + len(zone_rec_new) + len(zone_rec_old) + 1,
                "forecasting_count":                len(forecasting_models),
                "zone_recommendation_new_count":    len(zone_rec_new),
                "zone_recommendation_old_count":    len(zone_rec_old),
                "rule_based_count":                 1
            }
        },
        "status": 200
    })


@bp.get("/models/<model_name>")
def get_model_details(model_name):
    """GET /api/models/<model_name>"""
    model_loader = current_app.config["MODEL_LOADER"]
    model_meta = next(
        (m for m in model_loader.get_all_metadata() if m["id"] == model_name.lower()),
        None,
    )
    if not model_meta:
        return jsonify({"error": f"Model {model_name} not found", "status": 404}), 404
    return jsonify({"data": model_meta, "status": 200})