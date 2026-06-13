"""Report Generator (PDF export)

Génère trois rapports PDF distincts, alimentés exclusivement par le dataset
(.parquet) via les helpers de routes/dataset_api.py. Les sections de chaque
"""

from __future__ import annotations

import math
import unicodedata
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional


# Import lazy de reportlab pour ne pas bloquer le démarrage si la lib manque
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers de mise en forme
# ─────────────────────────────────────────────────────────────────────────────

_PRIMARY = colors.HexColor("#1a73e8") if REPORTLAB_AVAILABLE else None
_AMBER = colors.HexColor("#d97706") if REPORTLAB_AVAILABLE else None
_GREEN = colors.HexColor("#22c55e") if REPORTLAB_AVAILABLE else None
_GRAY_BG = colors.HexColor("#f3f4f6") if REPORTLAB_AVAILABLE else None
_DARK = colors.HexColor("#1f2937") if REPORTLAB_AVAILABLE else None


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _fmt_num(value: Any, decimals: int = 1) -> str:
    try:
        n = float(value)
        if math.isnan(n) or math.isinf(n):
            return "—"
        return (f"{n:,.{decimals}f}").replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _fmt_da(value: Any) -> str:
    formatted = _fmt_int(value)
    return f"{formatted} DA" if formatted != "—" else "—"


def _normalize_ascii(text: str) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    return s.encode("ascii", "ignore").decode("ascii")


# ─────────────────────────────────────────────────────────────────────────────
#  Connecteur dataset (réutilise les helpers de Phase 2 / 3)
# ─────────────────────────────────────────────────────────────────────────────

def _load_dataset_helpers():
    """Retourne les helpers DuckDB exposés par routes/dataset_api.py."""
    from routes.dataset_api import (
        _all_wilaya_scores_df,
        _resolve_wilaya,
        _monthly_ghi_df,
        _national_monthly_ghi,
        _yearly_ghi_df,
        _classify_trend,
        _grid_distance_km_proxy,
        _region_for,
        _production_kwh_from_ghi,
        _HORIZON_CONFIG,
    )
    return {
        "scores_df": _all_wilaya_scores_df,
        "resolve": _resolve_wilaya,
        "monthly_df": _monthly_ghi_df,
        "national_monthly": _national_monthly_ghi,
        "yearly_df": _yearly_ghi_df,
        "classify_trend": _classify_trend,
        "grid_distance": _grid_distance_km_proxy,
        "region_for": _region_for,
        "production_kwh": _production_kwh_from_ghi,
        "horizon_cfg": _HORIZON_CONFIG,
    }


def _wilaya_dataset_payload(name_or_code: str) -> Dict[str, Any]:
    """Construit un dictionnaire complet pour une wilaya depuis le dataset."""
    helpers = _load_dataset_helpers()
    info = helpers["resolve"](name_or_code)
    if not info:
        raise ValueError(f"Wilaya '{name_or_code}' introuvable dans le dataset.")

    code = int(info["wilaya_code"])
    canonical = info["wilaya_name"]

    df = helpers["scores_df"]()
    row = df[df["wilaya_code"] == code].iloc[0]

    monthly_rows = helpers["monthly_df"]()
    monthly = (
        monthly_rows[monthly_rows["wilaya_code"] == code]
        .sort_values("month")["ghi_monthly_kwh_m2"]
        .tolist()
    )
    monthly = [round(float(v), 2) for v in monthly]
    if len(monthly) < 12:
        avg = float(row["ghi_annual_kwh_m2"]) / 12.0
        monthly = (monthly + [round(avg, 2)] * 12)[:12]

    rank_df = df.sort_values("score_composite", ascending=False).reset_index(drop=True)
    rank = int(rank_df[rank_df["wilaya_code"] == code].index[0]) + 1

    yearly_df = helpers["yearly_df"]()
    yearly_rows = yearly_df[yearly_df["wilaya_code"] == code].sort_values("year")
    yearly_values = [float(v) for v in yearly_rows["ghi_annual_kwh_m2"].tolist()]
    yearly_years = [int(y) for y in yearly_rows["year"].tolist()]
    trend = helpers["classify_trend"](yearly_values)

    return {
        "code": code,
        "name": canonical,
        "region": helpers["region_for"](code),
        "climate": str(row["climate"]),
        "latitude": round(float(row["latitude"]), 4),
        "longitude": round(float(row["longitude"]), 4),
        "communes_count": int(row["communes_count"]),
        "ghi_annual": round(float(row["ghi_annual_kwh_m2"]), 1),
        "ghi_monthly": monthly,
        "national_monthly": helpers["national_monthly"](),
        "sunshine_hours_year": round(float(row["sunshine_hours_year"]), 0),
        "t_min": round(float(row["t_min"]), 1),
        "t_max": round(float(row["t_max"]), 1),
        "wind_speed": round(float(row["wind_speed"]), 2),
        "precip_mm": round(float(row["precip_annual_mm"]), 1),
        "potential_mw": round(float(row["potential_mw"]), 0),
        "score_composite": round(float(row["score_composite"]), 2),
        "score_ghi": round(float(row["score_ghi"]), 2),
        "score_stability": round(float(row["score_stability"]), 2),
        "score_accessibility": round(float(row["score_accessibility"]), 2),
        "score_risk_inverse": round(float(row["score_risk_inverse"]), 2),
        "rank": rank,
        "demand_mw_avg": round(float(row["demand_mw_avg"]), 2),
        "grid_distance_km": float(helpers["grid_distance"](row)),
        "yearly_years": yearly_years,
        "yearly_values": yearly_values,
        "trend": trend,
    }


def _classify_climate_risk(monthly: List[float]) -> Dict[str, Any]:
    """Risque climatique = écart-type des 12 valeurs mensuelles (Phase 3A)."""
    values = [float(v) for v in monthly if v is not None]
    if len(values) < 2:
        return {"std": None, "level": "Non disponible"}
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    if std < 20:
        level = "Faible"
    elif std <= 40:
        level = "Moyen"
    else:
        level = "Élevé"
    return {"std": round(std, 2), "level": level}


def _classify_grid_risk(distance_km: float) -> str:
    if distance_km is None:
        return "Non disponible"
    if distance_km < 20:
        return "Faible"
    if distance_km <= 100:
        return "Moyen"
    return "Élevé"


def _panel_type_for_climate(climate: str) -> str:
    """Recommandation de panneau selon le climat de la wilaya."""
    if not climate:
        return "Panneau monocristallin haute température (PERC)"
    c = climate.lower()
    if "sahar" in c or "desert" in c or "arid" in c or "bwh" in c or "bwk" in c:
        return "Monocristallin PERC haute température + verre anti-sable (climat saharien)"
    if "semi" in c or "bsh" in c or "bsk" in c:
        return "Monocristallin PERC adapté semi-aride"
    if "csa" in c or "csb" in c or "medit" in c:
        return "Monocristallin bifacial — climat méditerranéen"
    return "Monocristallin PERC (compromis multi-climat)"


# ─────────────────────────────────────────────────────────────────────────────
#  Calculs financiers (Phase 3D)
# ─────────────────────────────────────────────────────────────────────────────

def _roi_from_dataset(payload: Dict[str, Any], power_kwc: float = 100.0,
                     pr: float = 0.80) -> Dict[str, Any]:
    """Calcule un ROI complet à partir des données du dataset (Phase 3D)."""
    COST_DA_PER_KWC = 100000
    TARIFF_DA_PER_KWH = 5
    PROJECT_YEARS = 25
    DEGRADATION_PER_YEAR = 0.005
    CO2_KG_PER_KWH = 0.6

    # Ajustement risque climatique
    climate_risk = _classify_climate_risk(payload["ghi_monthly"])
    factor = 1.0
    if climate_risk["level"] == "Élevé":
        factor = 0.90
    elif climate_risk["level"] == "Moyen":
        factor = 0.95

    investment = power_kwc * COST_DA_PER_KWC
    annual_kwh_year1 = payload["ghi_annual"] * power_kwc * pr * factor
    annual_savings_year1 = annual_kwh_year1 * TARIFF_DA_PER_KWH
    co2_tons_year = (annual_kwh_year1 * CO2_KG_PER_KWH) / 1000

    cumulative = 0.0
    payback_years = None
    for year in range(1, PROJECT_YEARS + 1):
        prod = annual_kwh_year1 * ((1 - DEGRADATION_PER_YEAR) ** (year - 1))
        prev = cumulative
        cumulative += prod * TARIFF_DA_PER_KWH
        if prev < investment <= cumulative and payback_years is None:
            frac = (investment - prev) / (cumulative - prev or 1)
            payback_years = (year - 1) + frac

    if payback_years is None and annual_savings_year1 > 0:
        payback_years = investment / annual_savings_year1

    payback_year = int(payback_years) if payback_years is not None else None
    payback_month = (
        int(round((payback_years - payback_year) * 12))
        if payback_years is not None else None
    )
    if payback_month == 12 and payback_year is not None:
        payback_year += 1
        payback_month = 0

    return {
        "investment_da": investment,
        "production_year1_kwh": annual_kwh_year1,
        "savings_year1_da": annual_savings_year1,
        "payback_years": payback_years,
        "payback_year": payback_year,
        "payback_month": payback_month,
        "cumulative_25y_da": cumulative,
        "net_benefit_25y_da": cumulative - investment,
        "co2_tons_per_year": co2_tons_year,
        "performance_ratio": pr,
        "climate_factor": factor,
        "climate_risk": climate_risk,
    }


def _forecast_year_for_wilaya(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Réutilise les règles Phase 3C pour produire la prévision annuelle."""
    helpers = _load_dataset_helpers()
    horizon_meta = helpers["horizon_cfg"]["1an"]
    power_kwc = 100.0
    monthly_values = payload["ghi_monthly"][:12] or [payload["ghi_annual"] / 12.0] * 12
    production_kwh = [
        round(helpers["production_kwh"](v, power_kwc), 2)
        for v in monthly_values
    ]
    total = round(sum(production_kwh), 2)
    mean = total / 12 if production_kwh else 0
    mae = mean * (horizon_meta["mae_pct"] / 100.0)
    reliability = 0
    if mean > 0:
        reliability = max(0, min(100, int(round(100 - (mae / mean) * 100))))
    month_labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
    best_idx = max(range(12), key=lambda i: production_kwh[i])
    worst_idx = min(range(12), key=lambda i: production_kwh[i])
    return {
        "labels": month_labels,
        "production_kwh": production_kwh,
        "total_kwh": total,
        "reliability_pct": reliability,
        "best_month": {"label": month_labels[best_idx], "value": production_kwh[best_idx]},
        "worst_month": {"label": month_labels[worst_idx], "value": production_kwh[worst_idx]},
        "model_label": horizon_meta["model"],
    }


def _long_term_for_wilaya(payload: Dict[str, Any]) -> Dict[str, Any]:
    """5 années historiques + projection avec dégradation 0,5%/an."""
    helpers = _load_dataset_helpers()
    power_kwc = 100.0
    deg = 0.005
    years_hist = payload["yearly_years"][:]
    ghi_hist = payload["yearly_values"][:]
    if not ghi_hist:
        ghi_hist = [payload["ghi_annual"]]
        years_hist = [datetime.utcnow().year]
    last_year = years_hist[-1]
    base = ghi_hist[-1]

    historical_production = [
        round(helpers["production_kwh"](v, power_kwc), 2) for v in ghi_hist
    ]
    projection = []
    remaining = max(0, 10 - len(historical_production))
    for offset in range(1, remaining + 1):
        factor = (1 - deg) ** offset
        projection.append({
            "year": last_year + offset,
            "production_kwh": round(helpers["production_kwh"](base, power_kwc) * factor, 2),
            "type": "projection",
        })

    five_year_factor = (1 - deg) ** 5
    production_5y = round(helpers["production_kwh"](base, power_kwc) * five_year_factor, 2)

    series = [
        {"year": int(y), "production_kwh": p, "type": "historique"}
        for y, p in zip(years_hist, historical_production)
    ] + projection
    return {
        "series_10y": series[:10],
        "production_5y": production_5y,
        "trend": payload["trend"],
    }


def _build_region_summary(region: str) -> Dict[str, Any]:
    """Liste les wilayas d'une région avec leur GHI, score et classement intra."""
    helpers = _load_dataset_helpers()
    df = helpers["scores_df"]().copy()
    region_norm = (region or "").strip().lower()
    if not region_norm:
        return {"region": None, "wilayas": [], "avg_ghi": 0, "national_avg_ghi": float(df["ghi_annual_kwh_m2"].mean())}

    region_df = df[df["region"].str.lower() == region_norm].copy()
    if region_df.empty:
        # Fallback : prendre la région de la wilaya passée en argument (si jamais)
        info = helpers["resolve"](region)
        if info:
            region_label = helpers["region_for"](info["wilaya_code"])
            region_df = df[df["region"] == region_label].copy()
        else:
            return {"region": region, "wilayas": [], "avg_ghi": 0,
                    "national_avg_ghi": float(df["ghi_annual_kwh_m2"].mean())}

    region_df = region_df.sort_values("score_composite", ascending=False).reset_index(drop=True)
    items = []
    for idx, r in region_df.iterrows():
        items.append({
            "rank_intra": int(idx) + 1,
            "code": int(r["wilaya_code"]),
            "name": str(r["wilaya_name"]),
            "ghi": round(float(r["ghi_annual_kwh_m2"]), 1),
            "score": round(float(r["score_composite"]), 2),
            "potential_mw": round(float(r["potential_mw"]), 0),
        })

    return {
        "region": str(region_df["region"].iloc[0]),
        "wilayas": items,
        "avg_ghi": round(float(region_df["ghi_annual_kwh_m2"].mean()), 1),
        "national_avg_ghi": round(float(df["ghi_annual_kwh_m2"].mean()), 1),
        "total_potential_mw": round(float(region_df["potential_mw"].sum()), 0),
    }


def _build_national_top10() -> List[Dict[str, Any]]:
    helpers = _load_dataset_helpers()
    df = helpers["scores_df"]().copy().sort_values("score_composite", ascending=False).head(10).reset_index(drop=True)
    return [
        {
            "rank": int(i) + 1,
            "code": int(r["wilaya_code"]),
            "name": str(r["wilaya_name"]),
            "region": str(r["region"]),
            "ghi": round(float(r["ghi_annual_kwh_m2"]), 1),
            "score": round(float(r["score_composite"]), 2),
            "potential_mw": round(float(r["potential_mw"]), 0),
        }
        for i, r in df.iterrows()
    ]


def _build_region_distribution() -> List[Dict[str, Any]]:
    helpers = _load_dataset_helpers()
    df = helpers["scores_df"]().copy()
    grouped = df.groupby("region").agg(
        count=("wilaya_code", "count"),
        avg_ghi=("ghi_annual_kwh_m2", "mean"),
        total_potential=("potential_mw", "sum"),
        avg_grid_distance=("demand_mw_avg", "mean"),
    ).reset_index().sort_values("avg_ghi", ascending=False)
    items = []
    for _, r in grouped.iterrows():
        items.append({
            "region": str(r["region"]),
            "count": int(r["count"]),
            "avg_ghi": round(float(r["avg_ghi"]), 1),
            "total_potential_mw": round(float(r["total_potential"]), 0),
            # Distance moyenne approchée via le proxy demand → grid distance
            "avg_grid_distance_km": round(max(0.0, 200.0 - float(r["avg_grid_distance"]) * 2.0), 1),
        })
    return items


def _final_recommendation(payload: Dict[str, Any], roi: Dict[str, Any]) -> str:
    score = float(payload["score_composite"])
    ghi = float(payload["ghi_annual"])
    payback = roi["payback_years"]
    parts = []
    if score >= 75:
        parts.append(
            f"La wilaya de {payload['name']} présente un potentiel solaire très favorable "
            f"(score composite {score:.2f}/100). Le profil d'irradiation ({ghi:.1f} kWh/m²/an) "
            f"justifie un engagement d'investissement prioritaire."
        )
    elif score >= 60:
        parts.append(
            f"La wilaya de {payload['name']} affiche un potentiel solide "
            f"(score composite {score:.2f}/100) avec un GHI annuel de {ghi:.1f} kWh/m². "
            f"Le projet est recommandé sous réserve d'une étude technique de raccordement."
        )
    else:
        parts.append(
            f"La wilaya de {payload['name']} obtient un score modéré ({score:.2f}/100). "
            f"Il est conseillé d'approfondir l'étude de zone et d'évaluer les contraintes "
            f"avant tout engagement financier."
        )

    if payback is not None and payback > 0:
        parts.append(
            f"Le retour sur investissement estimé est de {payback:.2f} années dans les conditions "
            f"de marché algérien actuelles (100 000 DA/kWc, 5 DA/kWh)."
        )
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
#  Générateur PDF
# ─────────────────────────────────────────────────────────────────────────────

class ReportGenerator:
    """Génère 3 rapports PDF distincts à partir des données réelles du dataset."""

    REPORT_TYPES = ("investor", "government", "technical")

    # ----- styles partagés ---------------------------------------------------

    def _styles(self):
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            "DocTitle", parent=styles["Heading1"], fontSize=22,
            textColor=_DARK, alignment=TA_CENTER, spaceAfter=8,
        ))
        styles.add(ParagraphStyle(
            "DocSubtitle", parent=styles["Normal"], fontSize=11,
            textColor=colors.grey, alignment=TA_CENTER, spaceAfter=18,
        ))
        styles.add(ParagraphStyle(
            "SectionH", parent=styles["Heading2"], fontSize=14,
            textColor=_PRIMARY, spaceBefore=14, spaceAfter=10,
        ))
        styles.add(ParagraphStyle(
            "Body", parent=styles["BodyText"], fontSize=10,
            alignment=TA_JUSTIFY, leading=14, spaceAfter=6,
        ))
        styles.add(ParagraphStyle(
            "Small", parent=styles["BodyText"], fontSize=9,
            textColor=colors.grey, spaceAfter=4,
        ))
        return styles

    def _kv_table(self, rows: List[List[str]], col_widths=None):
        col_widths = col_widths or [6 * cm, 9 * cm]
        table = Table(rows, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), _GRAY_BG),
            ("TEXTCOLOR", (0, 0), (-1, -1), _DARK),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ]))
        return table

    def _data_table(self, headers: List[str], rows: List[List[str]],
                    col_widths=None):
        data = [headers] + rows
        col_widths = col_widths or [3.5 * cm] * len(headers)
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9.5),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#f9fafb")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _header(self, story, styles, title: str, subtitle: str):
        story.append(Paragraph(title, styles["DocTitle"]))
        story.append(Paragraph(subtitle, styles["DocSubtitle"]))
        story.append(Spacer(1, 0.2 * cm))

    def _section(self, story, styles, label: str):
        story.append(Paragraph(label, styles["SectionH"]))

    def _footer(self, story, styles, label: str):
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(
            f"<i>{label} — généré par SolarDecide DZ le "
            f"{datetime.utcnow().strftime('%d/%m/%Y')} — données issues du dataset .parquet</i>",
            styles["Small"],
        ))

    # ----- API publique ------------------------------------------------------

    def generate(
        self,
        report_type: str,
        wilaya: Optional[str] = None,
        region: Optional[str] = None,
        power_kwc: float = 100.0,
        roi_data: Optional[Dict] = None,
        title: Optional[str] = None,
    ) -> BytesIO:
        if not REPORTLAB_AVAILABLE:
            return self._fallback_pdf(
                title or f"Rapport {report_type}",
                report_type, wilaya, region, power_kwc, roi_data,
            )

        report_type = (report_type or "investor").lower().strip()
        if report_type not in self.REPORT_TYPES:
            report_type = "investor"

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        story: List[Any] = []
        styles = self._styles()

        if report_type == "investor":
            self._build_investor(story, styles, wilaya, power_kwc, roi_data,
                                 title=title)
        elif report_type == "government":
            self._build_government(story, styles, region, wilaya, title=title)
        else:  # technical
            self._build_technical(story, styles, wilaya, power_kwc, title=title)

        doc.build(story)
        buffer.seek(0)
        return buffer

    # ─────────────────────────────────────────────────────────────────────
    #  RAPPORT 1 — INVESTISSEUR
    # ─────────────────────────────────────────────────────────────────────

    def _build_investor(self, story, styles, wilaya: str, power_kwc: float,
                        roi_data: Optional[Dict], title: Optional[str] = None):
        if not wilaya:
            raise ValueError("Le rapport investisseur exige une wilaya.")
        payload = _wilaya_dataset_payload(wilaya)

        pr = 0.80
        if roi_data and roi_data.get("performance_ratio"):
            try:
                pr = float(roi_data.get("performance_ratio"))
            except (TypeError, ValueError):
                pr = 0.80

        # Si la page ROI fournit déjà des résultats, on les réutilise tels quels.
        if roi_data and roi_data.get("investment_da"):
            roi = {
                "investment_da": float(roi_data.get("investment_da") or 0),
                "production_year1_kwh": float(roi_data.get("production_year1_kwh") or 0),
                "savings_year1_da": float(roi_data.get("savings_year1_da") or 0),
                "payback_years": float(roi_data.get("payback_years"))
                                  if roi_data.get("payback_years") not in (None, "") else None,
                "payback_year": None,
                "payback_month": None,
                "cumulative_25y_da": None,
                "net_benefit_25y_da": float(roi_data.get("net_benefit_25y_da") or 0),
                "co2_tons_per_year": float(roi_data.get("co2_tons_per_year") or 0),
                "performance_ratio": pr,
                "climate_factor": float(roi_data.get("climate_factor") or 1.0),
                "climate_risk": _classify_climate_risk(payload["ghi_monthly"]),
            }
            if roi["payback_years"] is not None:
                py = int(roi["payback_years"])
                pm = int(round((roi["payback_years"] - py) * 12))
                if pm == 12:
                    py += 1
                    pm = 0
                roi["payback_year"], roi["payback_month"] = py, pm
        else:
            roi = _roi_from_dataset(payload, power_kwc=power_kwc, pr=pr)

        forecast = _forecast_year_for_wilaya(payload)
        long_term = _long_term_for_wilaya(payload)
        climate_risk = roi["climate_risk"]
        grid_level = _classify_grid_risk(payload["grid_distance_km"])

        # En-tête
        self._header(
            story, styles,
            title or f"Rapport Investisseur — Wilaya de {payload['name']}",
            "Analyse financière & risques solaire basée sur le dataset .parquet",
        )

        # Section 1
        self._section(story, styles, "Section 1 — Résumé de la zone")
        story.append(self._kv_table([
            ["Wilaya", f"{payload['name']} (code {payload['code']})"],
            ["Région", payload["region"]],
            ["Coordonnées GPS", f"{payload['latitude']}°, {payload['longitude']}°"],
            ["Type de climat", payload["climate"]],
            ["GHI annuel", f"{_fmt_num(payload['ghi_annual'], 1)} kWh/m²"],
            ["Potentiel solaire estimé", f"{_fmt_int(payload['potential_mw'])} MW"],
            ["Score composite", f"{_fmt_num(payload['score_composite'], 2)} / 100"],
            ["Classement national", f"#{payload['rank']} sur 58 wilayas"],
        ]))

        # Section 2
        self._section(story, styles, "Section 2 — Potentiel solaire réel")
        month_labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
        rows = []
        for i in range(12):
            wilaya_val = payload["ghi_monthly"][i] if i < len(payload["ghi_monthly"]) else None
            nat_val = payload["national_monthly"][i] if i < len(payload["national_monthly"]) else None
            delta = (wilaya_val - nat_val) if (wilaya_val is not None and nat_val is not None) else None
            rows.append([
                month_labels[i],
                f"{_fmt_num(wilaya_val, 1)}",
                f"{_fmt_num(nat_val, 1)}",
                f"{('+' if (delta or 0) >= 0 else '')}{_fmt_num(delta, 1)}",
            ])
        story.append(self._data_table(
            ["Mois", "GHI wilaya", "GHI national", "Écart"],
            rows,
            col_widths=[2.8 * cm, 4 * cm, 4 * cm, 4 * cm],
        ))
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(
            f"Ensoleillement annuel : <b>{_fmt_int(payload['sunshine_hours_year'])} heures</b>.",
            styles["Body"],
        ))

        # Section 3
        self._section(story, styles, "Section 3 — Calcul ROI détaillé")
        payback_text = (
            f"{roi['payback_year']} ans et {roi['payback_month']} mois"
            if roi["payback_years"] is not None and roi["payback_year"] is not None
            else "Non atteint sur 25 ans"
        )
        story.append(self._kv_table([
            ["Puissance projetée", f"{_fmt_num(power_kwc, 0)} kWc"],
            ["Investissement total", _fmt_da(roi["investment_da"])],
            ["Production annuelle estimée (an 1)", f"{_fmt_int(roi['production_year1_kwh'])} kWh"],
            ["Économies annuelles", _fmt_da(roi["savings_year1_da"])],
            ["Payback period", payback_text],
            ["Bénéfice net sur 25 ans", _fmt_da(roi["net_benefit_25y_da"])],
            ["Performance ratio appliqué", f"{roi['performance_ratio']:.2f}"],
            ["Ajustement risque climatique", f"× {roi['climate_factor']:.2f}"],
        ]))

        # Section 4
        self._section(story, styles, "Section 4 — Analyse des risques")
        env_text = (
            "Non disponible — le dataset .parquet actuel ne contient pas "
            "de champ explicite sur les zones protégées ou agricoles."
        )
        access_text = (
            "Non disponible — le dataset .parquet actuel ne contient pas "
            "de champ explicite sur la distance aux routes."
        )
        std_txt = f" (écart-type GHI mensuel = {climate_risk['std']})" if climate_risk["std"] is not None else ""
        story.append(self._kv_table([
            ["Risque climatique", f"{climate_risk['level']}{std_txt}"],
            ["Risque d'accès", access_text],
            ["Risque réseau",
             f"{grid_level} — distance estimée {_fmt_num(payload['grid_distance_km'], 1)} km"],
            ["Risque environnemental", env_text],
        ]))

        # Section 5
        self._section(story, styles, "Section 5 — Prévision de production")
        story.append(Paragraph(
            f"Prévision de production sur 12 mois pour une installation de référence "
            f"100 kWc avec PR 0,80 (modèle backend : {forecast['model_label']}).",
            styles["Body"],
        ))
        story.append(self._data_table(
            ["Mois", "Production estimée (kWh)"],
            [[lbl, _fmt_int(v)] for lbl, v in zip(forecast["labels"], forecast["production_kwh"])],
            col_widths=[6 * cm, 6 * cm],
        ))
        story.append(Spacer(1, 0.3 * cm))
        story.append(self._kv_table([
            ["Production annuelle totale (réf. 100 kWc)", f"{_fmt_int(forecast['total_kwh'])} kWh"],
            ["Meilleur mois", f"{forecast['best_month']['label']} ({_fmt_int(forecast['best_month']['value'])} kWh)"],
            ["Mois le plus faible",
             f"{forecast['worst_month']['label']} ({_fmt_int(forecast['worst_month']['value'])} kWh)"],
            ["Fiabilité estimée", f"{forecast['reliability_pct']}%"],
            ["Tendance sur 5 ans",
             f"{long_term['trend']['label']} — production à 5 ans estimée à {_fmt_int(long_term['production_5y'])} kWh"],
        ]))

        # Section 6
        self._section(story, styles, "Section 6 — Recommandation finale")
        story.append(Paragraph(_final_recommendation(payload, roi), styles["Body"]))

        self._footer(story, styles, "Rapport Investisseur")

    # ─────────────────────────────────────────────────────────────────────
    #  RAPPORT 2 — GOUVERNEMENT / INSTITUTIONNEL
    # ─────────────────────────────────────────────────────────────────────

    def _build_government(self, story, styles, region: Optional[str],
                          wilaya: Optional[str], title: Optional[str] = None):
        if not region and wilaya:
            try:
                ref_payload = _wilaya_dataset_payload(wilaya)
                region = ref_payload["region"]
            except Exception:
                region = None

        if not region:
            raise ValueError("Le rapport gouvernemental exige une région ou une wilaya.")

        region_data = _build_region_summary(region)
        top10 = _build_national_top10()
        distribution = _build_region_distribution()

        # En-tête
        self._header(
            story, styles,
            title or f"Rapport Institutionnel — Région {region_data['region']}",
            "Synthèse régionale et nationale du potentiel solaire algérien",
        )

        # Section 1
        self._section(story, styles, "Section 1 — Analyse régionale")
        rows = [
            [str(item["rank_intra"]), item["name"], _fmt_num(item["ghi"], 1),
             _fmt_num(item["score"], 2), _fmt_int(item["potential_mw"])]
            for item in region_data["wilayas"]
        ]
        story.append(self._data_table(
            ["Rang", "Wilaya", "GHI (kWh/m²)", "Score", "Potentiel (MW)"],
            rows,
            col_widths=[1.8 * cm, 4 * cm, 4 * cm, 2.5 * cm, 3.7 * cm],
        ))
        story.append(Spacer(1, 0.3 * cm))
        story.append(self._kv_table([
            ["GHI moyen de la région",
             f"{_fmt_num(region_data['avg_ghi'], 1)} kWh/m²"],
            ["GHI moyen national",
             f"{_fmt_num(region_data['national_avg_ghi'], 1)} kWh/m²"],
            ["Écart vs national",
             f"{('+' if region_data['avg_ghi'] >= region_data['national_avg_ghi'] else '')}"
             f"{_fmt_num(region_data['avg_ghi'] - region_data['national_avg_ghi'], 1)} kWh/m²"],
            ["Nombre de wilayas dans la région", str(len(region_data["wilayas"]))],
            ["Potentiel cumulé de la région",
             f"{_fmt_int(region_data['total_potential_mw'])} MW"],
        ]))

        # Section 2
        self._section(story, styles, "Section 2 — Potentiel national")
        story.append(Paragraph(
            "Top 10 des wilayas algériennes par score composite, à partir du dataset officiel.",
            styles["Body"],
        ))
        top_rows = [
            [str(item["rank"]), item["name"], item["region"],
             _fmt_num(item["ghi"], 1), _fmt_num(item["score"], 2), _fmt_int(item["potential_mw"])]
            for item in top10
        ]
        story.append(self._data_table(
            ["#", "Wilaya", "Région", "GHI", "Score", "Potentiel (MW)"],
            top_rows,
            col_widths=[1.2 * cm, 3.5 * cm, 3.5 * cm, 2.5 * cm, 2.2 * cm, 3 * cm],
        ))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("Répartition du potentiel par région (dataset .parquet).",
                               styles["Body"]))
        dist_rows = [
            [item["region"], str(item["count"]),
             _fmt_num(item["avg_ghi"], 1), _fmt_int(item["total_potential_mw"]),
             _fmt_num(item["avg_grid_distance_km"], 1)]
            for item in distribution
        ]
        story.append(self._data_table(
            ["Région", "Wilayas", "GHI moyen", "Potentiel (MW)", "Dist. réseau (km)"],
            dist_rows,
            col_widths=[3.5 * cm, 1.8 * cm, 3 * cm, 3.5 * cm, 4 * cm],
        ))

        # Section 3
        self._section(story, styles, "Section 3 — État de l'infrastructure")
        infra_rows = [
            [item["region"],
             _fmt_num(item["avg_grid_distance_km"], 1),
             _fmt_num(item["avg_ghi"], 1),
             _fmt_int(item["total_potential_mw"])]
            for item in distribution
        ]
        story.append(self._data_table(
            ["Région", "Distance moyenne réseau (km)", "GHI moyen", "Potentiel (MW)"],
            infra_rows,
            col_widths=[3.5 * cm, 5 * cm, 3 * cm, 4 * cm],
        ))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            "Note : la distance routière n'est pas explicitement exposée par le dataset "
            "actuel ; seul un proxy de distance au réseau électrique est calculé à partir "
            "de la demande moyenne (MW) de chaque région.",
            styles["Small"],
        ))

        # Section 4
        self._section(story, styles, "Section 4 — Zones prioritaires recommandées")
        priority = top10[:5]
        for item in priority:
            story.append(Paragraph(
                f"<b>{item['rank']}. {item['name']}</b> ({item['region']}) — score {item['score']:.2f}/100. "
                f"GHI annuel {item['ghi']:.1f} kWh/m², potentiel estimé {int(item['potential_mw'])} MW. "
                f"Justification : excellent score composite combinant irradiation, stabilité, "
                f"accessibilité et risque inverse calculés sur l'ensemble du dataset.",
                styles["Body"],
            ))

        # Section 5
        self._section(story, styles, "Section 5 — Prévisions et tendances")
        helpers = _load_dataset_helpers()
        for item in priority:
            try:
                p = _wilaya_dataset_payload(item["name"])
                trend = p["trend"]
                story.append(Paragraph(
                    f"<b>{item['name']}</b> : tendance climatique « {trend['label']} » "
                    f"(pente {trend['slope_pct_per_year']}%/an sur les années du dataset).",
                    styles["Body"],
                ))
            except Exception:
                continue
        helpers_scores = helpers["scores_df"]()
        total_potential_mw = float(helpers_scores["potential_mw"].sum())
        national_avg_ghi = float(helpers_scores["ghi_annual_kwh_m2"].mean())
        # Production potentielle nationale = 100% du potentiel installé × heures équivalentes pleine puissance
        eq_full_hours = national_avg_ghi * 0.80
        national_production_kwh = total_potential_mw * 1000 * eq_full_hours / 1000  # MWh implicit
        story.append(Spacer(1, 0.2 * cm))
        story.append(self._kv_table([
            ["Potentiel solaire national cumulé",
             f"{_fmt_int(total_potential_mw)} MW"],
            ["GHI national moyen",
             f"{_fmt_num(national_avg_ghi, 1)} kWh/m²"],
            ["Production potentielle nationale estimée (PR 0,80)",
             f"{_fmt_int(national_production_kwh)} MWh/an"],
        ]))

        # Section 6
        self._section(story, styles, "Section 6 — Plan d'action suggéré")
        actions = [
            f"Concentrer les premiers programmes utility-scale sur le Top 5 national, "
            f"à commencer par {priority[0]['name']} et {priority[1]['name']} (scores > 70/100).",
            f"Renforcer le maillage réseau dans les régions affichant une distance moyenne "
            f"supérieure à 100 km au réseau électrique.",
            "Lancer des appels à projets dédiés aux régions à GHI très élevé "
            "mais à faible accessibilité actuelle.",
            "Mettre en place un suivi annuel des tendances climatiques par wilaya, "
            "en s'appuyant sur la pente du GHI annuel exposée par le backend.",
        ]
        for line in actions:
            story.append(Paragraph(f"• {line}", styles["Body"]))

        self._footer(story, styles, "Rapport Gouvernemental")

    # ─────────────────────────────────────────────────────────────────────
    #  RAPPORT 3 — PERSPECTIVES TECHNIQUES
    # ─────────────────────────────────────────────────────────────────────

    def _build_technical(self, story, styles, wilaya: str, power_kwc: float,
                         title: Optional[str] = None):
        if not wilaya:
            raise ValueError("Le rapport technique exige une wilaya.")
        if not (power_kwc and power_kwc > 0):
            raise ValueError("Le rapport technique exige une puissance projet > 0 kWc.")

        payload = _wilaya_dataset_payload(wilaya)
        climate_risk = _classify_climate_risk(payload["ghi_monthly"])
        grid_level = _classify_grid_risk(payload["grid_distance_km"])

        # Dimensionnement
        surface_min = power_kwc * 6.0
        surface_max = power_kwc * 8.0
        # Onduleur typique 0,95 × kWc (puissance crête onduleur en kVA)
        inverter_kva = power_kwc * 0.95
        # Configuration sommaire : nombre de chaînes & panneaux
        # On suppose des modules 550 Wc → nombre de modules
        module_wp = 550
        modules_count = math.ceil((power_kwc * 1000) / module_wp)
        strings_count = max(1, math.ceil(modules_count / 24))
        production_estimated_kwh = payload["ghi_annual"] * power_kwc * 0.80

        # En-tête
        self._header(
            story, styles,
            title or f"Perspectives Techniques — Wilaya de {payload['name']}",
            f"Projet solaire {_fmt_num(power_kwc, 0)} kWc — étude technique préliminaire",
        )

        # Section 1
        self._section(story, styles, "Section 1 — Spécifications équipement recommandé")
        panel_type = _panel_type_for_climate(payload["climate"])
        story.append(self._kv_table([
            ["Type de panneaux recommandé", panel_type],
            ["Module unitaire (référence)", f"{module_wp} Wc monocristallin PERC"],
            ["Puissance onduleur recommandée", f"{_fmt_num(inverter_kva, 1)} kVA (ratio DC/AC ≈ 1,05)"],
            ["Configuration système",
             f"{modules_count} modules ≈ {strings_count} string(s) onduleur(s)"],
            ["Performance ratio cible", "0,80"],
            ["Compatibilité climatique",
             f"Climat {payload['climate']} — Tmax mesurée {_fmt_num(payload['t_max'], 1)} °C, "
             f"Tmin mesurée {_fmt_num(payload['t_min'], 1)} °C"],
        ]))

        # Section 2
        self._section(story, styles, "Section 2 — Dimensionnement")
        story.append(self._kv_table([
            ["Puissance à installer", f"{_fmt_num(power_kwc, 0)} kWc"],
            ["Surface nécessaire",
             f"{_fmt_int(surface_min)} m² à {_fmt_int(surface_max)} m² "
             f"(ratio 6 à 8 m²/kWc)"],
            ["Puissance installable / m² disponible",
             "0,125 à 0,167 kWc/m² (selon densité d'occupation)"],
            ["Production annuelle estimée",
             f"{_fmt_int(production_estimated_kwh)} kWh "
             f"(GHI {_fmt_num(payload['ghi_annual'], 1)} kWh/m² × kWc × 0,80)"],
        ]))

        # Section 3
        self._section(story, styles, "Section 3 — Étude de faisabilité")
        std_txt = f"écart-type GHI mensuel {climate_risk['std']}" if climate_risk["std"] is not None else "non disponible"
        story.append(self._kv_table([
            ["Score composite de la zone",
             f"{_fmt_num(payload['score_composite'], 2)} / 100 (rang #{payload['rank']})"],
            ["Risque climatique", f"{climate_risk['level']} ({std_txt})"],
            ["Risque réseau",
             f"{grid_level} — {_fmt_num(payload['grid_distance_km'], 1)} km estimés au réseau"],
            ["Risque d'accès (routes)",
             "Donnée non présente dans le dataset .parquet actuel"],
            ["Conditions d'installation",
             f"Climat {payload['climate']}, vents moyens {_fmt_num(payload['wind_speed'], 2)} m/s, "
             f"précipitations annuelles {_fmt_num(payload['precip_mm'], 1)} mm"],
        ]))

        # Section 4
        self._section(story, styles, "Section 4 — Contraintes et solutions")
        constraints: List[List[str]] = []
        if climate_risk["level"] == "Élevé":
            constraints.append([
                "Forte variabilité climatique mensuelle (GHI σ > 40)",
                "Sur-dimensionner légèrement le générateur (10%) ; suivi PR mensuel ; "
                "modules à coefficient de température bas."
            ])
        elif climate_risk["level"] == "Moyen":
            constraints.append([
                "Variabilité climatique modérée (GHI σ entre 20 et 40)",
                "Conserver le PR cible 0,80 ; monitoring trimestriel ; "
                "calibrer scénarios financiers sur P75."
            ])
        else:
            constraints.append([
                "Variabilité climatique faible",
                "Conditions favorables — privilégier l'optimisation du LCOE."
            ])

        if grid_level == "Élevé":
            constraints.append([
                f"Distance estimée au réseau {_fmt_num(payload['grid_distance_km'], 1)} km",
                "Étudier solution hybride (stockage BESS) ; négocier extension HTB ; "
                "envisager site captif si demande locale identifiable."
            ])
        elif grid_level == "Moyen":
            constraints.append([
                f"Distance modérée au réseau ({_fmt_num(payload['grid_distance_km'], 1)} km)",
                "Confirmer la disponibilité de poste source proche ; étude raccordement HTA."
            ])
        else:
            constraints.append([
                "Bonne proximité du réseau électrique",
                "Procéder à une étude de raccordement standard ; pas de stockage requis."
            ])

        if "sahar" in payload["climate"].lower() or payload["t_max"] >= 45:
            constraints.append([
                "Stress thermique fort (Tmax élevée, climat saharien)",
                "Modules à coefficient de température bas ; structures ventilées ; "
                "nettoyage régulier anti-poussière."
            ])

        if payload["wind_speed"] >= 5:
            constraints.append([
                f"Vents soutenus (moyenne {_fmt_num(payload['wind_speed'], 2)} m/s)",
                "Renforcer la fixation des structures ; calcul de charges vent classe II minimum."
            ])

        if not constraints:
            constraints.append([
                "Aucune contrainte critique identifiée dans le dataset",
                "Procéder selon les standards d'installation utility-scale."
            ])

        story.append(self._data_table(
            ["Contrainte identifiée", "Solution proposée"],
            constraints,
            col_widths=[7 * cm, 9 * cm],
        ))

        self._footer(story, styles, "Perspectives Techniques")

    # ─────────────────────────────────────────────────────────────────────
    #  Fallback PDF (si reportlab indisponible)
    # ─────────────────────────────────────────────────────────────────────

    def _fallback_pdf(self, title, report_type, wilaya, region, power_kwc, roi_data) -> BytesIO:
        lines = [
            str(title),
            "",
            f"Type de rapport : {report_type}",
            f"Wilaya : {wilaya or '-'}",
            f"Région : {region or '-'}",
            f"Puissance projet : {power_kwc} kWc",
        ]
        if roi_data:
            lines.append("")
            lines.append("ROI :")
            for k, v in roi_data.items():
                lines.append(f"  {k}: {v}")
        text = "\n".join(_normalize_ascii(line) for line in lines)
        body = text.encode("latin-1", "ignore")
        pdf = (
            b"%PDF-1.1\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
            b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"5 0 obj<</Length " + str(len(body) + 40).encode("ascii") + b">>stream\n"
            b"BT /F1 11 Tf 40 800 Td (" + body.replace(b"(", b"\\(").replace(b")", b"\\)").replace(b"\n", b") Tj 0 -14 Td (") + b") Tj ET\n"
            b"endstream endobj\n"
            b"xref\n0 6\n0000000000 65535 f \n"
            b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
        )
        return BytesIO(pdf)
