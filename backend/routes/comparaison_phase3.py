"""
Endpoint pour la page Comparaison.

Combine :
  • les scores ML pré-calculés (ml/comparaison_wilaya/compare.py — modèle
    Hybrid_Ridge_MLP) — l'ordre / le « best » viennent du modèle, intact.
  • les vraies features par wilaya issues du parquet via data_service :
    GHI_annuel, DNI_moyen, KT, T2M, WS10M, score_composite (réel).
  • la normalisation min/max nationale pour le radar (0-100 garanti).
  • un résumé textuel généré dynamiquement.
  • un export PDF (WeasyPrint → fallback ReportLab), plan-gated Pro+.

Routes
──────
  POST /api/comparaison
       body : { "wilayas": ["Adrar","Alger","Annaba"] }
       resp : 200 OK, payload détaillé (voir _build_payload).

  POST /api/comparaison/pdf
       body : { "wilayas": ["Adrar","Alger","Annaba"] }
       resp : 200 application/pdf  OU  401/402 selon plan.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import pandas as pd
from flask import Blueprint, Response, jsonify, request

from utils.data_service import (
    _q,
    _resolve_wilaya,
    _wilaya_agg_df,
    get_wilaya_stats,
    list_wilayas,
)

logger = logging.getLogger(__name__)
bp = Blueprint("comparaison_phase3", __name__)


# ─────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────
def _ml_score_for(name: str) -> Optional[dict]:
    """Lookup the ML Hybrid_Ridge_MLP score for a wilaya from compare.py's CSV."""
    try:
        from ml.comparaison_wilaya.compare import _load_df  # type: ignore
        df = _load_df()
        m = df["wilaya_name"].str.lower() == name.lower()
        row = df[m]
        if row.empty:
            return None
        r = row.iloc[0]
        rang = int(r.get("rang_Hybrid_Ridge_MLP", 58))
        if rang <= 15:
            zone = "Saharien"
        elif rang <= 30:
            zone = "Semi-aride"
        elif rang <= 45:
            zone = "Méditerranéen"
        else:
            zone = "Humide"
        return {
            "wilaya":      str(r["wilaya_name"]),
            "solar_score": round(float(r["score_Hybrid_Ridge_MLP"]), 4),
            "rang_ml":     rang,
            "zone":        zone,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML score lookup failed for %s: %s", name, exc)
        return None


def _national_extremes() -> dict:
    """Return min/max for the normalisation axes across the 58 wilayas."""
    df = _wilaya_agg_df()
    axes = {
        "ghi":         ("ghi_annuel_kwh_m2", float(df["ghi_annuel_kwh_m2"].max())),
        "dni":         ("dni_mean",          float(df["dni_mean"].max())),
        "kt":          ("kt_mean",           float(df["kt_mean"].max())),
        "t2m":         ("t2m_mean",          float(df["t2m_mean"].max())),
        "ws10m":       ("ws10m_mean",        float(df["ws10m_mean"].max())),
        "score":       ("score_composite",   float(df["score_composite"].max())),
        # "stabilite" is computed dynamically per-wilaya via the daily CV — we
        # store the national MAX of the daily-stability % to normalise.
        "stabilite":   ("stabilite_pct_daily", 100.0),
    }
    return axes


# ------------------------------------------------------------------
# Daily-CV stability — same approach as the Zone Analysis page :
#  CV  = std(daily_GHI) / mean(daily_GHI)
#  pct = max(0, min(100, (1 − CV) × 100))   → always within [0, 100]
# ------------------------------------------------------------------
def _daily_stability_pct(wilaya_name: str) -> float:
    canon = _resolve_wilaya(wilaya_name)
    if canon is None:
        return 0.0
    sql = """
    SELECT AVG(daily_ghi) AS mean_d, STDDEV(daily_ghi) AS std_d
    FROM (
      SELECT DATE(datetime) AS d, SUM(GHI) AS daily_ghi
      FROM solar WHERE wilaya_name = ?
      GROUP BY DATE(datetime)
    )
    """
    df = _q(sql, [canon])
    if df.empty:
        return 0.0
    m = float(df.iloc[0]["mean_d"] or 0.0)
    s = float(df.iloc[0]["std_d"]  or 0.0)
    cv = (s / m) if m else 0.0
    return round(max(0.0, min(100.0, (1.0 - cv) * 100.0)), 2)


def _normalize(value: float, ref_max: float) -> float:
    """Return value/ref_max * 100, clipped to [0, 100]."""
    if not ref_max:
        return 0.0
    return max(0.0, min(100.0, (float(value) / float(ref_max)) * 100.0))


def _build_summary(payload: list[dict]) -> str:
    """Generate the human-readable summary in French."""
    if not payload:
        return ""
    best_ghi  = max(payload, key=lambda x: x["features"]["ghi_annuel"])
    best_stab = max(payload, key=lambda x: x["features"]["stabilite_pct"])
    # national avg GHI from data_service
    nat_avg_ghi = float(_wilaya_agg_df()["ghi_annuel_kwh_m2"].mean())
    delta = ((best_ghi["features"]["ghi_annuel"] - nat_avg_ghi) / nat_avg_ghi) * 100.0
    return (
        f"{best_ghi['wilaya']} présente le meilleur GHI avec "
        f"{best_ghi['features']['ghi_annuel']:.2f} kWh/m²/an, soit "
        f"{delta:+.1f}% par rapport à la moyenne nationale ({nat_avg_ghi:.2f} kWh/m²/an). "
        f"{best_stab['wilaya']} offre la meilleure stabilité climatique "
        f"({best_stab['features']['stabilite_pct']:.1f}%). "
        f"Recommandation : {best_ghi['wilaya']} pour maximiser la production annuelle."
    )


def _build_payload(wilayas: list[str]) -> dict:
    """Build the full Phase 3 comparison payload."""
    extremes = _national_extremes()

    items = []
    not_found = []
    for w in wilayas:
        stats = get_wilaya_stats(w)
        if stats is None:
            not_found.append(w)
            continue

        ml = _ml_score_for(stats["wilaya_name"]) or {}

        # Stabilité en %  — CV journalier (même logique que zone-analysis)
        stab_pct = _daily_stability_pct(stats["wilaya_name"])

        features = {
            "ghi_annuel":       float(stats.get("ghi_annuel_kwh_m2") or 0.0),
            "dni_moyen":        float(stats.get("dni_moyen")        or 0.0),
            "kt_moyen":         float(stats.get("clearness_kt_moyen") or 0.0),
            "t2m_moyen":        float(stats.get("t2m_moyen")        or 0.0),
            "ws10m_moyen":      float(stats.get("vent_moyen_m_s")   or 0.0),
            "score_composite":  float(stats.get("score_composite")  or 0.0),
            "stabilite_pct":    round(stab_pct, 2),
        }
        # Radar normalisé 0-100 sur max national  (chaque axe ∈ [0, 100])
        radar = {
            "ghi":       round(_normalize(features["ghi_annuel"],     extremes["ghi"][1]),       2),
            "dni":       round(_normalize(features["dni_moyen"],      extremes["dni"][1]),       2),
            "kt":        round(_normalize(features["kt_moyen"],       extremes["kt"][1]),        2),
            "ws10m":     round(_normalize(features["ws10m_moyen"],    extremes["ws10m"][1]),     2),
            "score":     round(_normalize(features["score_composite"],extremes["score"][1]),     2),
            "stabilite": round(stab_pct, 2),  # already 0-100
        }

        items.append({
            "wilaya":           stats["wilaya_name"],
            "wilaya_code":      stats.get("wilaya_code"),
            "climate":          stats.get("climate"),
            "climate_label":    stats.get("climate_label"),
            "rang_national":    stats.get("rang_national"),
            "potentiel_mw":     stats.get("potentiel_mw"),
            "n_communes":       stats.get("n_communes"),
            "features":         features,
            "radar_normalised": radar,
            # Hybrid_Ridge_MLP output (legacy compatible)
            "ml": {
                "solar_score": ml.get("solar_score"),
                "rang_ml":     ml.get("rang_ml"),
                "zone":        ml.get("zone"),
            },
        })

    if not items:
        return {"error": "Aucune wilaya trouvée", "not_found": not_found, "status": 404}

    # Sort by ml.solar_score (fallback features.score_composite) — the ML model is the reference
    items.sort(
        key=lambda x: (x["ml"]["solar_score"] if x["ml"].get("solar_score") is not None
                       else x["features"]["score_composite"]),
        reverse=True,
    )
    for i, it in enumerate(items, 1):
        it["rank"] = i

    summary_txt = _build_summary(items)

    return {
        "wilayas":     items,
        "best":        items[0]["wilaya"],
        "summary":     summary_txt,
        "axes_max":    {k: v[1] for k, v in extremes.items()},
        "model":       "Hybrid_Ridge_MLP",
        "model_metrics": {
            "rmse": 18.79, "mae": 11.09, "r2": 0.6363, "mape": 43.16,
            "note": "Métriques évaluées sur test 2023 (split temporel strict)",
        },
        "not_found":   not_found,
        "source":      "data_service + ml.comparaison_wilaya",
        "status":      200,
    }


# ─────────────────────────────────────────────────────────────────────────
#  POST /api/comparaison
# ─────────────────────────────────────────────────────────────────────────
@bp.post("/comparaison")
def api_comparaison():
    """Plan-gated to Pro+ for the full comparison."""
    from services.plan_service import check_plan

    @check_plan("pro", feature="action.comparaison")
    def _gated():
        body = request.get_json(silent=True) or {}
        wilayas = body.get("wilayas") or []
        # Also accept w1/w2/w3 keys for compatibility with the legacy /api/compare
        if not wilayas:
            wilayas = [body.get(k) for k in ("w1","w2","w3") if body.get(k)]
        wilayas = [w for w in wilayas if isinstance(w, str) and w.strip()]

        if len(wilayas) < 2:
            return jsonify({"error": "Sélectionnez au moins 2 wilayas", "status": 400}), 400
        if len(wilayas) > 3:
            return jsonify({"error": "Maximum 3 wilayas", "status": 400}), 400
        if len(set(w.lower() for w in wilayas)) != len(wilayas):
            return jsonify({"error": "Wilayas doivent être différentes", "status": 400}), 400

        payload = _build_payload(wilayas)
        # Phase 3 — admin activity log
        try:
            from services.admin_service import log_activity
            from services.plan_service import get_current_user
            u = get_current_user()
            details = f"wilaya:{wilayas[0]} " + ",".join(wilayas[1:])
            log_activity("rapport" if False else "comparaison",
                         user_id=(u.id if u else None),
                         details=details)
        except Exception:  # noqa: BLE001
            pass
        return jsonify({"data": payload, **{k: v for k, v in payload.items() if k == "status"}}), payload.get("status", 200)

    return _gated()


# ─────────────────────────────────────────────────────────────────────────
#  POST /api/comparaison/pdf
# ─────────────────────────────────────────────────────────────────────────
@bp.post("/comparaison/pdf")
def api_comparaison_pdf():
    """Export PDF — Plan Pro+ via @check_plan('pro', feature='action.export_comparison_pdf')."""
    from services.plan_service import check_plan

    @check_plan("pro", feature="action.export_comparison_pdf")
    def _gated():
        body = request.get_json(silent=True) or {}
        wilayas = body.get("wilayas") or []
        wilayas = [w for w in wilayas if isinstance(w, str) and w.strip()]
        if len(wilayas) < 2:
            return jsonify({"error": "Sélectionnez au moins 2 wilayas", "status": 400}), 400

        payload = _build_payload(wilayas)
        if payload.get("status") and payload["status"] != 200:
            return jsonify(payload), payload["status"]

        pdf_bytes = _render_pdf(payload)
        if pdf_bytes is None:
            return jsonify({"error": "PDF generation unavailable", "status": 500}), 500

        names = "_".join(w["wilaya"].replace(" ","-") for w in payload["wilayas"])[:80]
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="comparaison_{names}.pdf"',
                "Cache-Control": "no-store",
            },
        )

    return _gated()


# ─────────────────────────────────────────────────────────────────────────
#  PDF renderer (WeasyPrint → ReportLab fallback)
# ─────────────────────────────────────────────────────────────────────────
def _render_pdf(payload: dict) -> Optional[bytes]:
    try:
        return _render_with_weasyprint(payload)
    except Exception as exc:  # noqa: BLE001
        logger.info("WeasyPrint unavailable (%s) — falling back to ReportLab", exc)
        try:
            return _render_with_reportlab(payload)
        except Exception as exc2:  # noqa: BLE001
            logger.exception("PDF generation failed completely: %s", exc2)
            return None


def _render_with_weasyprint(payload: dict) -> bytes:
    from weasyprint import HTML  # noqa: WPS433

    rows = ""
    for w in payload["wilayas"]:
        f = w["features"]
        rows += (
            f"<tr><td>{w['rank']}</td><td><strong>{w['wilaya']}</strong></td>"
            f"<td>{w.get('climate_label') or w.get('climate') or ''}</td>"
            f"<td>{f['ghi_annuel']:.2f}</td>"
            f"<td>{f['dni_moyen']:.3f}</td>"
            f"<td>{f['kt_moyen']:.3f}</td>"
            f"<td>{f['t2m_moyen']:.1f}</td>"
            f"<td>{f['ws10m_moyen']:.2f}</td>"
            f"<td>{f['stabilite_pct']:.1f}%</td>"
            f"<td>{f['score_composite']:.1f}</td>"
            f"<td>{w['ml'].get('solar_score') or '—'}</td>"
            "</tr>"
        )
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><style>
      body{{font-family: 'DejaVu Sans', Arial, sans-serif; padding: 24px; color:#1e293b}}
      h1{{color:#f59e0b; margin:0 0 4px}}
      h2{{color:#3b82f6; font-size:14px; margin-top:24px}}
      table{{width:100%; border-collapse:collapse; margin-top:12px; font-size:11px}}
      th,td{{border:1px solid #e2e8f0; padding:6px 8px; text-align:left}}
      th{{background:#f1f5f9; color:#0f172a}}
      .summary{{background:#fef3c7; border-left:4px solid #f59e0b; padding:12px 14px; margin-top:20px; border-radius:4px; font-size:12px; line-height:1.55}}
      .best{{background:#d1fae5;}}
      .meta{{color:#64748b; font-size:10px; margin-top:30px}}
    </style></head><body>
      <h1>SolarDecide DZ — Rapport de comparaison</h1>
      <p>Wilaya gagnante : <strong>{payload['best']}</strong> &nbsp;|&nbsp; Modèle : {payload['model']}</p>
      <h2>Tableau comparatif</h2>
      <table>
        <thead><tr>
          <th>#</th><th>Wilaya</th><th>Climat</th><th>GHI (kWh/m²/an)</th><th>DNI</th><th>KT</th>
          <th>T (°C)</th><th>Vent (m/s)</th><th>Stab.</th><th>Score comp.</th><th>Score ML</th>
        </tr></thead><tbody>{rows}</tbody>
      </table>
      <h2>Résumé</h2>
      <div class='summary'>{payload['summary']}</div>
      <div class='meta'>Source : NASA POWER (2019–2023) via data_service · Modèle : {payload['model']} (R² = {payload['model_metrics']['r2']})</div>
    </body></html>"""
    return HTML(string=html).write_pdf()


def _render_with_reportlab(payload: dict) -> bytes:
    from reportlab.lib.pagesizes import A4  # noqa: WPS433
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("h1", parent=styles["Title"], textColor=colors.HexColor("#f59e0b"))
    body_style = styles["BodyText"]; body_style.fontSize = 9

    elements = []
    elements.append(Paragraph("SolarDecide DZ — Rapport de comparaison", h_style))
    elements.append(Paragraph(f"Wilaya gagnante : <b>{payload['best']}</b> | Modèle : {payload['model']}", body_style))
    elements.append(Spacer(1, 0.4*cm))

    data = [["#", "Wilaya", "Climat", "GHI", "DNI", "KT", "T°C", "Vent", "Stab.", "Score", "ML"]]
    for w in payload["wilayas"]:
        f = w["features"]
        data.append([
            str(w["rank"]), w["wilaya"], w.get("climate_label") or w.get("climate") or "",
            f"{f['ghi_annuel']:.2f}", f"{f['dni_moyen']:.3f}",
            f"{f['kt_moyen']:.3f}", f"{f['t2m_moyen']:.1f}",
            f"{f['ws10m_moyen']:.2f}", f"{f['stabilite_pct']:.0f}%",
            f"{f['score_composite']:.1f}",
            f"{w['ml'].get('solar_score') or '—'}",
        ])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#d1fae5")),  # winner row
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph("<b>Résumé</b>", body_style))
    elements.append(Paragraph(payload["summary"], body_style))
    elements.append(Spacer(1, 0.6*cm))
    elements.append(Paragraph(
        f"<font color='#64748b' size=7>Source : NASA POWER (2019–2023) via data_service · "
        f"Modèle : {payload['model']} (R²={payload['model_metrics']['r2']})</font>", body_style))

    doc.build(elements)
    return buf.getvalue()
