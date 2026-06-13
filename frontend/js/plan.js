(function (global) {
  'use strict';

  // Set to false to restore the paywall before production release
  const TEST_MODE_OPEN_ALL_FEATURES = true;

  const PLAN_ORDER = { free: 0, pro: 1, enterprise: 2 };

  // Single source of truth for feature access — edit here only
  const FEATURE_MATRIX = {
    'page.landing':          'free',
    'page.ranking':          'free',
    'page.wilaya':           'free',
    'page.zone':             'free',
    'page.comparison':       'pro',
    'page.forecast':         'pro',
    'page.roi':              'pro',
    'page.reports':          'pro',
    'page.history':          'free',
    'page.offline':          'free',
    'page.profile':          'free',
    'page.pricing':          'free',

    'action.export_csv_ranking':       'pro',
    'action.export_raw_csv':           'enterprise',
    'action.wilaya_pdf':               'pro',
    'action.zone_run_analysis':        'pro',
    'action.comparison_run':           'pro',
    'action.forecast_24h':             'pro',
    'action.forecast_7d':              'pro',
    'action.forecast_30d':             'enterprise',
    'action.forecast_1y':              'enterprise',
    'action.forecast_longterm':        'enterprise',
    'action.roi_compute':              'pro',
    'action.report_investor':          'pro',
    'action.report_government':        'enterprise',
    'action.report_no_watermark':      'enterprise',
    'action.recommendation':           'pro',
    'action.recommendation_unlimited': 'enterprise',
    'action.api_access':               'enterprise',
    'action.history_50':               'pro',
    'action.history_unlimited':        'enterprise',
  };

  const MONTHLY_QUOTAS = {
    free:       { recommandations: 0 },
    pro:        { recommandations: 5 },
    enterprise: { recommandations: Infinity },
  };

  const Plan = {
    _user: null,

    async refresh() {
      try {
        const u = await (window.API?.getCurrentUser?.());
        this._user = u || null;
      } catch (e) {
        this._user = null;
      }
      return this._user;
    },

    _cachedUser() {
      if (this._user) return this._user;
      try {
        const raw = sessionStorage.getItem('user');
        if (raw) {
          this._user = JSON.parse(raw);
          return this._user;
        }
      } catch (e) { /* ignore */ }
      return null;
    },

    current() {
      const u = this._cachedUser();
      const p = (u?.plan || 'free').toLowerCase();
      return PLAN_ORDER[p] === undefined ? 'free' : p;
    },

    counts() {
      const u = this._cachedUser() || {};
      return {
        analyses:        Number(u.analyses_count_month || 0),
        recommandations: Number(u.recommandations_count_month || 0),
      };
    },

    quota(name) {
      return MONTHLY_QUOTAS[this.current()]?.[name] ?? 0;
    },

    is(level) {
      return this.current() === level;
    },

    atLeast(level) {
      return PLAN_ORDER[this.current()] >= (PLAN_ORDER[level] ?? 0);
    },

    canAccess(featureId) {
      if (TEST_MODE_OPEN_ALL_FEATURES) return true;
      const required = FEATURE_MATRIX[featureId];
      if (required === undefined) return true; // unknown features are permissive by default
      return this.atLeast(required);
    },

    required(featureId) {
      return FEATURE_MATRIX[featureId] || 'free';
    },

    // Usage: onclick="return Plan.gate('action.zone_run_analysis') && doRun()"
    gate(featureId) {
      if (TEST_MODE_OPEN_ALL_FEATURES) return true;
      if (this.canAccess(featureId)) return true;
      const req = this.required(featureId);
      if (window.PlanGate?.open) PlanGate.open(req, featureId);
      return false;
    },

    label(plan) {
      const map = {
        free:       window.I18N ? I18N.t('topbar.plan_free')       : 'Gratuit',
        pro:        window.I18N ? I18N.t('topbar.plan_pro')        : 'Pro',
        enterprise: window.I18N ? I18N.t('topbar.plan_enterprise') : 'Entreprise',
      };
      return map[plan] || plan;
    },

    badgeHtml() {
      const plan = this.current();
      const label = this.label(plan);
      const showUpgrade = (plan === 'free');
      return `
        <div class="plan-block">
          <span class="plan-badge plan-${plan}" data-tooltip="${I18N?.t('profile.your_plan') || 'Plan'}">${label}</span>
          ${showUpgrade ? `
            <button class="btn btn-primary btn-xs btn-upgrade"
                    onclick="App.navigate('pricing')"
                    data-i18n="topbar.upgrade">${I18N?.t('topbar.upgrade') || 'Mettre à niveau'}</button>
          ` : ''}
        </div>
      `;
    },
  };

  Plan.FEATURE_MATRIX = FEATURE_MATRIX;
  Plan.MONTHLY_QUOTAS = MONTHLY_QUOTAS;
  Plan.PLAN_ORDER = PLAN_ORDER;
  global.Plan = Plan;
})(typeof window !== 'undefined' ? window : globalThis);