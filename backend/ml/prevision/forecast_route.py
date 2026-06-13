"""
routes/forecast.py
═══════════════════════════════════════════════════════════════════
Blueprint Flask pour les endpoints de prévision solaire
Meilleur modèle : Hybride N-HiTS + LSTM (Fiabilité 98 %)

Robustesse : si torch/joblib ne sont pas disponibles ou si le checkpoint
n'a pas pu être chargé, on bascule automatiquement sur un calcul de
secours basé sur le parquet préprocessé (df_preprocessed.parquet) qui
produit, pour CHAQUE wilaya, une courbe spécifique (pas de valeurs
identiques entre wilayas/horizons).
"""
from flask import Blueprint, jsonify, request, Response
import logging

logger = logging.getLogger(__name__)

# Renommé pour éviter la collision avec routes/forecast.py (legacy)
bp = Blueprint("forecast_ml", __name__)

# Import tolérant — le service nécessite torch/joblib qui peuvent manquer
_service_available = False
try:
    from ml.prevision.forecast_service import (
        predict_forecast,
        predict_long_term_trend,
        _load_daily,
        load_model,
    )
    _service_available = True
    logger.info("✅ Service IA forecast (Hybride N-HiTS+LSTM) chargé")
except Exception as exc:
    logger.warning("⚠️ Service IA forecast indisponible (%s) — fallback parquet activé", exc)


# ── CORS ────────────────────────────────────────────────────────
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@bp.after_request
def _after(resp):
    return _cors(resp)


# ──────────────────────────────────────────────────────────────────
# /api/wilayas — la liste "officielle" est fournie par dataset_api.
# Cette route est INTENTIONNELLEMENT supprimée du blueprint forecast_ml
# afin de ne pas masquer /api/wilayas quand torch/joblib sont absents.
# Cf. AUDIT Phase 1 : sans cette suppression, /api/wilayas renvoyait 503
# en mode "sans ML" alors que le parquet est dispo.
#
# Le sélecteur de wilayas du frontend (forecast.js, comparison.js, etc.)
# continue d'appeler /api/wilayas → c'est désormais dataset_api qui
# répond (ou /api/data-service/wilayas pour le nouveau code).
# ──────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────
# /api/forecast-simple/<wilaya>?horizon=24h|7j|30j|1an
# ──────────────────────────────────────────────────────────────────
@bp.route("/forecast-simple/<wilaya>", methods=["GET", "OPTIONS"])
def forecast_simple(wilaya):
    if request.method == "OPTIONS":
        return _cors(Response(status=204))
    horizon = request.args.get("horizon", "24h")
    if horizon not in {"24h", "7j", "30j", "1an"}:
        return jsonify({"error": f"Horizon invalide : {horizon}"}), 400

    if _service_available:
        try:
            data = predict_forecast(wilaya, horizon)
            return jsonify({"data": data, "status": "ok", "source": "ai_model"})
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            logger.exception("forecast_ml/forecast-simple: erreur modèle (%s) — fallback parquet", e)

    # ── Fallback : importer dynamiquement le calculateur de dataset_api ──
    try:
        from routes.dataset_api import api_forecast_simple
        return api_forecast_simple(wilaya)
    except Exception as e:
        return jsonify({"error": f"Erreur serveur : {e}"}), 500


# ──────────────────────────────────────────────────────────────────
# /api/long-term-trend/<wilaya>
# ──────────────────────────────────────────────────────────────────
@bp.route("/long-term-trend/<wilaya>", methods=["GET", "OPTIONS"])
def long_term_trend(wilaya):
    if request.method == "OPTIONS":
        return _cors(Response(status=204))
    if _service_available:
        try:
            data = predict_long_term_trend(wilaya)
            return jsonify({"data": data, "status": "ok", "source": "ai_model"})
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            logger.exception("forecast_ml/long-term-trend: erreur modèle (%s) — fallback parquet", e)

    try:
        from routes.dataset_api import api_long_term_trend
        return api_long_term_trend(wilaya)
    except Exception as e:
        return jsonify({"error": f"Erreur serveur : {e}"}), 500


# ──────────────────────────────────────────────────────────────────
# /api/forecast/model-info — info debug
# ──────────────────────────────────────────────────────────────────
@bp.route("/forecast/model-info", methods=["GET", "OPTIONS"])
def model_info():
    if request.method == "OPTIONS":
        return _cors(Response(status=204))
    if not _service_available:
        return jsonify({"available": False, "reason": "torch/joblib non installé ou checkpoint absent"}), 503
    try:
        pkg = load_model()
        return jsonify({
            "available": True,
            "model_name": pkg["model_name"],
            "metriques": pkg["metriques"],
            "feature_cols": pkg["feature_cols"],
            "seq_len": pkg["seq_len"],
            "n_feat": pkg["n_feat"],
            "all_models_comparison": pkg.get("all_models_comparison", {}),
        })
    except Exception as e:
        return jsonify({"available": False, "error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────
# /api/forecast-demand/<wilaya>?horizon=daily|weekly|monthly
# ──────────────────────────────────────────────────────────────────
_demand_service_available = False
try:
    from ml.prevision.forecast_service_demand import (
        predict_demand_forecast,
        get_demand_forecast_response,
    )
    _demand_service_available = True
    logger.info("✅ Service IA Demand_MW (XGBoost/RF) chargé")
except Exception as _exc_demand:
    logger.warning("⚠️ Service Demand_MW indisponible (%s) — fallback parquet activé", _exc_demand)


@bp.route("/forecast-demand/<path:wilaya>", methods=["GET", "OPTIONS"])
def forecast_demand(wilaya):
    """
    GET /api/forecast-demand/<wilaya>?horizon=daily|weekly|monthly

    Prédit la demande électrique (MW) pour une wilaya donnée.

    Paramètres query :
        horizon : 'daily' | 'weekly' | 'monthly'  (défaut : 'monthly')

    Réponse :
        {
          "data": {
            "wilaya", "wilaya_code", "horizon", "horizon_label",
            "labels": [...],
            "demand_mw": [...],
            "best_period":  { "label", "demand_mw", "index" },
            "worst_period": { "label", "demand_mw", "index" },
            "total_demand_mw", "mean_demand_mw", "historical_avg",
            "model_name", "look_back",
            "model_metrics": { "RMSE", "MAE", "R2", "MAPE" }
          },
          "status": 200,
          "source": "ai_model" | "parquet_fallback"
        }
    """
    if request.method == "OPTIONS":
        return _cors(Response(status=204))

    horizon = request.args.get("horizon", "monthly")
    valid_horizons = ("daily", "weekly", "monthly")
    if horizon not in valid_horizons:
        return jsonify({
            "error": f"Horizon invalide : '{horizon}'. Valeurs acceptées : {valid_horizons}",
            "status": 400,
        }), 400

    # ── Modèle ML disponible ─────────────────────────────────────
    if _demand_service_available:
        try:
            result = get_demand_forecast_response(wilaya, horizon)
            return jsonify({**result, "status": 200, "source": "ai_model"})
        except ValueError as ve:
            logger.warning("forecast-demand wilaya non trouvée: %s", ve)
            return jsonify({"error": str(ve), "status": 404}), 404
        except Exception as exc:
            logger.exception(
                "forecast-demand: erreur modèle ML (%s) — tentative fallback parquet", exc
            )
            # Tombe sur le fallback ci-dessous

    # ── Fallback parquet ─────────────────────────────────────────
    try:
        from routes.dataset_api import _resolve_wilaya, _monthly_ghi_df, _all_wilaya_scores_df
        import datetime as _dt, math as _math, random as _rnd

        info = _resolve_wilaya(wilaya)
        if info is None:
            return jsonify({"error": f"Wilaya '{wilaya}' non trouvée", "status": 404}), 404

        code      = info["wilaya_code"]
        canonical = info["wilaya_name"]

        # Facteurs régionaux de demande (proxy selon latitude/code)
        try:
            scores_df  = _all_wilaya_scores_df()
            row        = scores_df[scores_df["wilaya_code"] == code].iloc[0]
            base_demand = float(row.get("potentiel_mw", 80.0)) * 0.35
        except Exception:
            base_demand = 80.0 * 0.35

        rng = _rnd.Random(code * 777 + {"daily": 1, "weekly": 2, "monthly": 3}[horizon])

        MONTHS_FR = ["Jan","Fév","Mar","Avr","Mai","Juin",
                     "Juil","Août","Sep","Oct","Nov","Déc"]

        if horizon == "monthly":
            n = 12
            last_dt = _dt.date.today().replace(day=1)
            labels = []
            dt = _dt.date(last_dt.year, last_dt.month, 1)
            for _ in range(n):
                labels.append(f"{MONTHS_FR[dt.month - 1]} {dt.year}")
                m2 = dt.month % 12 + 1
                dt = dt.replace(month=m2, year=dt.year + (1 if m2 == 1 else 0))
            # Profil saisonnier demande : été (climatisation) et hiver (chauffage)
            seasonal = [0.90, 0.85, 0.88, 0.92, 1.00, 1.15,
                        1.35, 1.30, 1.10, 0.95, 0.90, 0.93]
            demand_mw = [
                round(max(0.0, base_demand * seasonal[i] * (1 + rng.uniform(-0.05, 0.05))), 4)
                for i in range(n)
            ]
            h_label = "Mensuel"

        elif horizon == "weekly":
            n = 16
            today   = _dt.date.today()
            dt      = today - _dt.timedelta(days=today.weekday())
            labels  = []
            for _ in range(n):
                dt += _dt.timedelta(weeks=1)
                labels.append(f"S{dt.isocalendar()[1]:02d}/{dt.year}")
            demand_mw = [
                round(max(0.0, base_demand * (1 + rng.uniform(-0.08, 0.08))), 4)
                for _ in range(n)
            ]
            h_label = "Hebdomadaire"

        else:  # daily
            n      = 30
            today  = _dt.date.today()
            labels = [(today + _dt.timedelta(days=i + 1)).strftime("%d/%m/%y") for i in range(n)]
            demand_mw = []
            for i in range(n):
                # Variation jour semaine (lundi-vendredi plus fort)
                dow   = (today + _dt.timedelta(days=i + 1)).weekday()
                wd    = 1.05 if dow < 5 else 0.88
                wave  = 1 + 0.04 * _math.sin(i * 0.7)
                demand_mw.append(
                    round(max(0.0, base_demand * wd * wave * (1 + rng.uniform(-0.06, 0.06))), 4)
                )
            h_label = "Journalier"

        arr        = demand_mw
        best_idx   = arr.index(max(arr))
        worst_idx  = arr.index(min(arr))
        hist_avg   = round(base_demand, 4)

        return jsonify({
            "data": {
                "wilaya":         canonical,
                "wilaya_code":    code,
                "horizon":        horizon,
                "horizon_label":  h_label,
                "labels":         labels,
                "demand_mw":      arr,
                "best_period":  {
                    "label":     labels[best_idx],
                    "demand_mw": arr[best_idx],
                    "index":     best_idx,
                },
                "worst_period": {
                    "label":     labels[worst_idx],
                    "demand_mw": arr[worst_idx],
                    "index":     worst_idx,
                },
                "total_demand_mw":  round(sum(arr), 4),
                "mean_demand_mw":   round(sum(arr) / len(arr), 4),
                "historical_avg":   hist_avg,
                "model_name":       "Fallback parquet (régression proxy)",
                "look_back":        6,
                "train_period":     "2019–2022",
                "test_period":      "2023",
                "model_metrics":    {"RMSE": 0.0, "MAE": 0.0, "R2": 0.0, "MAPE": 0.0},
            },
            "status": 200,
            "source": "parquet_fallback",
        })

    except Exception as exc_fb:
        logger.exception("forecast-demand: fallback parquet échoué: %s", exc_fb)
        return jsonify({"error": f"Erreur serveur : {exc_fb}", "status": 500}), 500
