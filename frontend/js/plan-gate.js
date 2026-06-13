// Upsell modal — shown when a feature requires a higher plan.
// Usage:
//   PlanGate.open('pro', 'action.zone_run_analysis')
//   PlanGate.open('enterprise')
//   PlanGate.close()
//   PlanGate.intercept(response)  // handles { error:'plan_required' } 422 responses

(function (global) {
  'use strict';

  const T = (k) => (window.I18N ? I18N.t(k) : k);

  const FEATURE_BLURB = {
    'action.export_csv_ranking':       'Exportez le classement complet en CSV pour vos présentations.',
    'action.export_raw_csv':           'Téléchargez les données brutes du dataset (NASA POWER) à des fins de modélisation.',
    'action.wilaya_pdf':               'Téléchargez la fiche complète d\'une wilaya au format PDF.',
    'action.zone_run_analysis':        'Lancez l\'analyse détaillée d\'une zone (commune) avec scoring composite.',
    'action.comparison_run':           'Comparez jusqu\'à 3 wilayas côte à côte avec le modèle Hybrid Ridge+MLP.',
    'action.forecast_24h':             'Accédez aux prévisions IA de production solaire.',
    'action.forecast_7d':              'Accédez aux prévisions à 7 jours.',
    'action.forecast_30d':             'Accédez aux prévisions à 30 jours.',
    'action.forecast_1y':              'Accédez aux prévisions sur 12 mois.',
    'action.forecast_longterm':        'Accédez à la prédiction long terme sur 5 ans.',
    'action.roi_compute':              'Calculez votre retour sur investissement avec scénarios.',
    'action.report_investor':          'Générez des rapports PDF d\'investissement professionnels.',
    'action.report_government':        'Générez des rapports gouvernementaux PDF.',
    'action.report_no_watermark':      'Téléchargez vos rapports sans filigrane.',
    'action.recommendation':           'Bénéficiez de recommandations de zones par IA.',
    'action.recommendation_unlimited': 'Recommandations illimitées (vous avez atteint le quota mensuel).',
    'action.api_access':               'Accédez à l\'API REST complète avec votre clé d\'authentification.',
    'action.history_50':               'Conservez 50 analyses dans votre historique.',
    'action.history_unlimited':        'Historique illimité.',
    'page.comparison':                 'Comparez les wilayas avec notre modèle IA.',
    'page.forecast':                   'Accédez à toutes les prévisions IA.',
    'page.roi':                        'Modélisez vos projets financièrement.',
    'page.reports':                    'Générez tous types de rapports professionnels.',
  };

  const PlanGate = {
    open(required = 'pro', featureId = null) {
      this.close();
      const isPro   = required === 'pro';
      const title   = isPro ? T('plangate.title_pro')        : T('plangate.title_enterprise');
      const price   = isPro ? T('plangate.price_pro')        : T('plangate.price_enterprise');
      const accent  = isPro ? '#3b82f6'                      : '#a855f7';
      const blurb   = (featureId && FEATURE_BLURB[featureId])
        ? FEATURE_BLURB[featureId]
        : (isPro
            ? 'Cette fonctionnalité est incluse dans le plan Pro.'
            : 'Cette fonctionnalité est incluse dans le plan Entreprise.');

      const overlay = document.createElement('div');
      overlay.id = 'plan-gate-overlay';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.style.cssText = `
        position:fixed;inset:0;z-index:9999;
        background:rgba(8,10,14,0.78);
        backdrop-filter:blur(6px);
        display:flex;align-items:center;justify-content:center;
        animation:plan-gate-fade-in .15s ease-out;
      `;
      overlay.innerHTML = `
        <div class="plan-gate-card" style="
            max-width:440px;width:calc(100% - 32px);
            background:var(--bg-card, #1a1f2b);
            border:1px solid ${accent}55;
            border-radius:16px;
            box-shadow:0 24px 60px rgba(0,0,0,.55), 0 0 0 1px ${accent}22 inset;
            padding:28px 26px 22px;
            color:var(--text-primary, #f3f4f6);
            position:relative;
            animation:plan-gate-pop .18s ease-out;
        ">
          <button class="plan-gate-close" onclick="PlanGate.close()" aria-label="${T('common.close')}"
            style="position:absolute;top:10px;right:12px;background:transparent;border:0;color:var(--text-muted,#9ca3af);font-size:18px;cursor:pointer;width:28px;height:28px;border-radius:50%;display:grid;place-items:center;">
            <i class="fas fa-times"></i>
          </button>

          <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px;">
            <div style="width:48px;height:48px;border-radius:12px;background:${accent}22;display:grid;place-items:center;flex-shrink:0;">
              <i class="fas fa-${isPro ? 'crown' : 'building'}" style="color:${accent};font-size:22px;"></i>
            </div>
            <div>
              <div style="font-size:11px;letter-spacing:.08em;color:var(--text-muted,#9ca3af);text-transform:uppercase;font-weight:600;">${isPro ? 'PRO' : 'ENTERPRISE'}</div>
              <h3 style="margin:2px 0 0;font-size:18px;font-weight:700;color:var(--text-primary,#f3f4f6);">${title}</h3>
            </div>
          </div>

          <p style="margin:0 0 18px;font-size:14px;line-height:1.55;color:var(--text-secondary,#cbd5e1);">
            ${blurb}
          </p>

          <div style="background:rgba(255,255,255,.04);border:1px solid var(--border-color,rgba(255,255,255,.08));border-radius:10px;padding:12px 14px;margin-bottom:18px;display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:12px;color:var(--text-muted,#9ca3af);">${isPro ? 'Plan Pro' : 'Plan Entreprise'}</span>
            <span style="font-weight:700;font-size:15px;color:${accent};">${price}</span>
          </div>

          <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button class="btn btn-ghost btn-sm" onclick="PlanGate.close()" data-i18n="plangate.close">${T('plangate.close')}</button>
            <button class="btn btn-primary btn-sm" onclick="PlanGate.close();App.navigate('pricing');" style="background:${accent};border-color:${accent};">
              <i class="fas fa-arrow-right" style="margin-right:6px;"></i>
              <span data-i18n="plangate.see_plans">${T('plangate.see_plans')}</span>
            </button>
          </div>
        </div>
        <style>
          @keyframes plan-gate-fade-in { from { opacity: 0 } to { opacity: 1 } }
          @keyframes plan-gate-pop { from { transform: scale(.93); opacity: 0 } to { transform: scale(1); opacity: 1 } }
        </style>
      `;
      overlay.addEventListener('click', (e) => { if (e.target === overlay) this.close(); });
      document.body.appendChild(overlay);
      this._keyHandler = (e) => { if (e.key === 'Escape') this.close(); };
      document.addEventListener('keydown', this._keyHandler);
    },

    // Quota-exhausted variant — simpler modal without plan details
    openQuota() {
      this.close();
      const overlay = document.createElement('div');
      overlay.id = 'plan-gate-overlay';
      overlay.style.cssText = `position:fixed;inset:0;z-index:9999;background:rgba(8,10,14,0.78);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;`;
      overlay.innerHTML = `
        <div style="max-width:420px;width:calc(100% - 32px);background:var(--bg-card,#1a1f2b);border:1px solid #a855f755;border-radius:16px;padding:26px;color:var(--text-primary,#f3f4f6);">
          <h3 style="margin:0 0 8px;">${T('plangate.quota_exceeded')}</h3>
          <p style="margin:0 0 18px;font-size:14px;color:var(--text-secondary,#cbd5e1);line-height:1.55;">${T('plangate.quota_msg')}</p>
          <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button class="btn btn-ghost btn-sm" onclick="PlanGate.close()">${T('plangate.close')}</button>
            <button class="btn btn-primary btn-sm" onclick="PlanGate.close();App.navigate('pricing');">${T('plangate.see_plans')}</button>
          </div>
        </div>
      `;
      overlay.addEventListener('click', (e) => { if (e.target === overlay) this.close(); });
      document.body.appendChild(overlay);
    },

    close() {
      const el = document.getElementById('plan-gate-overlay');
      if (el) el.remove();
      if (this._keyHandler) {
        document.removeEventListener('keydown', this._keyHandler);
        this._keyHandler = null;
      }
    },

    // Returns true if the response was a plan/quota error and the modal was shown
    intercept(jsonOrError) {
      if (!jsonOrError) return false;
      const err = jsonOrError.error || jsonOrError;
      if (err === 'plan_required' || jsonOrError?.error === 'plan_required') {
        this.open(jsonOrError.required || 'pro');
        return true;
      }
      if (err === 'quota_exceeded' || jsonOrError?.error === 'quota_exceeded') {
        this.openQuota();
        return true;
      }
      return false;
    },
  };

  global.PlanGate = PlanGate;
})(typeof window !== 'undefined' ? window : globalThis);