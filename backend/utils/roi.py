"""
ROI Calculator
Algorithme complet de rentabilité financière pour projets solaires en Algérie.

Formule du ROI utilisée (standard financier) :
    ROI (%) = [(Gain total de l'investissement − Coût total de l'investissement) / Coût total] × 100

où :
    • Gain total = Σ (revenus annuels actualisés sur la durée de vie du projet)
    • Coût total = CAPEX + Σ (OPEX annuels actualisés)

En complément, on calcule aussi :
    • NPV  : Valeur Actuelle Nette
    • IRR  : Taux de Rendement Interne
    • LCOE : Coût actualisé de l'énergie
    • Payback : période de retour sur investissement
"""

import numpy as np
import numpy_financial as npf
from typing import Optional, Dict, Any


class ROICalculator:
    """
    Calcule ROI, NPV, IRR, LCOE et payback pour un projet solaire.
    Tous les calculs sont en dinars algériens (DZD) avec données du marché algérien.
    """

    # ────────────────────────────────────────────────────────────────────
    # CONSTANTES ALGÉRIENNES (à jour 2025)
    # ────────────────────────────────────────────────────────────────────

    # CAPEX par MW (investissement initial) en DZD
    CAPEX_DZD_PAR_MW = {
        "ground_mount": 180_000_000,   # 180M DZD/MW (selon projets SKTM)
        "rooftop":      220_000_000,   # Plus cher (toiture)
        "hybrid":       200_000_000,   # Hybrid (sol + toiture)
    }

    # Tarifs de rachat électricité (DZD/kWh) — 3 scénarios
    TARIF_DZD_KWH = {
        "bas":   22.5,   # Pessimiste : tarif bas Sonelgaz
        "moyen": 30.0,   # Base : tarif actuel moyen (PPA national)
        "eleve": 40.0,   # Optimiste : contrats export/PPA long terme
    }

    # Paramètres opérationnels
    OPEX_PCT_CAPEX    = 0.015   # OPEX = 1.5% CAPEX/an (maintenance, nettoyage, assurance)
    DEGRADATION       = 0.005   # Perte annuelle 0.5% (standard constructeur)
    DISCOUNT_RATE     = 0.08    # Taux d'actualisation 8% (standard énergie Algérie)
    LIFETIME_YEARS    = 25      # Durée de vie standard
    DEBT_RATIO        = 0.70
    EQUITY_RATIO      = 0.30
    BANK_RATE         = 0.06
    PERFORMANCE_RATIO = 0.75
    TEMP_COEFF        = -0.004
    CO2_FACTOR        = 0.5
    CONSUMPTION_PER_HOUSEHOLD = 3.5

    def __init__(
        self,
        capacity_mw: float,
        ghi_annual: float,
        temp_avg: float,
        tariff_scenario: str = "moyen",
        installation_type: str = "ground_mount",
        lifetime_years: int = 25,
        inflation_rate: float = 0.02,
    ):
        """
        Initialise le calculateur ROI.

        Args:
            capacity_mw     : capacité installée en MW
            ghi_annual      : Global Horizontal Irradiance annuelle (kWh/m²/an)
            temp_avg        : température moyenne annuelle (°C)
            tariff_scenario : 'bas', 'moyen', ou 'eleve'
            installation_type : 'ground_mount', 'rooftop', ou 'hybrid'
            lifetime_years  : durée de vie du projet (défaut 25 ans)
            inflation_rate  : taux d'inflation annuel (défaut 2%)
        """
        self.capacity_mw = capacity_mw
        self.ghi_annual  = ghi_annual
        self.temp_avg    = temp_avg
        self.tariff      = self.TARIF_DZD_KWH.get(tariff_scenario, self.TARIF_DZD_KWH["moyen"])
        self.install_type = installation_type
        self.lifetime    = lifetime_years
        self.inflation   = inflation_rate

        # Validation des entrées
        if capacity_mw <= 0:
            raise ValueError("Capacity must be positive")
        if ghi_annual <= 0:
            raise ValueError("GHI must be positive")
        if tariff_scenario not in self.TARIF_DZD_KWH:
            raise ValueError(f"Tariff must be one of {list(self.TARIF_DZD_KWH.keys())}")

    # ────────────────────────────────────────────────────────────────────
    # CALCULS INTERMÉDIAIRES
    # ────────────────────────────────────────────────────────────────────

    def _compute_year1_production(self) -> float:
        """Production de la 1ère année avec correction température (MWh)."""
        # Production brute : capacité × GHI × performance ratio
        yield_raw = self.capacity_mw * self.ghi_annual * self.PERFORMANCE_RATIO  # MWh/an

        # Correction température (coefficient négatif, perte seulement si T > 25°C)
        temp_loss = max(0.0, (self.temp_avg - 25.0) * abs(self.TEMP_COEFF))
        # Bornage : perte max 15% (sécurité numérique)
        temp_loss = min(temp_loss, 0.15)

        yield_corrected = yield_raw * (1.0 - temp_loss)
        return yield_corrected

    def _compute_capex(self) -> Dict[str, float]:
        """Décomposition du CAPEX (total, dette, capitaux propres)."""
        capex_rate  = self.CAPEX_DZD_PAR_MW[self.install_type]
        capex_total = self.capacity_mw * capex_rate
        return {
            "total":  capex_total,
            "debt":   capex_total * self.DEBT_RATIO,
            "equity": capex_total * self.EQUITY_RATIO,
        }

    def _compute_revenues_and_opex(self, yield_an1: float, opex_annual: float):
        """
        Sépare revenus et OPEX (utile pour le ROI brut et l'affichage frontend).

        Returns:
            revenues_per_year : list[float]  — revenus bruts par an (DZD)
            opex_per_year     : list[float]  — OPEX par an (DZD)
            cashflows         : list[float]  — flux de trésorerie nets (revenus − OPEX)
        """
        revenues = []
        opex_list = []
        cashflows = []

        for year in range(1, self.lifetime + 1):
            production = yield_an1 * (1 - self.DEGRADATION) ** (year - 1)
            tariff_inflated = self.tariff * (1 + self.inflation) ** (year - 1)
            # Revenu = production (MWh) × tarif (DZD/kWh) × 1000
            revenue = production * tariff_inflated * 1000

            revenues.append(revenue)
            opex_list.append(opex_annual)
            cashflows.append(revenue - opex_annual)

        return revenues, opex_list, cashflows

    def _compute_npv(self, capex: float, cashflows: list) -> float:
        """Valeur Actuelle Nette (NPV)."""
        cf_array = [-capex] + cashflows
        return float(sum(cf / (1 + self.DISCOUNT_RATE) ** t for t, cf in enumerate(cf_array)))

    def _compute_irr(self, capex: float, cashflows: list) -> float:
        """Taux de Rendement Interne (IRR)."""
        cf_array = [-capex] + cashflows
        try:
            irr = npf.irr(cf_array)
            return float(irr) if irr is not None and not np.isnan(irr) else 0.0
        except Exception:
            return 0.0

    def _compute_payback(self, capex: float, cashflows: list) -> Optional[float]:
        """Période de retour (en années). Renvoie None si jamais rentabilisé."""
        cumul = -capex
        for year, cf in enumerate(cashflows, 1):
            cumul_prev = cumul
            cumul += cf
            if cumul >= 0:
                # Interpolation linéaire pour avoir une fraction d'année
                if cf > 0:
                    fraction = -cumul_prev / cf
                    return float(year - 1 + fraction)
                return float(year)
        return None

    def _compute_lcoe(self, capex: float, opex_annual: float, yield_an1: float) -> float:
        """LCOE = coût total actualisé / production totale actualisée (DZD/kWh)."""
        total_prod_discounted = sum(
            yield_an1 * (1 - self.DEGRADATION) ** t / (1 + self.DISCOUNT_RATE) ** (t + 1)
            for t in range(self.lifetime)
        )
        total_cost_discounted = capex + sum(
            opex_annual / (1 + self.DISCOUNT_RATE) ** t
            for t in range(1, self.lifetime + 1)
        )
        return total_cost_discounted / (total_prod_discounted * 1000)

    def _compute_co2_avoided(self, yield_an1: float) -> float:
        """CO2 évité sur toute la durée de vie (tonnes)."""
        total_kwh = sum(
            yield_an1 * (1 - self.DEGRADATION) ** t * 1000
            for t in range(self.lifetime)
        )
        return (total_kwh * self.CO2_FACTOR) / 1000  # kg → tonnes

    def _compute_households(self, yield_an1: float) -> int:
        """Nombre de foyers algériens alimentables sur 1 an."""
        return int(yield_an1 * 1000 / self.CONSUMPTION_PER_HOUSEHOLD)

    # ────────────────────────────────────────────────────────────────────
    # ROI BRUT — formule classique demandée
    # ────────────────────────────────────────────────────────────────────

    def _compute_roi(
        self,
        capex: float,
        revenues: list,
        opex_list: list,
        actualise: bool = True,
    ) -> Dict[str, float]:
        """
        Calcule le ROI selon la formule classique :

            ROI (%) = [(Gain − Coût) / Coût] × 100

        où :
            Gain   = Σ revenus (actualisés si actualise=True)
            Coût   = CAPEX + Σ OPEX (actualisés si actualise=True)
            Profit = Gain − Coût

        Args:
            capex      : investissement initial (DZD)
            revenues   : liste des revenus annuels (DZD)
            opex_list  : liste des OPEX annuels (DZD)
            actualise  : si True, actualise les flux au taux DISCOUNT_RATE

        Returns:
            Dict avec total_revenue_dzd, total_cost_dzd, net_profit_dzd, roi_pct
            + version "simple" (non actualisée) pour affichage
        """
        # ── Version actualisée (valeurs financières correctes)
        if actualise:
            total_revenue = sum(
                r / (1 + self.DISCOUNT_RATE) ** (t + 1)
                for t, r in enumerate(revenues)
            )
            total_opex = sum(
                o / (1 + self.DISCOUNT_RATE) ** (t + 1)
                for t, o in enumerate(opex_list)
            )
        else:
            total_revenue = sum(revenues)
            total_opex    = sum(opex_list)

        total_cost   = capex + total_opex
        net_profit   = total_revenue - total_cost
        roi_pct      = (net_profit / total_cost) * 100 if total_cost > 0 else 0.0

        # ── Version simple (somme brute, non actualisée) — utile pour l'affichage utilisateur
        gross_revenue = sum(revenues)
        gross_cost    = capex + sum(opex_list)
        gross_profit  = gross_revenue - gross_cost
        gross_roi_pct = (gross_profit / gross_cost) * 100 if gross_cost > 0 else 0.0

        return {
            # ── ROI actualisé (utilisé comme valeur officielle)
            "total_revenue_dzd": float(round(total_revenue, 2)),
            "total_cost_dzd":    float(round(total_cost, 2)),
            "net_profit_dzd":    float(round(net_profit, 2)),
            "roi_pct":           float(round(roi_pct, 2)),
            # ── ROI brut (somme non actualisée) — pour comprendre vite
            "gross_revenue_dzd": float(round(gross_revenue, 2)),
            "gross_cost_dzd":    float(round(gross_cost, 2)),
            "gross_profit_dzd":  float(round(gross_profit, 2)),
            "gross_roi_pct":     float(round(gross_roi_pct, 2)),
        }

    # ────────────────────────────────────────────────────────────────────
    # MÉTHODE PRINCIPALE
    # ────────────────────────────────────────────────────────────────────

    def calculate(self) -> Dict:
        """Calcule l'ensemble des indicateurs financiers et environnementaux."""
        # 1) CAPEX
        capex_dict = self._compute_capex()
        capex      = capex_dict["total"]

        # 2) Production an 1
        yield_an1 = self._compute_year1_production()

        # 3) OPEX annuel
        opex_annual = capex * self.OPEX_PCT_CAPEX

        # 4) Revenus + OPEX + Cashflows nets (25 ans)
        revenues, opex_list, cashflows = self._compute_revenues_and_opex(yield_an1, opex_annual)

        # 5) Indicateurs financiers
        npv      = self._compute_npv(capex, cashflows)
        irr      = self._compute_irr(capex, cashflows)
        payback  = self._compute_payback(capex, cashflows)
        lcoe     = self._compute_lcoe(capex, opex_annual, yield_an1)
        roi_data = self._compute_roi(capex, revenues, opex_list, actualise=True)

        # 6) Impact environnemental
        co2_avoided = self._compute_co2_avoided(yield_an1)
        households  = self._compute_households(yield_an1)

        return {
            # ── Investissement
            "capex_dzd":        int(capex),
            "capex_debt_dzd":   int(capex_dict["debt"]),
            "capex_equity_dzd": int(capex_dict["equity"]),

            # ── Production
            "annual_yield_mwh": float(round(yield_an1, 2)),

            # ── Coûts opérationnels
            "opex_annual_dzd":  int(opex_annual),

            # ── Indicateurs financiers
            "npv_dzd":          int(npv),
            "irr_pct":          float(round(irr * 100, 2)),
            "payback_years":    float(round(payback, 1)) if payback is not None else None,
            "lcoe_dzd_kwh":     float(round(lcoe, 3)),

            # ── ★ ROI (formule classique) ★
            "roi_pct":              roi_data["roi_pct"],
            "total_revenue_dzd":    roi_data["total_revenue_dzd"],
            "total_cost_dzd":       roi_data["total_cost_dzd"],
            "net_profit_dzd":       roi_data["net_profit_dzd"],
            # version brute (non actualisée)
            "gross_roi_pct":        roi_data["gross_roi_pct"],
            "gross_revenue_dzd":    roi_data["gross_revenue_dzd"],
            "gross_cost_dzd":       roi_data["gross_cost_dzd"],
            "gross_profit_dzd":     roi_data["gross_profit_dzd"],

            # ── Environnemental
            "co2_avoided_tons":  int(co2_avoided),
            "households_powered": households,

            # ── Cashflows annuels nets + détail revenus/OPEX (pour graphique)
            "cashflows":  [int(cf) for cf in cashflows],
            "revenues":   [int(r)  for r in revenues],
            "opex_yearly": [int(o) for o in opex_list],

            # ── Métadonnées
            "lifetime_years":     self.lifetime,
            "discount_rate_pct":  self.DISCOUNT_RATE * 100,
            "tariff_dzd_kwh":     self.tariff,
            "installation_type":  self.install_type,
        }

    def calculate_scenarios(
        self, capacity_mw: float, ghi_annual: float, temp_avg: float
    ) -> Dict[str, Dict]:
        """Calcule le ROI pour les 3 scénarios tarifaires."""
        results = {}
        for scenario in ["bas", "moyen", "eleve"]:
            calc = ROICalculator(
                capacity_mw=capacity_mw,
                ghi_annual=ghi_annual,
                temp_avg=temp_avg,
                tariff_scenario=scenario,
                installation_type=self.install_type,
                lifetime_years=self.lifetime,
                inflation_rate=self.inflation,
            )
            results[scenario] = calc.calculate()
        return results


# ════════════════════════════════════════════════════════════════════════
# TEST CLI
# ════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    calc = ROICalculator(
        capacity_mw=50,
        ghi_annual=2450,
        temp_avg=28,
        tariff_scenario="moyen",
        installation_type="ground_mount",
    )
    r = calc.calculate()

    print("=" * 70)
    print("ROI CALCULATION — 50 MW Solar Plant, Tamanrasset")
    print("=" * 70)
    print()
    print("INVESTMENT:")
    print(f"  CAPEX Total:        {r['capex_dzd']:>18,} DZD")
    print(f"  CAPEX (70% debt):   {r['capex_debt_dzd']:>18,} DZD")
    print(f"  CAPEX (30% equity): {r['capex_equity_dzd']:>18,} DZD")
    print()
    print("PRODUCTION:")
    print(f"  Annual Yield (Yr1): {r['annual_yield_mwh']:>18,.0f} MWh")
    print()
    print("OPERATING COSTS:")
    print(f"  Annual OPEX:        {r['opex_annual_dzd']:>18,} DZD")
    print()
    print("FINANCIAL METRICS:")
    print(f"  NPV (25 years):     {r['npv_dzd']:>18,} DZD")
    print(f"  IRR:                {r['irr_pct']:>18.2f} %")
    print(f"  Payback Period:     {r['payback_years']:>18.1f} years")
    print(f"  LCOE:               {r['lcoe_dzd_kwh']:>18.3f} DZD/kWh")
    print()
    print("★ ROI (formula: (gain - cost) / cost × 100):")
    print(f"  Total Revenue:      {r['total_revenue_dzd']:>18,.0f} DZD (actualisé)")
    print(f"  Total Cost:         {r['total_cost_dzd']:>18,.0f} DZD (CAPEX + Σ OPEX actualisés)")
    print(f"  Net Profit:         {r['net_profit_dzd']:>18,.0f} DZD")
    print(f"  ROI:                {r['roi_pct']:>18.2f} %  (actualisé)")
    print(f"  Gross ROI:          {r['gross_roi_pct']:>18.2f} %  (non actualisé)")
    print()
    print("ENVIRONMENTAL:")
    print(f"  CO2 Avoided:        {r['co2_avoided_tons']:>18,} tons")
    print(f"  Households Powered: {r['households_powered']:>18,}")
    print("=" * 70)
