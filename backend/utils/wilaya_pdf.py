"""
Generate a 1-page "Fiche wilaya" 

Primary engine  : WeasyPrint (HTML/CSS) — gives the nicest layout.
Fallback engine : ReportLab — no system libs required, always available.

The caller passes three pre-computed dicts :
    stats    from get_wilaya_stats()
    monthly  from get_wilaya_monthly()
    extras   from get_wilaya_extras()

Returns the PDF as a `bytes` object.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

#  HTML / CSS template

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Fiche {wilaya_name}</title>
<style>
    @page {{
        size: A4;
        margin: 18mm 16mm;
    }}
    body {{
        font-family: 'Helvetica Neue', Arial, sans-serif;
        color: #1f2937;
        font-size: 11pt;
        line-height: 1.45;
    }}
    h1 {{ font-size: 22pt; margin: 0 0 4mm; color: #0f172a; }}
    h2 {{ font-size: 13pt; margin: 6mm 0 2mm; color: #0f172a; border-bottom: 1px solid #e5e7eb; padding-bottom: 2mm; }}
    .accent {{ color: #f59e0b; }}
    .brand-bar {{ background: #f59e0b; color: #ffffff; padding: 5mm 6mm; border-radius: 3mm;
                  margin-bottom: 5mm; display: flex; justify-content: space-between; align-items: center; }}
    .brand-bar .brand-title {{ font-size: 16pt; font-weight: 800; letter-spacing: 0.03em; color:#ffffff; }}
    .brand-bar .brand-sub   {{ font-size: 9pt; color:#fff7e0; margin-top: 1mm; }}
    .brand-bar .brand-meta  {{ font-size: 9pt; text-align: right; color:#ffffff; }}
    .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6mm; }}
    .meta {{ font-size: 9pt; color: #6b7280; text-align: right; }}
    .badge {{ display: inline-block; padding: 1mm 3mm; border-radius: 3mm;
              background: #fef3c7; color: #92400e; font-weight: 700; font-size: 10pt; }}
    .grid {{ display: table; width: 100%; border-spacing: 0 1.5mm; }}
    .row {{ display: table-row; }}
    .cell {{ display: table-cell; padding: 2mm 3mm; vertical-align: top; border-bottom: 1px dashed #e5e7eb; }}
    .label {{ color: #6b7280; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.04em; }}
    .value {{ font-weight: 700; font-size: 12pt; color: #111827; }}
    .kpi-grid {{ width: 100%; border-collapse: collapse; margin-bottom: 4mm; }}
    .kpi-grid td {{
        width: 25%;
        padding: 3mm 4mm;
        border: 1px solid #e5e7eb;
        vertical-align: top;
    }}
    .kpi-grid .label {{ font-size: 8.5pt; }}
    .kpi-grid .value {{ font-size: 14pt; color: #f59e0b; }}
    table.monthly {{ width: 100%; border-collapse: collapse; font-size: 9pt; margin-top: 2mm; }}
    table.monthly th, table.monthly td {{ padding: 1.5mm; border: 1px solid #e5e7eb; text-align: center; }}
    table.monthly th {{ background: #f3f4f6; color: #374151; font-weight: 700; }}
    table.monthly td.lbl {{ background: #fafafa; font-weight: 700; color: #374151; text-align: left; padding-left: 3mm; }}
    .footer {{ position: fixed; bottom: -10mm; left: 0; right: 0; text-align: center;
               font-size: 8pt; color: #9ca3af; }}
    {watermark_css}
</style>
</head>
<body>

<div class="brand-bar">
    <div>
        <div class="brand-title">☀ SolarDecide DZ</div>
        <div class="brand-sub">Plateforme d'aide à la décision solaire pour l'Algérie — NASA POWER 2019-2023</div>
    </div>
    <div class="brand-meta">
        <div><b>Fiche wilaya</b></div>
        <div>{generated_at}</div>
    </div>
</div>

<div class="header">
    <div>
        <h1>{wilaya_name} <span class="accent">·</span> Fiche wilaya</h1>
        <div style="color:#6b7280;font-size:10pt">
            {climate_label} &nbsp;·&nbsp; {region} &nbsp;·&nbsp; {n_communes} communes
        </div>
    </div>
    <div class="meta">
        <div class="badge">Rang #{rang_national} / 58</div><br>
        <div style="margin-top:2mm">Score composite : <b>{score_composite}/100</b></div>
    </div>
</div>

<h2>Indicateurs clés</h2>
<table class="kpi-grid">
    <tr>
        <td>
            <div class="label">GHI annuel</div>
            <div class="value">{ghi}</div>
            <div style="font-size:9pt;color:#6b7280">kWh/m&sup2;/an</div>
        </td>
        <td>
            <div class="label">Potentiel</div>
            <div class="value">{potentiel} MW</div>
            <div style="font-size:9pt;color:#6b7280">10 km&sup2; ref.</div>
        </td>
        <td>
            <div class="label">DNI moyen</div>
            <div class="value">{dni}</div>
            <div style="font-size:9pt;color:#6b7280">kWh/m&sup2;/h</div>
        </td>
        <td>
            <div class="label">Indice de clart&eacute;</div>
            <div class="value">{kt}</div>
            <div style="font-size:9pt;color:#6b7280">CLEARNESS_KT</div>
        </td>
    </tr>
    <tr>
        <td>
            <div class="label">T2M moyenne</div>
            <div class="value">{t2m}&deg;C</div>
            <div style="font-size:9pt;color:#6b7280">min {t2m_min}&deg;C &mdash; max {t2m_max}&deg;C</div>
        </td>
        <td>
            <div class="label">Vent moyen</div>
            <div class="value">{ws10m} m/s</div>
            <div style="font-size:9pt;color:#6b7280">WS10M</div>
        </td>
        <td>
            <div class="label">Humidit&eacute; RH2M</div>
            <div class="value">{rh2m} %</div>
            <div style="font-size:9pt;color:#6b7280">moyenne annuelle</div>
        </td>
        <td>
            <div class="label">Ensoleillement</div>
            <div class="value">{ensoleillement}</div>
            <div style="font-size:9pt;color:#6b7280">heures/an</div>
        </td>
    </tr>
</table>

<h2>Indicateurs avancés</h2>
<div class="grid">
    <div class="row">
        <div class="cell"><div class="label">Jours nuageux/an</div><div class="value">{cloudy_days}</div></div>
        <div class="cell"><div class="label">Instabilit&eacute; GHI</div><div class="value">{ghi_instab} %</div></div>
        <div class="cell"><div class="label">Pr&eacute;cipitations annuelles</div><div class="value">{precip} mm</div></div>
        <div class="cell"><div class="label">Climat dominant</div><div class="value">{dominant_climate}</div></div>
    </div>
</div>

<h2>Données mensuelles réelles (dataset)</h2>
<table class="monthly">
    <tr><th style="text-align:left;padding-left:3mm">Indicateur</th>{th_months}<th>Annuel</th></tr>
    <tr><td class="lbl">GHI (kWh/m²/mois)</td>{td_ghi}<td><b>{ghi_total}</b></td></tr>
    <tr><td class="lbl">DNI (W/m²)</td>{td_dni}<td><b>{dni_mean_val}</b></td></tr>
    <tr><td class="lbl">Température (°C)</td>{td_t2m}<td><b>{t2m_mean_val}</b></td></tr>
    <tr><td class="lbl">Vent (m/s)</td>{td_ws}<td><b>{ws_mean}</b></td></tr>
    <tr><td class="lbl">PR (%)</td>{td_pr}<td><b>{pr_mean}</b></td></tr>
</table>

<div class="footer">
    SolarDecide DZ &mdash; Source : NASA POWER 2019-2023 &mdash; Plateforme d'aide &agrave; la d&eacute;cision solaire en Alg&eacute;rie
</div>

</body>
</html>
"""

_WATERMARK_CSS_PRO = """
    body::before {
        content: 'SolarDecide DZ — Version Pro';
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) rotate(-32deg);
        font-size: 60pt;
        color: rgba(245, 158, 11, 0.12);
        font-weight: 700;
        z-index: -1;
        white-space: nowrap;
        letter-spacing: 0.04em;
    }
"""


def _format_html(stats: dict, monthly: Optional[dict], extras: Optional[dict],
                 watermark: bool) -> str:
    m = monthly or {}
    months_lbl  = m.get("labels") or ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Aoû","Sep","Oct","Nov","Déc"]
    ghi_monthly = m.get("ghi")    or [0] * 12
    dni_monthly = m.get("dni")    or [0] * 12
    t2m_monthly = m.get("t2m")    or [0] * 12
    ws_monthly  = m.get("ws10m")  or [0] * 12
    pr_monthly  = m.get("pr")     or [0] * 12

    def _row(values, fmt):
        return "".join(f"<td>{fmt(v)}</td>" for v in values)

    def _avg(arr):
        nums = [float(x) for x in arr if x is not None]
        return sum(nums) / len(nums) if nums else 0.0

    th_months    = "".join(f"<th>{x}</th>" for x in months_lbl)
    td_ghi       = _row(ghi_monthly, lambda v: f"{float(v or 0):.0f}")
    td_dni       = _row(dni_monthly, lambda v: f"{float(v or 0):.0f}")
    td_t2m       = _row(t2m_monthly, lambda v: f"{float(v or 0):.1f}")
    td_ws        = _row(ws_monthly,  lambda v: f"{float(v or 0):.2f}")
    td_pr        = _row(pr_monthly,  lambda v: f"{float(v or 0) * 100:.1f}")
    ghi_total    = f"{sum(float(x or 0) for x in ghi_monthly):.0f}"
    dni_mean_val = f"{_avg(dni_monthly):.0f}"
    t2m_mean_val = f"{_avg(t2m_monthly):.1f}"
    ws_mean      = f"{_avg(ws_monthly):.2f}"
    pr_mean      = f"{_avg(pr_monthly) * 100:.1f}"

    return _HTML_TEMPLATE.format(
        wilaya_name        = stats.get("wilaya_name", "—"),
        climate_label      = stats.get("climate_label", "—"),
        region             = stats.get("region", "—"),
        n_communes         = stats.get("n_communes", "—"),
        rang_national      = stats.get("rang_national", "—"),
        score_composite    = stats.get("score_composite", "—"),
        ghi                = stats.get("ghi_annuel_kwh_m2", "—"),
        potentiel          = stats.get("potentiel_mw", "—"),
        dni                = stats.get("dni_moyen", "—"),
        kt                 = stats.get("clearness_kt_moyen", "—"),
        t2m                = stats.get("t2m_moyen", "—"),
        t2m_min            = stats.get("t2m_min", "—"),
        t2m_max            = stats.get("t2m_max", "—"),
        ws10m              = stats.get("vent_moyen_m_s", "—"),
        rh2m               = stats.get("rh2m_moyen", "—"),
        ensoleillement     = stats.get("ensoleillement_h_an", "—"),
        cloudy_days        = (extras or {}).get("cloudy_days_year", "—"),
        ghi_instab         = (extras or {}).get("ghi_instability_pct", "—"),
        precip             = (extras or {}).get("precip_annual_mm", "—"),
        dominant_climate   = (extras or {}).get("dominant_climate", "—"),
        th_months          = th_months,
        td_ghi             = td_ghi,
        td_dni             = td_dni,
        td_t2m             = td_t2m,
        td_ws              = td_ws,
        td_pr              = td_pr,
        ghi_total          = ghi_total,
        dni_mean_val       = dni_mean_val,
        t2m_mean_val       = t2m_mean_val,
        ws_mean            = ws_mean,
        pr_mean            = pr_mean,
        generated_at       = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        watermark_css      = _WATERMARK_CSS_PRO if watermark else "",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_wilaya_pdf(stats: dict, monthly: Optional[dict] = None,
                     extras: Optional[dict] = None,
                     watermark: bool = False) -> bytes:
    """
    Build a 1-page PDF for the given wilaya.

    Tries WeasyPrint first ; falls back to ReportLab if WeasyPrint is not
    installed (cairo / pango can be tricky to install on some systems).
    """
    html = _format_html(stats, monthly, extras, watermark)

    # 1° Try WeasyPrint -------------------------------------------------------
    try:
        from weasyprint import HTML  # type: ignore
        return HTML(string=html, base_url=".").write_pdf()
    except Exception as exc:  # noqa: BLE001
        logger.info("WeasyPrint unavailable, falling back to ReportLab: %s", exc)

    # 2° Fallback: ReportLab --------------------------------------------------
    return _build_with_reportlab(stats, monthly, extras, watermark)


def _build_with_reportlab(stats: dict, monthly: Optional[dict],
                          extras: Optional[dict], watermark: bool) -> bytes:
    """Pure-Python fallback using ReportLab (always available)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"],
        fontSize=18, leading=22, textColor=colors.HexColor("#0f172a"),
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=12, leading=16, textColor=colors.HexColor("#0f172a"), spaceBefore=10, spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "Meta", parent=styles["Normal"],
        fontSize=9, leading=12, textColor=colors.HexColor("#6b7280"),
    )

    # Brand header bar (orange band)
    brand_tbl = Table(
        [[
            Paragraph(
                "<font color='white' size=14><b>☀ SolarDecide DZ</b></font><br/>"
                "<font color='#fff7e0' size=8>Plateforme d'aide à la décision solaire — NASA POWER 2019-2023</font>",
                styles["Normal"],
            ),
            Paragraph(
                f"<font color='white' size=10><b>Fiche wilaya</b></font><br/>"
                f"<font color='white' size=8>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</font>",
                ParagraphStyle('rightm', parent=styles["Normal"], alignment=2),
            ),
        ]],
        colWidths=[120 * mm, 60 * mm],
    )
    brand_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f59e0b")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("BOX",        (0, 0), (-1, -1), 0, colors.HexColor("#f59e0b")),
        ("LEFTPADDING",(0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [brand_tbl, Spacer(1, 6)]

    story.append(Paragraph(
        f"<b>{stats.get('wilaya_name','—')}</b> · Fiche wilaya",
        title_style,
    ))
    story.append(Paragraph(
        f"{stats.get('climate_label','—')} · {stats.get('region','—')} · "
        f"{stats.get('n_communes','—')} communes — Rang #{stats.get('rang_national','—')}/58 — "
        f"Score composite <b>{stats.get('score_composite','—')}/100</b>",
        meta_style,
    ))
    story.append(Spacer(1, 8))

    # KPI grid
    kpi_data = [
        ["GHI annuel", "Potentiel MW", "DNI moyen", "Indice de clarté"],
        [
            f"{stats.get('ghi_annuel_kwh_m2','—')} kWh/m²/an",
            f"{stats.get('potentiel_mw','—')} MW",
            f"{stats.get('dni_moyen','—')}",
            f"{stats.get('clearness_kt_moyen','—')}",
        ],
        ["T2M moyenne", "Vent (WS10M)", "RH2M", "Ensoleillement"],
        [
            f"{stats.get('t2m_moyen','—')} °C  (min {stats.get('t2m_min','—')}, max {stats.get('t2m_max','—')})",
            f"{stats.get('vent_moyen_m_s','—')} m/s",
            f"{stats.get('rh2m_moyen','—')} %",
            f"{stats.get('ensoleillement_h_an','—')} h/an",
        ],
    ]
    kpi_tbl = Table(kpi_data, colWidths=[45 * mm] * 4)
    kpi_tbl.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [colors.HexColor("#f9fafb"), colors.HexColor("#ffffff")]),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.HexColor("#6b7280")),
        ("TEXTCOLOR",  (0, 2), (-1, 2), colors.HexColor("#6b7280")),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("FONTSIZE",   (0, 2), (-1, 2), 8),
        ("FONTNAME",   (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTNAME",   (0, 3), (-1, 3), "Helvetica-Bold"),
        ("TEXTCOLOR",  (0, 1), (-1, 1), colors.HexColor("#f59e0b")),
        ("TEXTCOLOR",  (0, 3), (-1, 3), colors.HexColor("#f59e0b")),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    story.append(kpi_tbl)

    # Advanced
    story.append(Paragraph("Indicateurs avancés", h2))
    adv = extras or {}
    adv_data = [
        ["Jours nuageux/an", "Instabilité GHI (%)", "Précipitations (mm/an)", "Climat dominant"],
        [
            adv.get("cloudy_days_year", "—"),
            adv.get("ghi_instability_pct", "—"),
            adv.get("precip_annual_mm", "—"),
            adv.get("dominant_climate", "—"),
        ],
    ]
    adv_tbl = Table(adv_data, colWidths=[45 * mm] * 4)
    adv_tbl.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.HexColor("#6b7280")),
        ("FONTNAME",   (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 1), (-1, 1), 11),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(adv_tbl)

    # Monthly table (real values from parquet : GHI, DNI, T2M, WS10M, PR)
    story.append(Paragraph("Données mensuelles réelles (dataset)", h2))
    mm_data = monthly or {}
    months_lbl = mm_data.get("labels") or [
        "Jan","Fév","Mar","Avr","Mai","Juin","Juil","Aoû","Sep","Oct","Nov","Déc"
    ]
    ghi_monthly = mm_data.get("ghi")   or [0] * 12
    dni_monthly = mm_data.get("dni")   or [0] * 12
    t2m_monthly = mm_data.get("t2m")   or [0] * 12
    ws_monthly  = mm_data.get("ws10m") or [0] * 12
    pr_monthly  = mm_data.get("pr")    or [0] * 12

    def _fmt(values, f):
        return [f(v) for v in values]
    def _avg(arr):
        nums = [float(x) for x in arr if x is not None]
        return sum(nums) / len(nums) if nums else 0.0

    header_row = ["Indicateur"] + months_lbl + ["Annuel"]
    row_ghi = ["GHI (kWh/m²/mois)"] + _fmt(ghi_monthly, lambda v: f"{float(v or 0):.0f}") + [f"{sum(float(x or 0) for x in ghi_monthly):.0f}"]
    row_dni = ["DNI (W/m²)"]        + _fmt(dni_monthly, lambda v: f"{float(v or 0):.0f}") + [f"{_avg(dni_monthly):.0f}"]
    row_t2m = ["Température (°C)"]  + _fmt(t2m_monthly, lambda v: f"{float(v or 0):.1f}") + [f"{_avg(t2m_monthly):.1f}"]
    row_ws  = ["Vent (m/s)"]        + _fmt(ws_monthly,  lambda v: f"{float(v or 0):.2f}") + [f"{_avg(ws_monthly):.2f}"]
    row_pr  = ["PR (%)"]            + _fmt(pr_monthly,  lambda v: f"{float(v or 0)*100:.1f}") + [f"{_avg(pr_monthly)*100:.1f}"]

    monthly_data = [header_row, row_ghi, row_dni, row_t2m, row_ws, row_pr]
    col_widths = [32 * mm] + [11 * mm] * 12 + [15 * mm]
    monthly_tbl = Table(monthly_data, colWidths=col_widths, repeatRows=1)
    monthly_tbl.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 7.5),
        ("BACKGROUND",(0, 0), (-1, 0),  colors.HexColor("#f3f4f6")),
        ("BACKGROUND",(0, 1), (0, -1),  colors.HexColor("#fafafa")),
        ("FONTNAME",  (0, 1), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",  (-1, 1), (-1, -1),"Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0),  colors.HexColor("#374151")),
        ("BOX",       (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("ALIGN",     (1, 0), (-1, -1), "CENTER"),
        ("ALIGN",     (0, 0), (0, -1),  "LEFT"),
        ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2),
    ]))
    story.append(monthly_tbl)

    # Footer
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"<font size=8 color='#9ca3af'>SolarDecide DZ — Source: NASA POWER 2019-2023 — Généré le "
        f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</font>",
        meta_style,
    ))

    # Optional watermark on every page
    def _watermark(canvas, doc):
        if not watermark:
            return
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 50)
        canvas.setFillColorRGB(0.96, 0.62, 0.04, alpha=0.10)
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(32)
        canvas.drawCentredString(0, 0, "SolarDecide DZ — Version Pro")
        canvas.restoreState()

    doc.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    pdf = buf.getvalue()
    buf.close()
    return pdf
