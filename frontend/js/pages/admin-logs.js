const AdminLogsPage = {
  // Cached API response split into activity and error arrays
  _data: { activities: [], errors: [] },

  // Active filter state sent with every API request
  _filter: { type: 'all', date: '' },

  // Resolves a translation key with an optional fallback string
  _t(k, f = '') {
    return (typeof I18N !== 'undefined' && I18N.t) ? (I18N.t(k) || f) : f;
  },

  // Renders the loading skeleton then triggers the initial data fetch
  async render() {
    const content = document.getElementById('page-content');
    content.innerHTML = `<div class="page-wrapper">${Components.loading('', '…')}</div>`;
    await this._load();
  },

  // Fetches filtered log data, rebuilds the page HTML, and re-binds filter controls
  async _load() {
    this._data = await DataService.adminLogs(this._filter);
    document.getElementById('page-content').innerHTML = this._template();
    if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();
    this._bindFilters();
  },

  // Escapes angle brackets in user-supplied strings to prevent XSS in innerHTML
  _safe(v) {
    return (v == null) ? '' : String(v).replace(/</g, '&lt;');
  },

  // Builds the full page HTML: filter bar, activity table, and error table
  _template() {
    const t = (k, f = '') => this._t(k, f);

    // Supported action types used to populate the filter dropdown
    const activityActions = ['login', 'analyse_zone', 'calcul_roi', 'rapport', 'upgrade', 'forecast'];
    const actOpts = activityActions.map(a =>
      `<option value="${a}" ${this._filter.type === a ? 'selected' : ''}>${a}</option>`
    ).join('');

    // One table row per activity log entry; timestamps are localised at render time
    const actRows = (this._data.activities || []).map(a => `
      <tr>
        <td style="white-space:nowrap;font-family:monospace;font-size:11px">${a.created_at ? new Date(a.created_at).toLocaleString() : '—'}</td>
        <td>${a.user
          ? `${this._safe(a.user.name)} <small style="color:#64748b">(${this._safe(a.user.email)})</small>`
          : '<span style="color:#94a3b8">anonyme</span>'}</td>
        <td><span style="display:inline-block;padding:2px 8px;background:#dbeafe;color:#1e40af;border-radius:10px;font-size:11px;font-weight:600">${this._safe(a.action)}</span></td>
        <td style="font-size:12px;color:#475569">${this._safe(a.details || '')}</td>
      </tr>`).join('');

    // One table row per error log entry; page origin is highlighted in red monospace
    const errRows = (this._data.errors || []).map(e => `
      <tr>
        <td style="white-space:nowrap;font-family:monospace;font-size:11px">${e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
        <td>${e.user
          ? `${this._safe(e.user.name)} <small style="color:#64748b">(${this._safe(e.user.email)})</small>`
          : '<span style="color:#94a3b8">anonyme</span>'}</td>
        <td style="font-family:monospace;font-size:11px;color:#991b1b">${this._safe(e.page || '')}</td>
        <td style="font-size:12px">${this._safe(e.message)}</td>
      </tr>`).join('');

    return `
      <div class="page-wrapper">

        <div class="page-header" style="margin-bottom:18px">
          <h1 style="margin:0">
            <i class="fas fa-clipboard-list"></i>
            <span data-i18n="admin.logs.title">${t('admin.logs.title')}</span>
          </h1>
        </div>

        <!-- Filter bar: action type dropdown and date picker -->
        <div class="card" style="margin-bottom:14px">
          <div class="card-body" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;align-items:end">
            <div>
              <label data-i18n="admin.logs.filter_type">${t('admin.logs.filter_type')}</label>
              <select id="adm-log-type" class="form-control">
                <option value="all" ${this._filter.type === 'all' ? 'selected' : ''}>${t('admin.logs.all_types')}</option>
                ${actOpts}
              </select>
            </div>
            <div>
              <label data-i18n="admin.logs.filter_date">${t('admin.logs.filter_date')}</label>
              <input id="adm-log-date" type="date" class="form-control" value="${this._safe(this._filter.date)}">
            </div>
          </div>
        </div>

        <!-- Activity log table -->
        <div class="card" style="margin-bottom:18px">
          <div class="card-header">
            <h3 data-i18n="admin.logs.activities_title">${t('admin.logs.activities_title')}</h3>
          </div>
          <div class="card-body" style="overflow-x:auto">
            <table style="width:100%;border-collapse:collapse;font-size:13px">
              <thead>
                <tr style="background:#f1f5f9">
                  <th style="padding:8px" data-i18n="admin.logs.col_date">${t('admin.logs.col_date')}</th>
                  <th style="padding:8px" data-i18n="admin.logs.col_user">${t('admin.logs.col_user')}</th>
                  <th style="padding:8px" data-i18n="admin.logs.col_action">${t('admin.logs.col_action')}</th>
                  <th style="padding:8px" data-i18n="admin.logs.col_details">${t('admin.logs.col_details')}</th>
                </tr>
              </thead>
              <tbody>
                ${actRows || `<tr><td colspan="4" style="padding:14px;text-align:center;color:#64748b">—</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>

        <!-- Error log table -->
        <div class="card">
          <div class="card-header">
            <h3 data-i18n="admin.logs.errors_title">${t('admin.logs.errors_title')}</h3>
          </div>
          <div class="card-body" style="overflow-x:auto">
            <table style="width:100%;border-collapse:collapse;font-size:13px">
              <thead>
                <tr style="background:#fef2f2">
                  <th style="padding:8px" data-i18n="admin.logs.col_date">${t('admin.logs.col_date')}</th>
                  <th style="padding:8px" data-i18n="admin.logs.col_user">${t('admin.logs.col_user')}</th>
                  <th style="padding:8px" data-i18n="admin.logs.col_page">${t('admin.logs.col_page')}</th>
                  <th style="padding:8px" data-i18n="admin.logs.col_message">${t('admin.logs.col_message')}</th>
                </tr>
              </thead>
              <tbody>
                ${errRows || `<tr><td colspan="4" style="padding:14px;text-align:center;color:#64748b">—</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>

      </div>`;
  },

  // Attaches change handlers to the type dropdown and date input;
  // each change updates the filter state and triggers a fresh data load
  _bindFilters() {
    const tSel = document.getElementById('adm-log-type');
    if (tSel) tSel.onchange = () => { this._filter.type = tSel.value; this._load(); };

    const dIn = document.getElementById('adm-log-date');
    if (dIn) dIn.onchange = () => { this._filter.date = dIn.value; this._load(); };
  },
};

window.AdminLogsPage = AdminLogsPage;