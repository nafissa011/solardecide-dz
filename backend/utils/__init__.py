"""
SolarDZ — Utilitaires : scoring, ROI, décision, métriques
"""

import numpy as np
import pandas as pd
from config import SCORE_WEIGHTS, ROI_SCENARIOS

# ─────────────────────────────────────────────────────────────────────────────
#  Métriques
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    yt, yp = y_true[mask], y_pred[mask]
    mae  = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    nz = yt != 0
    mape = float(np.mean(np.abs((yt[nz] - yp[nz]) / yt[nz])) * 100) if nz.any() else 0.0
    sst = float(np.sum((yt - yt.mean()) ** 2))
    r2 = float(1 - np.sum((yt - yp) ** 2) / sst) if sst > 0 else float("nan")
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 2), "r2": round(r2, 4)}


# ─────────────────────────────────────────────────────────────────────────────
#  Scoring
# ─────────────────────────────────────────────────────────────────────────────

def _norm01(arr: np.ndarray) -> np.ndarray:
    mn, mx = arr.min(), arr.max()
    return (arr - mn) / (mx - mn + 1e-9)


def compute_wilaya_score(row: dict) -> dict:
    """
    Score composite (0-100) identique au notebook.
    row doit contenir : mean_ghi, peak_ghi, sunshine_frac, mean_clearness, variability
    Note : la normalisation cross-wilaya est faite dans DataEngine ; ici on suppose
    que les valeurs sont déjà normalisées (s_*).
    """
    s = (
        row.get("s_mean_ghi", 0)        * SCORE_WEIGHTS["mean_ghi"]        +
        row.get("s_peak_ghi", 0)        * SCORE_WEIGHTS["peak_ghi"]        +
        row.get("s_sunshine_hours", 0)  * SCORE_WEIGHTS["sunshine_hours"]  +
        row.get("s_clearness", 0)       * SCORE_WEIGHTS["clearness"]       +
        row.get("s_low_variability", 0) * SCORE_WEIGHTS["low_variability"]
    ) * 100
    return {"score": round(s, 1)}


# ─────────────────────────────────────────────────────────────────────────────
#  ROI Calculator
# ─────────────────────────────────────────────────────────────────────────────

def compute_roi(capacity_mw: float, mean_ghi: float, scenario: str = "base") -> dict:
    """
    Calcule NPV, IRR, LCOE, payback et cashflows sur 25 ans.
    mean_ghi : GHI moyen annuel (kWh/m²/jour)
    """
    s = ROI_SCENARIOS.get(scenario, ROI_SCENARIOS["base"])

    capex = capacity_mw * s["capex_per_mw"]
    # mean_ghi est en kWh/m²/h (moyenne horaire).
    # GHI annuel = mean_ghi × 8760 h/an  →  ex: 0.735 × 8760 ≈ 6,438 kWh/m²/an
    # Production (MWh) = MW × GHI_annuel × PR  (spec yield simplifié, PR=0.85)
    ghi_annual_kwh_m2 = mean_ghi * 8760
    annual_gen_mwh = capacity_mw * ghi_annual_kwh_m2 * 0.85  # MWh/an
    annual_revenue = annual_gen_mwh * s["tariff_usd_kwh"] * 1000
    annual_opex = capacity_mw * s["opex_per_mw_yr"]

    # Cashflows 25 ans
    cashflows = []
    cumulative = -capex
    payback_year = None
    for yr in range(1, 26):
        gen = annual_gen_mwh * (1 - s["degradation_pct"] / 100) ** (yr - 1)
        revenue = gen * s["tariff_usd_kwh"] * 1000
        ncf = revenue - annual_opex
        cumulative += ncf
        if payback_year is None and cumulative >= 0:
            payback_year = yr
        cashflows.append({
            "year": yr,
            "revenue": round(revenue),
            "opex": round(annual_opex),
            "ncf": round(ncf),
            "cumulative": round(cumulative),
        })

    # NPV
    r = s["discount_rate"]
    npv = -capex + sum(
        cf["ncf"] / (1 + r) ** cf["year"] for cf in cashflows
    )

    # IRR (Newton simple)
    def _irr(cfs):
        rate = 0.10
        for _ in range(100):
            npv_val = sum(c / (1 + rate) ** i for i, c in enumerate(cfs))
            dnpv = sum(-i * c / (1 + rate) ** (i + 1) for i, c in enumerate(cfs))
            if abs(dnpv) < 1e-10:
                break
            rate -= npv_val / dnpv
        return max(0, rate)

    cf_series = [-capex] + [cf["ncf"] for cf in cashflows]
    irr = round(_irr(cf_series) * 100, 1)

    return {
        "scenario": s,
        "capex": round(capex),
        "npv": round(npv),
        "irr": irr,
        "payback_years": payback_year or 25,
        "lcoe_usd_kwh": s["lcoe"],
        "annual_generation_mwh": round(annual_gen_mwh),
        "annual_revenue_usd": round(annual_revenue),
        "cashflows": cashflows,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Decision Engine
# ─────────────────────────────────────────────────────────────────────────────

_ACTIONS = {
    "build": [
        {"title": "Lancer étude de faisabilité détaillée",
         "desc": "Mandater un bureau d'études pour PVsyst et analyse géotechnique",
         "priority": "haute", "timeline": "2-3 mois", "cost": "80-120K USD"},
        {"title": "Déposer demande d'autorisation foncière",
         "desc": "Auprès de la Direction des Domaines et du Ministère de l'Énergie",
         "priority": "haute", "timeline": "3-6 mois", "cost": "15-25K USD"},
        {"title": "Préparer dossier financement",
         "desc": "Business plan + modèle financier pour banques ou investisseurs",
         "priority": "haute", "timeline": "1-2 mois", "cost": "40-60K USD"},
        {"title": "Connecter au réseau HTB",
         "desc": "Négocier accord de raccordement avec Sonelgaz",
         "priority": "moyenne", "timeline": "6-12 mois", "cost": "Variable"},
    ],
    "study": [
        {"title": "Étude d'impact sécheresse et ensablement",
         "desc": "Analyse historique vents + mesures terrain sur 12 mois min.",
         "priority": "haute", "timeline": "6-12 mois", "cost": "50-80K USD"},
        {"title": "Évaluation foncière approfondie",
         "desc": "Statut juridique terrain, propriétaires, contraintes",
         "priority": "haute", "timeline": "3-6 mois", "cost": "20-35K USD"},
        {"title": "Analyse infrastructure d'accès",
         "desc": "Routes, eau, télécoms, logement personnel",
         "priority": "moyenne", "timeline": "2-4 mois", "cost": "15-25K USD"},
    ],
    "wait": [
        {"title": "Surveiller développement infrastructure réseau",
         "desc": "Suivre programme HTB Sonelgaz pour cette région",
         "priority": "basse", "timeline": "Continu", "cost": "Minimal"},
        {"title": "Actualiser analyse dans 18 mois",
         "desc": "Réévaluer quand contexte réglementaire évolue",
         "priority": "basse", "timeline": "18 mois", "cost": "Minimal"},
    ],
}


def get_verdict(zone: dict) -> tuple[str, float, list]:
    """
    Retourne (verdict, confidence, actions).
    verdict : 'build' | 'study' | 'wait'

    Logique :
      score >= 80 AND grid_dist < 300km AND risk_sand != 'high' → 'build'
      score >= 65 OR (score >= 55 AND grid_dist < 500km)        → 'study'
      sinon                                                       → 'wait'
    """
    score = float(zone.get("score", 0))
    grid_dist = float(zone.get("grid_dist_km", 500))
    risk_sand = zone.get("risk_sand", "medium")

    if score >= 80 and grid_dist < 300 and risk_sand != "high":
        verdict, conf = "build", min(0.60 + (score - 80) / 100, 0.95)
    elif score >= 65 or (score >= 55 and grid_dist < 500):
        verdict, conf = "study", 0.70 + (score - 55) / 200
    else:
        verdict, conf = "wait", max(0.50, 0.80 - (65 - score) / 100)

    return verdict, round(conf, 2), _ACTIONS.get(verdict, _ACTIONS["study"])


def build_risks(zone: dict) -> list[dict]:
    grid_dist = float(zone.get("grid_dist_km", 500))
    risk_sand = zone.get("risk_sand", "medium")
    return [
        {"type": "Technique", "level": risk_sand,
         "detail": f"Risque d'ensablement : {risk_sand}"},
        {"type": "Réseau", "level": "high" if grid_dist > 300 else "medium",
         "detail": f"Distance réseau HTB : {int(grid_dist)} km"},
        {"type": "Financement", "level": "medium", "detail": "Accès crédit projet"},
        {"type": "Réglementaire", "level": "low",  "detail": "Contexte DZ favorable (loi EnR 2024)"},
    ]
