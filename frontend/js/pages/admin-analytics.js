const AdminAnalyticsPage = {
  // Local data cache and chart instances registry
  _data: null,
  _charts: {},

  // Resolves a translation key with an optional fallback string
  _t(k, f = '') {
    return (typeof I18N !== 'undefined' && I18N.t) ? (I18N.t(k) || f) : f;
  },

  // Fetches analytics data, renders the page skeleton, then mounts charts
  async render() {
    const content = document.getElementById('page-content');
    content.innerHTML = `<div class="page-wrapper">${Components.loading('', '…')}</div>`;

    this._data = await DataService.adminAnalytics();

    if (!this._data) {
      content.innerHTML = `<div class="page-wrapper">
        <div class="alert alert-danger" style="padding:14px">
          ${this._t('admin.required')}
        </div>
      </div>`;
      return;
    }

    content.innerHTML = this._template();

    if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();

    this._renderCharts();
  },

  // Destroys all active Chart.js instances to free memory before page teardown
  cleanup() {
    Object.values(this._charts).forEach(c => {
      try { c.destroy(); } catch (_) {}
    });
    this._charts = {};
  },

  // Builds the full HTML layout: KPI cards, chart panels, and the top users table
  _template() {
    const t = (k, f = '') => this._t(k, f);
    const d = this._data || {};

    const topUsersRows = (d.top_active_users || []).map(u => `
      <tr>
        <td>${u.id}</td>
        <td>${u.name || '—'}</td>
        <td style="font-family:monospace;font-size:12px">${u.email || '—'}</td>
        <td style="text-align:center;font-weight:600">${u.actions}</td>
      </tr>`).join('');

    return `
      <div class="page-wrapper">

        <div class="page-header" style="margin-bottom:18px">
          <h1 style="margin:0">
            <i class="fas fa-chart-bar"></i>
            <span data-i18n="admin.analytics.title">${t('admin.analytics.title')}</span>
          </h1>
        </div>

        <!-- KPI summary row -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:18px">

          <div class="kpi-card" style="background:#fff;padding:14px;border-left:4px solid #3b82f6;border-radius:8px">
            <div class="muted" style="font-size:11px;text-transform:uppercase" data-i18n="admin.analytics.total_users">
              ${t('admin.analytics.total_users')}
            </div>
            <div style="font-size:22px;font-weight:700">${d.total_users || 0}</div>
          </div>

          <div class="kpi-card" style="background:#fff;padding:14px;border-left:4px solid #10b981;border-radius:8px">
            <div class="muted" style="font-size:11px;text-transform:uppercase" data-i18n="admin.analytics.paid_users">
              ${t('admin.analytics.paid_users')}
            </div>
            <div style="font-size:22px;font-weight:700">${d.paid_users || 0}</div>
          </div>

          <div class="kpi-card" style="background:#fff;padding:14px;border-left:4px solid #f59e0b;border-radius:8px">
            <div class="muted" style="font-size:11px;text-transform:uppercase" data-i18n="admin.analytics.conversion_rate">
              ${t('admin.analytics.conversion_rate')}
            </div>
            <div style="font-size:22px;font-weight:700">${(d.conversion_rate || 0).toFixed(2)} %</div>
          </div>

        </div>

        <!-- Time-series charts: daily registrations and daily activity -->
        <div class="grid-2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
          <div class="card">
            <div class="card-header">
              <h3 data-i18n="admin.analytics.registrations_30d">${t('admin.analytics.registrations_30d')}</h3>
            </div>
            <div class="card-body"><canvas id="adm-reg-chart" height="220"></canvas></div>
          </div>
          <div class="card">
            <div class="card-header">
              <h3 data-i18n="admin.analytics.analyses_30d">${t('admin.analytics.analyses_30d')}</h3>
            </div>
            <div class="card-body"><canvas id="adm-act-chart" height="220"></canvas></div>
          </div>
        </div>

        <!-- Geographic distribution and top active users -->
        <div class="grid-2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px">

          <div class="card">
            <div class="card-header">
              <h3 data-i18n="admin.analytics.top_wilayas">${t('admin.analytics.top_wilayas')}</h3>
            </div>
            <div class="card-body"><canvas id="adm-tw-chart" height="220"></canvas></div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3 data-i18n="admin.analytics.top_users">${t('admin.analytics.top_users')}</h3>
            </div>
            <div class="card-body" style="overflow-x:auto">
              <table style="width:100%;border-collapse:collapse;font-size:13px">
                <thead>
                  <tr style="background:#f1f5f9">
                    <th style="padding:8px">ID</th>
                    <th style="padding:8px">Nom</th>
                    <th style="padding:8px">Email</th>
                    <th style="padding:8px;text-align:center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  ${topUsersRows || `<tr><td colspan="4" style="padding:14px;text-align:center;color:#64748b">—</td></tr>`}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </div>`;
  },

  // Instantiates all Chart.js charts after the DOM is ready
  _renderCharts() {
    if (typeof Chart === 'undefined' || !this._data) return;
    const d = this._data;

    // Factory for area line charts shared by registration and activity panels
    const mkLine = (id, label, color, values) => {
      const ctx = document.getElementById(id);
      if (!ctx) return null;
      return new Chart(ctx, {
        type: 'line',
        data: {
          labels: d.labels,
          datasets: [{
            label,
            data: values,
            borderColor: color,
            backgroundColor: color + '33',
            fill: true,
            tension: 0.3,
            pointRadius: 2,
          }],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true },
            x: { ticks: { maxRotation: 0, autoSkip: true } },
          },
        },
      });
    };

    this._charts.reg = mkLine('adm-reg-chart', this._t('admin.analytics.registrations_30d'), '#3b82f6', d.registrations);
    this._charts.act = mkLine('adm-act-chart', this._t('admin.analytics.analyses_30d'), '#f59e0b', d.daily_activity);

    // Horizontal bar chart showing user count per wilaya; replaced with a placeholder when empty
    const twCtx = document.getElementById('adm-tw-chart');
    if (twCtx) {
      const labels = (d.top_wilayas || []).map(w => w.wilaya);
      const counts = (d.top_wilayas || []).map(w => w.count);

      if (labels.length === 0) {
        twCtx.replaceWith(Object.assign(document.createElement('div'), {
          textContent: '—',
          style: 'text-align:center;color:#64748b;padding:20px',
        }));
      } else {
        this._charts.tw = new Chart(twCtx, {
          type: 'bar',
          data: {
            labels,
            datasets: [{
              data: counts,
              backgroundColor: '#a855f7aa',
              borderColor: '#a855f7',
              borderWidth: 1,
            }],
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { x: { beginAtZero: true } },
          },
        });
      }
    }
  },
};

window.AdminAnalyticsPage = AdminAnalyticsPage;