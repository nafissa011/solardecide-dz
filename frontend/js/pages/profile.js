const ProfilePage = {
  _data:     null,
  _analyses: [],
  _roi:      [],
  _reports:  [],

  _t(k, f = '') {
    return (typeof I18N !== 'undefined' && I18N.t) ? (I18N.t(k) || f) : f;
  },

  async render() {
    const content = document.getElementById('page-content');
    if (!content) return;

    if (!API.isAuthenticated()) {
      App.navigate('login');
      return;
    }

    content.innerHTML = `<div class="page-wrapper">${Components.loading('', this._t('common.loading', 'Chargement…'))}</div>`;

    try {
      const verified = await API.verify();
      if (!verified?.authenticated) { App.navigate('login'); return; }

      const profile = await DataService.getProfile();
      if (!profile) throw new Error('profile_unavailable');

      this._data = profile;

      // Persist the latest profile so other modules read fresh data
      try { sessionStorage.setItem('user', JSON.stringify(profile)); } catch (_) {}

      const limit = this._planLimit(profile.plan);

      // Fetch all profile sections in parallel to reduce total load time
      const [analysesRes, roiRes, reportsRes] = await Promise.all([
        DataService.getProfileAnalyses(limit),
        DataService.getProfileRoi(limit),
        DataService.getProfileReports(),
      ]);

      this._analyses = analysesRes?.data || [];
      this._roi      = roiRes?.data      || [];
      this._reports  = reportsRes?.data  || [];

      content.innerHTML = this._template();

      if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();
      this._bindActions();
    } catch (e) {
      console.error('[profile] render error:', e);
      content.innerHTML = `
        <div class="page-wrapper">
          <div class="card" style="max-width:560px;margin:40px auto">
            <div class="card-body text-center">
              <i class="fas fa-exclamation-triangle" style="font-size:42px;color:#f59e0b"></i>
              <p>${e.message || ''}</p>
              <button class="btn btn-primary" onclick="App.navigate('landing')">${this._t('common.back', 'Retour')}</button>
            </div>
          </div>
        </div>`;
    }
  },

  // Returns the history fetch limit for a given plan; 0 means unlimited (enterprise)
  _planLimit(plan) {
    return ({ free: 5, pro: 50, enterprise: 0 })[(plan || 'free').toLowerCase()];
  },

  // Coerces null/undefined to an em dash and escapes HTML to prevent XSS
  _safe(v) {
    return (v === null || v === undefined) ? '—' : String(v).replace(/</g, '&lt;');
  },

  _formatDate(iso) {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleDateString(); } catch (_) { return iso; }
  },

  _template() {
    const t = (k, f = '') => this._t(k, f);
    const d = this._data || {};
    const plan = (d.plan || 'free').toLowerCase();

    const planBadgeColor = ({
      free:       '#94a3b8',
      pro:        '#3b82f6',
      enterprise: '#10b981',
    })[plan] || '#94a3b8';

    const planLabel = ({
      free:       t('profile.plan.free'),
      pro:        t('profile.plan.pro'),
      enterprise: t('profile.plan.enterprise'),
    })[plan] || plan;

    const counters = d.counters || {};
    const c = {
      analyses: counters.analyses_month ?? 0,
      reports:  counters.reports_month  ?? 0,
      roi:      counters.roi_month      ?? 0,
    };

    return `
      <div class="page-wrapper profile-page">
        <div class="page-header" style="margin-bottom:18px">
          <h1 style="margin:0"><i class="fas fa-user-circle"></i> <span data-i18n="profile.title">${t('profile.title')}</span></h1>
          <p class="muted" data-i18n="profile.subtitle">${t('profile.subtitle')}</p>
        </div>

        <div class="kpi-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:18px">
          ${this._kpi('fa-chart-area', t('profile.counters.analyses_month'), c.analyses, '', '#3b82f6')}
          ${this._kpi('fa-coins',      t('profile.counters.roi_month'),      c.roi,      '', '#10b981')}
          ${this._kpi('fa-file-pdf',   t('profile.counters.reports_month'),  c.reports,  '', '#f59e0b')}
        </div>

        <div class="grid-2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
          <div class="card">
            <div class="card-header"><h3><i class="fas fa-id-card"></i> ${t('profile.title')}</h3></div>
            <div class="card-body">
              ${this._row(t('profile.info.name'),          this._safe(d.name))}
              ${this._row(t('profile.info.email'),         this._safe(d.email))}
              ${this._row(t('profile.info.registered_on'), this._formatDate(d.created_at))}
              ${this._row(t('profile.info.last_login'),    this._formatDate(d.last_login))}
              ${this._row(t('profile.info.role'),          this._safe(d.role))}
              ${this._row(t('profile.info.status'),
                d.is_active
                  ? `<span style="color:#10b981">${t('profile.info.active')}</span>`
                  : `<span style="color:#ef4444">${t('profile.info.inactive')}</span>`)}
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3><i class="fas fa-star"></i> <span data-i18n="profile.plan.title">${t('profile.plan.title')}</span></h3>
            </div>
            <div class="card-body">
              <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
                <span style="background:${planBadgeColor};color:#fff;padding:8px 14px;border-radius:20px;font-weight:600;font-size:14px">
                  ${planLabel}
                </span>
                ${d.plan_expires_at
                  ? `<span class="muted" style="font-size:13px">${t('profile.plan.expires_on')} ${this._formatDate(d.plan_expires_at)}</span>`
                  : (plan === 'free' ? '' : `<span class="muted" style="font-size:13px">${t('profile.plan.no_expiration')}</span>`)}
              </div>

              ${this._row(t('profile.plan.quota_used'), `${d.counters?.analyses_count_month ?? 0}`)}
              ${this._row(t('profile.plan.quota_total'),
                d.plan_limit_history === null
                  ? `<span style="color:#10b981">${t('profile.plan.unlimited')}</span>`
                  : `${d.plan_limit_history}`)}

              <div style="margin-top:16px;text-align:center">
                ${plan === 'free' ? `
                  <button class="btn btn-primary" id="prof-upgrade-pro">
                    <i class="fas fa-rocket"></i>
                    <span data-i18n="profile.plan.upgrade_pro">${t('profile.plan.upgrade_pro')}</span>
                  </button>` : ''}
                ${plan === 'pro' ? `
                  <button class="btn btn-success" id="prof-upgrade-ent">
                    <i class="fas fa-crown"></i>
                    <span data-i18n="profile.plan.upgrade_enterprise">${t('profile.plan.upgrade_enterprise')}</span>
                  </button>` : ''}
                ${plan === 'enterprise' ? `
                  <span style="color:#10b981;font-weight:600" data-i18n="profile.plan.active_enterprise">
                    <i class="fas fa-check-circle"></i> ${t('profile.plan.active_enterprise')}
                  </span>` : ''}
              </div>
            </div>
          </div>
        </div>

        ${this._sectionAnalyses(plan)}
        ${this._sectionRoi()}
        ${this._sectionReports()}
      </div>

      <style>
        .prof-table { width:100%; border-collapse:collapse; font-size:13px; }
        .prof-table th, .prof-table td { padding:8px 10px; border-bottom:1px solid var(--border-color); text-align:left; }
        .prof-table th { background:var(--bg-elevated); color:var(--text-secondary); font-weight:600; }
        .prof-empty { padding:18px; text-align:center; color:var(--text-muted); font-style:italic; }
      </style>
    `;
  },

  _kpi(icon, label, value, unit, color) {
    return `
      <div class="kpi-card" style="background:var(--bg-card);border:1px solid var(--border-color);border-left:4px solid ${color};border-radius:8px;padding:14px 16px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <span class="muted" style="font-size:12px;text-transform:uppercase;letter-spacing:.04em">${label}</span>
          <i class="fas ${icon}" style="color:${color};opacity:.7"></i>
        </div>
        <div style="font-size:24px;font-weight:700;margin-top:6px;color:var(--text-primary)">
          ${value}<span class="muted" style="font-size:13px;font-weight:500"> ${unit || ''}</span>
        </div>
      </div>`;
  },

  _row(label, value) {
    return `
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px dashed var(--border-color)">
        <span style="font-size:13px;color:var(--text-secondary)">${label}</span>
        <strong style="color:var(--text-primary)">${value}</strong>
      </div>`;
  },

  _sectionAnalyses(plan) {
    const t = (k, f = '') => this._t(k, f);

    const subtitle = ({
      free:       t('profile.analyses.subtitle_free'),
      pro:        t('profile.analyses.subtitle_pro'),
      enterprise: t('profile.analyses.subtitle_enterprise'),
    })[plan] || '';

    const rows = (this._analyses || []).map(a => `
      <tr>
        <td>${this._safe(a.wilaya)}</td>
        <td>${this._safe(a.commune)}</td>
        <td>${a.score != null ? Number(a.score).toFixed(1) : '—'}</td>
        <td>${a.ghi   != null ? Number(a.ghi).toFixed(2)   : '—'}</td>
        <td>${this._formatDate(a.date)}</td>
        <td>
          <button class="btn btn-sm btn-outline prof-review"
                  data-wilaya="${this._safe(a.wilaya)}" data-commune="${this._safe(a.commune)}">
            <i class="fas fa-eye"></i> ${t('profile.analyses.review')}
          </button>
        </td>
      </tr>`).join('');

    return `
      <div class="card" style="margin-bottom:18px">
        <div class="card-header">
          <h3><i class="fas fa-map-marker-alt"></i> <span data-i18n="profile.analyses.title">${t('profile.analyses.title')}</span></h3>
          <small class="muted">${subtitle}</small>
        </div>
        <div class="card-body" style="overflow-x:auto">
          ${this._analyses.length === 0
            ? `<div class="prof-empty">${t('profile.analyses.empty')}</div>`
            : `<table class="prof-table">
                <thead><tr>
                  <th>${t('profile.analyses.wilaya')}</th>
                  <th>${t('profile.analyses.commune')}</th>
                  <th>${t('profile.analyses.score')}</th>
                  <th>${t('profile.analyses.ghi')}</th>
                  <th>${t('profile.analyses.date')}</th>
                  <th>${t('profile.analyses.actions')}</th>
                </tr></thead>
                <tbody>${rows}</tbody>
              </table>`}
        </div>
      </div>`;
  },

  _sectionRoi() {
    const t = (k, f = '') => this._t(k, f);

    const rows = (this._roi || []).map(r => `
      <tr>
        <td>${this._safe(r.wilaya)}</td>
        <td>${r.capacity_kwc  != null ? Number(r.capacity_kwc).toFixed(0)   : '—'}</td>
        <td>${r.roi_pct       != null ? Number(r.roi_pct).toFixed(2) + '%'  : '—'}</td>
        <td>${r.payback_years != null ? Number(r.payback_years).toFixed(1)  : '—'}</td>
        <td>${this._formatDate(r.date)}</td>
      </tr>`).join('');

    return `
      <div class="card" style="margin-bottom:18px">
        <div class="card-header">
          <h3><i class="fas fa-coins"></i> <span data-i18n="profile.roi.title">${t('profile.roi.title')}</span></h3>
        </div>
        <div class="card-body" style="overflow-x:auto">
          ${this._roi.length === 0
            ? `<div class="prof-empty">${t('profile.roi.empty')}</div>`
            : `<table class="prof-table">
                <thead><tr>
                  <th>${t('profile.roi.wilaya')}</th>
                  <th>${t('profile.roi.capacity')}</th>
                  <th>${t('profile.roi.roi_pct')}</th>
                  <th>${t('profile.roi.payback')}</th>
                  <th>${t('profile.roi.date')}</th>
                </tr></thead>
                <tbody>${rows}</tbody>
              </table>`}
        </div>
      </div>`;
  },

  _sectionReports() {
    const t = (k, f = '') => this._t(k, f);

    const rows = (this._reports || []).map(r => `
      <tr>
        <td>${this._safe(r.report_type || r.title)}</td>
        <td>${this._safe(r.wilaya)}</td>
        <td>${this._formatDate(r.date)}</td>
        <td>
          ${r.has_pdf
            ? `<button class="btn btn-sm btn-primary prof-redownload" data-id="${r.id}">
                <i class="fas fa-download"></i> ${t('profile.reports.redownload')}
              </button>`
            : `<span class="muted" style="font-size:12px">—</span>`}
        </td>
      </tr>`).join('');

    return `
      <div class="card" style="margin-bottom:18px">
        <div class="card-header">
          <h3><i class="fas fa-file-pdf"></i> <span data-i18n="profile.reports.title">${t('profile.reports.title')}</span></h3>
        </div>
        <div class="card-body" style="overflow-x:auto">
          ${this._reports.length === 0
            ? `<div class="prof-empty">${t('profile.reports.empty')}</div>`
            : `<table class="prof-table">
                <thead><tr>
                  <th>${t('profile.reports.type')}</th>
                  <th>${t('profile.reports.wilaya')}</th>
                  <th>${t('profile.reports.date')}</th>
                  <th>${t('profile.reports.actions')}</th>
                </tr></thead>
                <tbody>${rows}</tbody>
              </table>`}
        </div>
      </div>`;
  },

  _bindActions() {
    // Wire "review" buttons to navigate back to the zone page with pre-filled params
    document.querySelectorAll('.prof-review').forEach(btn => {
      btn.onclick = () => {
        const wilaya  = btn.getAttribute('data-wilaya');
        const commune = btn.getAttribute('data-commune');
        if (!wilaya || wilaya === '—') return;
        const params = { wilaya };
        if (commune && commune !== '—') params.commune = commune;
        App.navigate('zone', params);
      };
    });

    // Trigger a direct file download by setting location.href to the report URL
    document.querySelectorAll('.prof-redownload').forEach(btn => {
      btn.onclick = () => {
        const id = btn.getAttribute('data-id');
        if (!id) return;
        window.location.href = DataService.profileReportDownloadUrl(id);
      };
    });

    const upPro = document.getElementById('prof-upgrade-pro');
    if (upPro) upPro.onclick = () => App.navigate('pricing');

    const upEnt = document.getElementById('prof-upgrade-ent');
    if (upEnt) upEnt.onclick = () => App.navigate('pricing');
  },
};

window.ProfilePage = ProfilePage;