"""Routes /api/roi — ROI calculation, history, and PDF export."""

import json
import logging
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from db_models import db, ROIHistory

logger = logging.getLogger(__name__)
bp = Blueprint("roi", __name__)

DZD_TO_USD = 0.0074

CAPEX_DA_PER_KWC = {
    "residentiel": 75_000,
    "industriel":  65_000,
    "ferme":       58_000,
}

# Fixed regulated tariffs — not inflation-indexed
TARIFF_DA_PER_KWH = {
    "residentiel":  5.00,
    "industriel":  10.00,
    "ferme":       12.00,
}

OPEX_RATIO = {
    "residentiel": 0.010,
    "industriel":  0.012,
    "ferme":       0.015,
}

PERFORMANCE_RATIO = {
    "residentiel": 0.78,
    "industriel":  0.82,
    "ferme":       0.85,
}

DISPLAY_YEARS   = 5
DEGRADATION     = 0.005      # 0.5%/year panel degradation
CO2_KG_PER_KWH  = 0.600
HOUSEHOLDS_KWH  = 3_800      # avg annual household consumption (kWh)
CO2_KG_PER_TREE = 21
CO2_KG_PER_KM   = 0.12
PANEL_WC        = 400        # standard panel wattage

TYPE_MAP = {
    "residentiel": "residentiel", "residential": "residentiel",
    "industriel":  "industriel",  "industrial":  "industriel",
    "ferme":       "ferme",       "farm":        "ferme",
    "ground_mount":"ferme",
}

# History rows returned per plan
HISTORY_LIMITS = {
    "free":       5,
    "pro":        50,
    "enterprise": None,
}


def _get_user_id_from_cookie_safe():
    try:
        from routes.auth import _get_user_id_from_cookie
        return _get_user_id_from_cookie()
    except Exception as exc:
        logger.debug("Auth lookup failed: %s", exc)
        return None


def _get_user_plan_safe(user_id):
    """Returns 'free' as default when unauthenticated or on error."""
    if not user_id:
        return "free"
    try:
        from services.plan_service import effective_plan, get_current_user
        user = get_current_user()
        if user is None:
            return "free"
        return effective_plan(user)
    except Exception as exc:
        logger.debug("Plan lookup failed: %s", exc)
        return "free"


def _normalize_type(t: str) -> str:
    return TYPE_MAP.get(str(t).lower(), "industriel")


def _get_wilaya_ghi_temp(wilaya_name: str) -> tuple[float, float]:
    """
    Returns (ghi_annual kWh/m²/yr, temp_avg °C) for a wilaya.
    Falls back to DataEngine summary, then (2400.0, 25.0) if both fail.
    """
    try:
        from utils.data_service import get_wilaya_stats
        stats = get_wilaya_stats(wilaya_name)
        if stats and stats.get("ghi_annuel_kwh_m2") is not None:
            ghi_annual = float(stats["ghi_annuel_kwh_m2"])
            temp_avg   = float(stats.get("t2m_moyen") or 25.0)
            # data_service returns mean(GHI) × 8760 / 1000 (~6.4) instead of
            # mean(GHI) × 8760 (~6400). Correct without touching the shared service.
            if 0 < ghi_annual < 100:
                ghi_annual *= 1000.0
            return ghi_annual, temp_avg
    except Exception as exc:
        logger.warning("data_service lookup failed for '%s': %s", wilaya_name, exc)

    try:
        from flask import current_app
        engine = current_app.config.get("DATA_ENGINE")
        if engine is not None:
            wilayas = engine.get_wilayas_summary()
            target = str(wilaya_name).strip().lower()
            for w in wilayas:
                if str(w.get("wilaya_name", "")).strip().lower() == target:
                    # mean(GHI) is in kWh/m²/h — multiply by 8760 for annual total
                    ghi_annual = float(w.get("mean_ghi") or 0.0) * 8760.0
                    temp_avg   = float(w.get("mean_t2m") or 25.0)
                    return ghi_annual, temp_avg
    except Exception as exc:
        logger.warning("DataEngine fallback failed for '%s': %s", wilaya_name, exc)

    logger.warning("Wilaya '%s' not found — using fallback GHI=2400, temp=25", wilaya_name)
    return 2400.0, 25.0


def _compute_roi(
    budget_da: float,
    project_type: str,
    ghi_annual: float,
    temp_avg: float,
    inflation_rate: float = 0.03,
) -> dict:
    """
    Core ROI calculation over DISPLAY_YEARS.
    - Tariff is fixed (regulated, not inflation-indexed).
    - OPEX grows with inflation: opex_base × (1 + inflation)^(y-1)
    - Production degrades 0.5%/year.
    - Temp correction: -0.35%/°C above 25°C.
    - Payback: linear interpolation between years; extrapolated from y1 cash flow
      if not reached within DISPLAY_YEARS. Returns None if ncf_y1 <= 0.
    """
    t             = _normalize_type(project_type)
    capex_per_kwc = CAPEX_DA_PER_KWC[t]
    capacity_kwc  = budget_da / capex_per_kwc
    nb_panels     = max(1, int(capacity_kwc * 1000 / PANEL_WC))
    opex_base     = budget_da * OPEX_RATIO[t]
    tariff        = TARIFF_DA_PER_KWH[t]
    pr            = PERFORMANCE_RATIO[t]

    temp_corr = 1.0 - max(0.0, (temp_avg - 25) * 0.0035)
    kwh_y1    = ghi_annual * capacity_kwc * pr * temp_corr

    series = []
    cumul  = 0.0
    kwh5   = 0.0

    for y in range(1, DISPLAY_YEARS + 1):
        prod    = kwh_y1 * (1 - DEGRADATION) ** (y - 1)
        revenue = prod * tariff
        opex_y  = opex_base * (1 + inflation_rate) ** (y - 1)
        net_cf  = revenue - opex_y
        cumul  += net_cf
        kwh5   += prod
        series.append({
            "year":       y,
            "production": round(prod),
            "revenue_da": round(revenue),
            "opex_da":    round(opex_y),
            "net_cf_da":  round(net_cf),
            "cumul_da":   round(cumul),
        })

    cumul5      = series[-1]["cumul_da"]
    eco_5y      = sum(s["revenue_da"] for s in series)
    ncf_y1      = series[0]["net_cf_da"]
    roi_y1      = (ncf_y1 / budget_da * 100) if budget_da > 0 else 0.0
    gain_net_5y = cumul5 - budget_da
    roi_5y      = (gain_net_5y / budget_da * 100) if budget_da > 0 else 0.0

    payback_years = payback_yr = payback_mo = None
    cc = 0.0
    for i, s in enumerate(series, 1):
        prev = cc
        cc  += s["net_cf_da"]
        if prev < budget_da <= cc and (cc - prev) > 0:
            py            = (i - 1) + (budget_da - prev) / (cc - prev)
            payback_years = round(py, 2)
            payback_yr    = int(py)
            payback_mo    = round((py - payback_yr) * 12)
            if payback_mo == 12:
                payback_yr += 1
                payback_mo  = 0
            break

    # Extrapolate from y1 cash flow if payback not reached within 5 years
    if payback_years is None and ncf_y1 > 0:
        py            = budget_da / ncf_y1
        payback_years = round(py, 2)
        payback_yr    = int(py)
        payback_mo    = round((py - payback_yr) * 12)
        if payback_mo == 12:
            payback_yr += 1
            payback_mo  = 0

    co2_per_year = round(kwh_y1 * CO2_KG_PER_KWH / 1000, 2)
    co2_5y       = round(kwh5   * CO2_KG_PER_KWH / 1000, 1)
    trees_eq     = int(co2_per_year * 1000 / CO2_KG_PER_TREE)
    km_car_eq    = int(co2_per_year * 1000 / CO2_KG_PER_KM)
    households   = int(kwh_y1 / HOUSEHOLDS_KWH)
    recovered_pct = min(100, round(cumul5 / budget_da * 100, 1)) if budget_da > 0 else 0

    return {
        "capacity_kwc":    round(capacity_kwc, 2),
        "nb_panels":       nb_panels,
        "capex_da":        round(budget_da),
        "capex_per_kwc":   capex_per_kwc,
        "opex_base_da":    round(opex_base),
        "tariff_da_kwh":   tariff,
        "pr":              pr,
        "temp_corr":       round(temp_corr, 4),
        "kwh_year1":       round(kwh_y1),
        "kwh_5y":          round(kwh5),
        "revenue_year1":   round(kwh_y1 * tariff),
        "eco_5y_da":       round(eco_5y),
        "roi_year1_pct":   round(roi_y1, 1),
        "roi_5y_pct":      round(roi_5y, 1),
        "gain_net_5y_da":  round(gain_net_5y),
        "cumul_5y_da":     round(cumul5),
        "recovered_pct":   recovered_pct,
        "payback_years":   payback_years,
        "payback_yr":      payback_yr,
        "payback_mo":      payback_mo,
        "co2_per_year_t":  co2_per_year,
        "co2_5y_t":        co2_5y,
        "trees_eq":        trees_eq,
        "km_car_eq":       km_car_eq,
        "households":      households,
        "series":          series,
    }


@bp.post("/roi")
def get_roi():
    try:
        body           = request.get_json(silent=True) or {}
        budget_da      = float(body.get("budget_da", body.get("investissement_da", 0)))
        project_type   = str(body.get("project_type", "industriel"))
        wilaya_id      = body.get("wilaya") or body.get("wilaya_code")
        inflation_rate = float(body.get("inflation_rate", 0.03))

        if budget_da <= 0:
            return jsonify({"error": "budget_da doit être > 0", "status": 400}), 400
        if budget_da > 50_000_000_000:
            return jsonify({"error": "budget_da trop élevé (max 50 Md DA)", "status": 400}), 400
        if inflation_rate < -0.5 or inflation_rate > 0.5:
            return jsonify({"error": "inflation_rate hors bornes (-0.5 .. 0.5)", "status": 400}), 400

        t           = _normalize_type(project_type)
        ghi_annual  = 2_400.0
        temp_avg    = 25.0
        wilaya_name = "Algérie"

        if wilaya_id:
            wilaya_name          = str(wilaya_id)
            ghi_annual, temp_avg = _get_wilaya_ghi_temp(wilaya_name)

        roi = _compute_roi(
            budget_da      = budget_da,
            project_type   = t,
            ghi_annual     = ghi_annual,
            temp_avg       = temp_avg,
            inflation_rate = inflation_rate,
        )

        result = {
            "status": 200,
            "params": {
                "budget_da":      budget_da,
                "project_type":   t,
                "wilaya":         wilaya_name,
                "ghi_annual":     round(ghi_annual, 1),
                "temp_avg":       round(temp_avg, 1),
                "inflation_rate": inflation_rate,
            },
            "data": roi,
        }

        # Persist to history if authenticated — silent on failure
        try:
            user_id = _get_user_id_from_cookie_safe()
            if user_id:
                record = ROIHistory(
                    user_id       = user_id,
                    wilaya_code   = str(wilaya_id) if wilaya_id else None,
                    wilaya_name   = wilaya_name,
                    capacity_mw   = roi["capacity_kwc"] / 1000,
                    scenario      = "moyen",
                    capex         = int(budget_da * DZD_TO_USD),
                    npv           = 0,
                    irr           = None,
                    payback_years = roi["payback_years"],
                    lcoe_usd_kwh  = 0,
                    result_json   = json.dumps(result),
                )
                db.session.add(record)
                db.session.commit()
                result["history_id"] = record.id

                try:
                    from services.admin_service import log_activity
                    log_activity(
                        "calcul_roi",
                        user_id=user_id,
                        details=f"wilaya:{wilaya_name} budget:{int(budget_da)}DA type:{t}",
                    )
                except Exception:
                    pass
        except Exception as db_err:
            logger.warning("ROI history save failed: %s", db_err)
            try:
                db.session.rollback()
            except Exception:
                pass

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": f"Paramètre invalide: {e}", "status": 400}), 400
    except Exception as e:
        logger.error("ROI calculation error: %s", e, exc_info=True)
        return jsonify({"error": str(e), "status": 400}), 400


@bp.get("/roi/history")
def get_roi_history():
    try:
        user_id = _get_user_id_from_cookie_safe()
        if not user_id:
            return jsonify({"error": "Non authentifié", "status": 401}), 401

        plan  = _get_user_plan_safe(user_id)
        limit = HISTORY_LIMITS.get(plan, 5)

        query = (
            ROIHistory.query
            .filter_by(user_id=user_id)
            .order_by(ROIHistory.created_at.desc())
        )
        if limit is not None:
            query = query.limit(limit)

        records = query.all()
        data = [
            {
                "id":            r.id,
                "wilaya_name":   r.wilaya_name,
                "capacity_mw":   r.capacity_mw,
                "capex":         r.capex,
                "payback_years": r.payback_years,
                "created_at":    r.created_at.isoformat() if r.created_at else None,
                "result":        json.loads(r.result_json) if r.result_json else None,
            }
            for r in records
        ]
        return jsonify({"status": 200, "plan": plan, "limit": limit, "data": data})

    except Exception as e:
        logger.error("ROI history error: %s", e, exc_info=True)
        return jsonify({"error": str(e), "status": 400}), 400


def _build_roi_html(record, params, data, plan):
    """Builds HTML string for WeasyPrint. Pro plan gets a watermark."""
    from datetime import datetime as _dt
    series = data.get("series", [])
    now_str = _dt.now().strftime("%d/%m/%Y %H:%M")
    watermark_html = '<div class="watermark">Version Pro</div>' if plan == "pro" else ""

    pb_yr = data.get("payback_yr")
    pb_mo = data.get("payback_mo")
    payback_str = f"{pb_yr} ans {pb_mo} mois" if pb_yr is not None else "Non atteint sur 5 ans"

    rows_html = ""
    budget_da = params.get("budget_da", 0)
    for s in series:
        row_class = 'green-row' if s.get("cumul_da", 0) >= budget_da else ''
        rows_html += f"""
        <tr class="{row_class}">
          <td>{s['year']}</td>
          <td>{s['production']:,}</td>
          <td>{s['revenue_da']:,}</td>
          <td>{s['opex_da']:,}</td>
          <td>{s['net_cf_da']:,}</td>
          <td>{s['cumul_da']:,}</td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
  body       {{ font-family: Arial, sans-serif; margin: 30px; color: #222; }}
  .watermark {{ position: fixed; top: 45%; left: 25%; opacity: 0.08;
                font-size: 80px; font-weight: bold; color: #888;
                transform: rotate(-30deg); z-index: 1000; }}
  h1         {{ color: #f59e0b; }}
  h2         {{ color: #374151; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }}
  .meta      {{ color: #6b7280; font-size: 12px; margin-bottom: 20px; }}
  .kpis      {{ display: flex; gap: 16px; margin: 16px 0; }}
  .kpi       {{ flex: 1; background: #f9fafb; border: 1px solid #e5e7eb;
                border-radius: 8px; padding: 12px; text-align: center; }}
  .kpi-val   {{ font-size: 24px; font-weight: bold; color: #10b981; }}
  .kpi-lbl   {{ font-size: 11px; color: #6b7280; }}
  table      {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
  th         {{ background: #f3f4f6; padding: 8px; text-align: right; }}
  th:first-child {{ text-align: center; }}
  td         {{ padding: 7px 8px; border-bottom: 1px solid #f3f4f6; text-align: right; }}
  td:first-child {{ text-align: center; }}
  .green-row td {{ background: #ecfdf5; }}
  .env       {{ background: #f0fdf4; border: 1px solid #bbf7d0;
                border-radius: 8px; padding: 14px; margin-top: 16px; }}
  .footer    {{ margin-top: 30px; font-size: 11px; color: #9ca3af; text-align: center; }}
</style>
</head>
<body>
{watermark_html}
<h1>☀ SolarDecide DZ — Rapport ROI</h1>
<div class="meta">Généré le {now_str}</div>
<h2>Paramètres du projet</h2>
<table>
  <tr><th style="text-align:left">Wilaya</th><td style="text-align:left">{params.get('wilaya','—')}</td></tr>
  <tr><th style="text-align:left">Type projet</th><td style="text-align:left">{params.get('project_type','—').capitalize()}</td></tr>
  <tr><th style="text-align:left">Budget</th><td style="text-align:left">{int(budget_da):,} DA</td></tr>
  <tr><th style="text-align:left">Capacité installée</th><td style="text-align:left">{data.get('capacity_kwc','—')} kWc</td></tr>
  <tr><th style="text-align:left">Nombre de panneaux</th><td style="text-align:left">{data.get('nb_panels','—')}</td></tr>
  <tr><th style="text-align:left">GHI annuel</th><td style="text-align:left">{params.get('ghi_annual','—')} kWh/m²/an</td></tr>
  <tr><th style="text-align:left">Inflation charges</th><td style="text-align:left">{params.get('inflation_rate', 0)*100:.1f}%/an</td></tr>
</table>
<h2>KPIs Principaux</h2>
<div class="kpis">
  <div class="kpi">
    <div class="kpi-val">{data.get('roi_year1_pct','—')}%</div>
    <div class="kpi-lbl">ROI Année 1</div>
  </div>
  <div class="kpi">
    <div class="kpi-val">{data.get('roi_5y_pct','—')}%</div>
    <div class="kpi-lbl">ROI 5 ans</div>
  </div>
  <div class="kpi">
    <div class="kpi-val" style="font-size:18px">{payback_str}</div>
    <div class="kpi-lbl">Retour sur investissement</div>
  </div>
  <div class="kpi">
    <div class="kpi-val" style="font-size:18px">{int(data.get('gain_net_5y_da',0)):,} DA</div>
    <div class="kpi-lbl">Gain net 5 ans</div>
  </div>
</div>
<h2>Tableau annuel</h2>
<table>
  <thead>
    <tr>
      <th>Année</th><th>Production (kWh)</th><th>Revenus (DA)</th>
      <th>Charges (DA)</th><th>Flux net (DA)</th><th>Cumul (DA)</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
<div class="env">
  <h2 style="margin-top:0">🌱 Impact Environnemental</h2>
  <p>CO₂ évité par an : <strong>{data.get('co2_per_year_t','—')} tonnes</strong></p>
  <p>CO₂ évité sur 5 ans : <strong>{data.get('co2_5y_t','—')} tonnes</strong></p>
  <p>Équivalent arbres plantés : <strong>{data.get('trees_eq','—')}</strong></p>
  <p>Équivalent km voiture évités : <strong>{int(data.get('km_car_eq',0)):,} km</strong></p>
  <p>Foyers alimentés : <strong>{data.get('households','—')}</strong></p>
</div>
<div class="footer">SolarDecide DZ — Calcul indicatif basé sur des données moyennes. Consultez un installateur certifié.</div>
</body>
</html>"""


def _build_roi_pdf_reportlab(record, params, data, plan):
    """ReportLab fallback — used when WeasyPrint is unavailable."""
    from datetime import datetime as _dt
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Title"], textColor=colors.HexColor("#f59e0b"),
        fontSize=20, spaceAfter=4,
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], textColor=colors.HexColor("#374151"),
        spaceBefore=14, spaceAfter=6,
    )
    meta = ParagraphStyle("meta", parent=styles["BodyText"], textColor=colors.grey, fontSize=10)

    story = []
    story.append(Paragraph("☀ SolarDecide DZ — Rapport ROI", title_style))
    story.append(Paragraph(f"Généré le {_dt.now().strftime('%d/%m/%Y %H:%M')}", meta))
    if plan == "pro":
        story.append(Paragraph("<i>Version Pro</i>", meta))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Paramètres du projet", h2))
    budget_da = params.get("budget_da", 0)
    params_rows = [
        ["Wilaya",             str(params.get("wilaya", "—"))],
        ["Type projet",        str(params.get("project_type", "—")).capitalize()],
        ["Budget",             f"{int(budget_da):,} DA"],
        ["Capacité installée", f"{data.get('capacity_kwc','—')} kWc"],
        ["Nombre de panneaux", str(data.get('nb_panels', '—'))],
        ["GHI annuel",         f"{params.get('ghi_annual','—')} kWh/m²/an"],
        ["Inflation charges",  f"{params.get('inflation_rate', 0)*100:.1f}%/an"],
    ]
    t = Table(params_rows, colWidths=[6*cm, 10*cm])
    t.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING",    (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    story.append(Paragraph("KPIs Principaux", h2))
    pb_yr = data.get("payback_yr")
    pb_mo = data.get("payback_mo")
    payback_str = f"{pb_yr} ans {pb_mo} mois" if pb_yr is not None else "Non atteint sur 5 ans"
    kpi_rows = [
        ["ROI Année 1", "ROI 5 ans", "Payback", "Gain net 5 ans"],
        [f"{data.get('roi_year1_pct','—')}%",
         f"{data.get('roi_5y_pct','—')}%",
         payback_str,
         f"{int(data.get('gain_net_5y_da',0)):,} DA"],
    ]
    kt = Table(kpi_rows, colWidths=[4*cm]*4)
    kt.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0),  9),
        ("FONTSIZE",   (0, 1), (-1, 1),  14),
        ("TEXTCOLOR",  (0, 1), (-1, 1),  colors.HexColor("#10b981")),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 0),  colors.HexColor("#f9fafb")),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("INNERGRID",  (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING",    (0, 0), (-1, -1), 8),
    ]))
    story.append(kt)

    story.append(Paragraph("Tableau annuel", h2))
    table_rows = [["Année", "Production (kWh)", "Revenus (DA)", "Charges (DA)",
                   "Flux net (DA)", "Cumul (DA)"]]
    for s in data.get("series", []):
        table_rows.append([
            s["year"], f"{s['production']:,}", f"{s['revenue_da']:,}",
            f"{s['opex_da']:,}", f"{s['net_cf_da']:,}", f"{s['cumul_da']:,}",
        ])
    at = Table(table_rows, colWidths=[1.6*cm, 3.2*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    at.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0),  colors.HexColor("#f3f4f6")),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ALIGN",      (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",      (0, 0), (0, -1),  "CENTER"),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
        ("PADDING",    (0, 0), (-1, -1), 5),
    ]))
    # Highlight rows where cumulative cash flow has recovered the budget
    for idx, s in enumerate(data.get("series", []), start=1):
        if s.get("cumul_da", 0) >= budget_da:
            at.setStyle(TableStyle([
                ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#ecfdf5")),
            ]))
    story.append(at)

    story.append(Paragraph("🌱 Impact Environnemental", h2))
    env_rows = [
        ["CO₂ évité par an",             f"{data.get('co2_per_year_t','—')} tonnes"],
        ["CO₂ évité sur 5 ans",          f"{data.get('co2_5y_t','—')} tonnes"],
        ["Équivalent arbres plantés",    str(data.get('trees_eq','—'))],
        ["Équivalent km voiture évités", f"{int(data.get('km_car_eq',0)):,} km"],
        ["Foyers alimentés",             str(data.get('households','—'))],
    ]
    et = Table(env_rows, colWidths=[7*cm, 9*cm])
    et.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#bbf7d0")),
        ("INNERGRID",  (0, 0), (-1, -1), 0.3, colors.HexColor("#bbf7d0")),
        ("PADDING",    (0, 0), (-1, -1), 6),
    ]))
    story.append(et)
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "<i>SolarDecide DZ — Calcul indicatif basé sur des données moyennes. "
        "Consultez un installateur certifié.</i>", meta))

    doc.build(story)
    buf.seek(0)
    return buf.read()


@bp.get("/roi/export-pdf/<int:history_id>")
def export_roi_pdf(history_id: int):
    """Pro/Enterprise only. Tries WeasyPrint first, falls back to ReportLab."""
    try:
        user_id = _get_user_id_from_cookie_safe()
        if not user_id:
            return jsonify({"error": "Non authentifié", "status": 401}), 401

        plan = _get_user_plan_safe(user_id)
        if plan not in ("pro", "enterprise"):
            return jsonify({
                "error":    "plan_required",
                "required": "pro",
                "message":  "Export PDF disponible avec le plan Pro ou Entreprise",
                "status":   402,
            }), 402

        record = ROIHistory.query.filter_by(id=history_id, user_id=user_id).first()
        if not record:
            return jsonify({"error": "Calcul introuvable", "status": 404}), 404

        result = json.loads(record.result_json) if record.result_json else {}
        params = result.get("params", {})
        data   = result.get("data", {})

        pdf_bytes = None
        try:
            from weasyprint import HTML as WeasyprintHTML
            html_content = _build_roi_html(record, params, data, plan)
            pdf_bytes = WeasyprintHTML(string=html_content).write_pdf()
        except Exception as exc:
            logger.info("WeasyPrint unavailable (%s) — falling back to ReportLab", exc)
            try:
                pdf_bytes = _build_roi_pdf_reportlab(record, params, data, plan)
            except Exception as exc2:
                logger.error("ReportLab PDF generation failed: %s", exc2, exc_info=True)
                return jsonify({
                    "error":  "pdf_generation_failed",
                    "detail": str(exc2),
                    "status": 500,
                }), 500

        buf = BytesIO(pdf_bytes)
        buf.seek(0)
        safe_name = str(record.wilaya_name or "wilaya").replace(" ", "_")
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"roi_solaire_{safe_name}_{history_id}.pdf",
        )

    except Exception as e:
        logger.error("PDF export error: %s", e, exc_info=True)
        return jsonify({"error": str(e), "status": 400}), 400