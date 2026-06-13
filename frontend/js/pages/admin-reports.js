const AdminReportsPage = {

  // Resolves a translation key with an optional fallback string
  _t(k, f = '') {
    return (typeof I18N !== 'undefined' && I18N.t) ? (I18N.t(k) || f) : f;
  },

  // Fetches report data, guards against non-admin access, then renders the page
  async render() {
    const content = document.getElementById('page-content');
    content.innerHTML = `<div class="page-wrapper">${Components.loading('', '…')}</div>`;

    const data = await DataService.adminReports();

    if (!data) {
      content.innerHTML = `<div class="page-wrapper">
        <div class="alert alert-danger" style="padding:14px">
          ${this._t('admin.required')}
        </div>
      </div>`;
      return;
    }

    content.innerHTML = this._template(data);
    if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();
  },

  // Escapes angle brackets in user-supplied strings to prevent XSS in innerHTML
  _safe(v) {
    return (v == null) ? '' : String(v).replace(/</g, '&lt;');
  },

  // Builds the full page HTML: KPI summary cards and the paginated reports table
  _template(d) {
    const t = (k, f = '') => this._t(k, f);

    // One table row per report; includes a download link when a filename is available
    const rows = (d.reports || []).map(r => `
      <tr>
        <td>${r.user
          ? `${this._safe(r.user.name)} <small style="color:#64748b">(${this._safe(r.user.email)})</small>`
          : '—'}</td>
        <td><span style="display:inline-block;padding:2px 8px;background:#dbeafe;color:#1e40af;border-radius:10px;font-size:11px;font-weight:600">${this._safe(r.type)}</span></td>
        <td>${this._safe(r.wilaya)}</td>
        <td style="font-family:monospace;font-size:11px">${r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</td>
        <td>${r.filename
          ? `<a href="/api/reports/${r.id}/download" class="btn btn-sm btn-outline" download><i class="fas fa-download"></i> ${t('admin.reports.download')}</a>`
          : '—'}</td>
      </tr>`).join('');

    // Aggregate stats derived from the API response
    const stats      = d.stats || {};
    const mostType   = stats.most_generated_type   || {};
    const mostWilaya = stats.most_requested_wilaya || {};

    return `
      <div class="page-wrapper">

        <div class="page-header" style="margin-bottom:18px">
          <h1 style="margin:0">
            <i class="fas fa-file-alt"></i>
            <span data-i18n="admin.reports.title">${t('admin.reports.title')}</span>
          </h1>
        </div>

        <!-- KPI cards: most-generated report type and most-requested wilaya -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:18px">

          <div class="kpi-card" style="background:#fff;padding:14px;border-left:4px solid #f59e0b;border-radius:8px">
            <div class="muted" style="font-size:11px;text-transform:uppercase" data-i18n="admin.reports.most_type">
              ${t('admin.reports.most_type')}
            </div>
            <div style="font-size:20px;font-weight:700">${this._safe(mostType.type || '—')}</div>
            <div style="font-size:11px;color:#64748b">${mostType.count || 0} rapports</div>
          </div>

          <div class="kpi-card" style="background:#fff;padding:14px;border-left:4px solid #3b82f6;border-radius:8px">
            <div class="muted" style="font-size:11px;text-transform:uppercase" data-i18n="admin.reports.most_wilaya">
              ${t('admin.reports.most_wilaya')}
            </div>
            <div style="font-size:20px;font-weight:700">${this._safe(mostWilaya.wilaya || '—')}</div>
            <div style="font-size:11px;color:#64748b">${mostWilaya.count || 0} rapports</div>
          </div>

        </div>

        <!-- Full reports table with download action per row -->
        <div class="card">
          <div class="card-body" style="overflow-x:auto">
            <table style="width:100%;border-collapse:collapse;font-size:13px">
              <thead>
                <tr style="background:#f1f5f9">
                  <th style="padding:8px" data-i18n="admin.reports.col_user">${t('admin.reports.col_user')}</th>
                  <th style="padding:8px" data-i18n="admin.reports.col_type">${t('admin.reports.col_type')}</th>
                  <th style="padding:8px" data-i18n="admin.reports.col_wilaya">${t('admin.reports.col_wilaya')}</th>
                  <th style="padding:8px" data-i18n="admin.reports.col_date">${t('admin.reports.col_date')}</th>
                  <th style="padding:8px" data-i18n="admin.reports.col_action">${t('admin.reports.col_action')}</th>
                </tr>
              </thead>
              <tbody>
                ${rows || `<tr><td colspan="5" style="padding:14px;text-align:center;color:#64748b">—</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>

      </div>`;
  },
};

window.AdminReportsPage = AdminReportsPage;