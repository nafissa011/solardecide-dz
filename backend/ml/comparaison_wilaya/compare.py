"""
routes/compare.py
Endpoint /api/compare  — utilise les scores pré-calculés du modèle Hybrid_Ridge_MLP
─────────────────────────────────────────────────────────────────────────────────────
Source des scores : wilaya_ranking_final.csv  (colonne score_Hybrid_Ridge_MLP)
Modèle de référence : Hybrid_Ridge_MLP
  RMSE = 18.7937  |  MAE = 11.0921  |  R² = 0.6363  |  MAPE = 43.16%
  Entraîné sur 2019-2022, testé sur 2023 (split temporel strict)
"""

from flask import Blueprint, request, jsonify, Response
from pathlib import Path
import pandas as pd

bp = Blueprint("compare", __name__)

CHECKPOINT_DIR = Path(__file__).resolve().parent
CSV_FILENAME   = "wilaya_ranking_final.csv"

MODEL_METRICS = {
    "RMSE": 18.7937,
    "MAE":  11.0921,
    "R2":   0.6363,
    "MAPE": 43.16,
}

_df_cache = None


def _load_df():
    """Lazy-loads the CSV once and caches it for the process lifetime."""
    global _df_cache
    if _df_cache is not None:
        return _df_cache

    csv_path = CHECKPOINT_DIR / CSV_FILENAME
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {csv_path}\n"
            f"Contenu de {CHECKPOINT_DIR} : "
            f"{[f.name for f in CHECKPOINT_DIR.iterdir()] if CHECKPOINT_DIR.exists() else 'dossier absent'}"
        )

    df = pd.read_csv(csv_path)
    df["wilaya_name"] = df["wilaya_name"].astype(str).str.strip()
    _df_cache = df
    return _df_cache


def _cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


@bp.after_request
def after_request(response):
    return _cors(response)


@bp.route("/compare", methods=["GET", "OPTIONS"])
def compare_wilayas():
    if request.method == "OPTIONS":
        return _cors(Response(status=204))

    params  = request.args
    wilayas = [params.get(f"w{i}", "").strip() for i in [1, 2, 3]]
    wilayas = [w for w in wilayas if w]

    if len(wilayas) < 2:
        return jsonify({"error": "Fournir au moins w1 et w2 (ex: ?w1=Adrar&w2=Annaba)"}), 400

    if len(set(w.lower() for w in wilayas)) != len(wilayas):
        return jsonify({"error": "Les wilayas doivent être différentes"}), 400

    try:
        df = _load_df()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Erreur chargement données : {e}"}), 500

    results   = []
    not_found = []

    for wilaya in wilayas:
        mask = df["wilaya_name"].str.lower() == wilaya.lower()
        row  = df[mask]

        if row.empty:
            not_found.append(wilaya)
            continue

        r = row.iloc[0]

        # Fallback to last rank if column missing (e.g. older CSV version)
        rang = int(r["rang_Hybrid_Ridge_MLP"]) if "rang_Hybrid_Ridge_MLP" in r.index else 58

        # Climate zones derived from national ranking thresholds (notebook §4.2)
        if rang <= 15:
            zone = "Saharien"
        elif rang <= 30:
            zone = "Semi-aride"
        elif rang <= 45:
            zone = "Méditerranéen"
        else:
            zone = "Humide"

        score_val = float(r["score_Hybrid_Ridge_MLP"])

        results.append({
            "wilaya":      str(r["wilaya_name"]),
            "solar_score": round(score_val, 4),
            "details": {
                "rang_national": rang,
                "zone":          zone,
            }
        })

    if not results:
        return jsonify({"error": "Aucune wilaya trouvée", "not_found": not_found}), 404

    results.sort(key=lambda x: x["solar_score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return jsonify({
        "model":   "Hybrid_Ridge_MLP",
        "results": results,
        "best":    results[0]["wilaya"],
        "metrics": {
            "rmse": MODEL_METRICS["RMSE"],
            "mae":  MODEL_METRICS["MAE"],
            "r2":   MODEL_METRICS["R2"],
            "mape": MODEL_METRICS["MAPE"],
            "note": "Métriques évaluées sur test 2023 (split temporel strict)",
        },
        "not_found": not_found,
    })


@bp.route("/compare/wilayas-list", methods=["GET", "OPTIONS"])
def wilayas_list():
    if request.method == "OPTIONS":
        return _cors(Response(status=204))
    try:
        df    = _load_df()
        names = sorted(df["wilaya_name"].tolist())
        return jsonify({"wilayas": names, "count": len(names)})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Erreur : {e}"}), 500