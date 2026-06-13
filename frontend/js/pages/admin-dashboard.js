const AdminDashboardPage = {
  // Auto-refresh timer handle, chart instances registry, and cached API payloads
  _timer: null,
  _charts: {},
  _stats: null,
  _ana: null,
  _logs: null,

  // Resolves a translation key with an optional fallback string
  _t(k, f = '') {
    return (typeof I18N !== 'undefined' && I18N.t) ? (I18N.t(k) || f) : f;
  },

  // Renders the loading skeleton, triggers the first data fetch,
  // then starts a 60-second auto-refresh interval
  async render() {
    const content = document.getElementById('page-content');
    content.innerHTML = `<div class="page-wrapper">${Components.loading('', 'Chargement du tableau de bord…')}</div>`;
    await this._refresh();
    if (this._timer) clearInterval(this._timer);
    this._timer = setInterval(() => this._refresh(), 60000);
  },

  // Clears the refresh timer and destroys all chart instances on page exit
  cleanup() {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
    this._destroyCharts();
  },

  // Safely destroys every Chart.js instance to prevent canvas reuse errors
  _destroyCharts() {
    Object.values(this._charts).forEach(c => { try { c.destroy(); } catch (_) {} });
    this._charts = {};
  },

  // Fetches stats, analytics, and logs in parallel, then re-renders the full page
  async _refresh() {
    const [stats, ana, logs] = await Promise.all([
      DataService.adminDashboardStats(),
      DataService.adminAnalytics(),
      DataService.adminLogs({ type: 'all', date: '' }),
    ]);

    // Abort render and show an access-denied message if the user is not an admin
    if (!stats) {
      document.getElementById('page-content').innerHTML = `
        <div class="page-wrapper">
          <div class="alert-card" style="max-width:520px;margin:60px auto;text-align:center;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-md);padding:32px">
            <i class="fas fa-shield-halved" style="font-size:36px;color:var(--amber-400);margin-bottom:12px"></i>
            <h3 style="color:var(--text-primary);margin:0 0 6px">Accès réservé</h3>
            <p style="color:var(--text-secondary);margin:0">${this._t('admin.required', 'Vous devez être administrateur pour accéder à cette page.')}</p>
          </div>
        </div>`;
      return;
    }

    // Normalize optional payloads to safe empty structures
    this._stats = stats;
    this._ana   = ana  || { labels: [], registrations: [], top_wilayas: [] };
    this._logs  = logs || { activities: [], errors: [] };

    document.getElementById('page-content').innerHTML = this._template();
    if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();
    this._renderCharts();
    this._bindRefreshBtn();
  },

  // Assembles the full page HTML: sticky header, KPI cards, charts, and log tables
  _template() {
    const d   = this._stats;
    const t   = (k, f = '') => this._t(k, f);
    const now = new Date().toLocaleString('fr-DZ');

    // Returns a KPI card with an icon, label, primary value, and optional sub-label
    const kpi = (icon, color, label, value, sub = '') => `
      <div class="kpi-card ${color}">
        <div class="kpi-header">
          <span class="kpi-label">${label}</span>
          <span class="kpi-icon ${color}"><i class="fas ${icon}"></i></span>
        </div>
        <div class="kpi-value">${value}</div>
        ${sub ? `<div class="kpi-sub">${sub}</div>` : ''}
      </div>`;

    // Returns a single plan distribution row with its color-coded plan name and count
    const planBadge = (plan, count) => {
      const colors = { free: 'var(--text-muted)', pro: 'var(--teal-400)', enterprise: 'var(--amber-400)' };
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color)">
        <span style="color:${colors[plan] || 'var(--text-secondary)'};font-weight:600;font-size:13px;text-transform:capitalize">${plan}</span>
        <span style="color:var(--text-primary);font-weight:700;font-size:16px">${count}</span>
      </div>`;
    };

    // Builds activity log rows, capped at 50 entries; falls back to an empty-state row
    const actRows = (this._logs.activities || []).slice(0, 50).map(a => {
      const actionColor = {
        login:        'var(--teal-400)',
        analyse_zone: 'var(--amber-400)',
        calcul_roi:   'var(--blue-300)',
        rapport:      'var(--purple-500)',
        forecast:     'var(--green-400)',
      }[a.action] || 'var(--text-muted)';

      const userHtml = a.user
        ? `<span style="color:var(--text-primary);font-weight:500">${this._esc(a.user.name)}</span>
           <br><span style="font-size:11px;color:var(--text-muted);font-family:monospace">${this._esc(a.user.email)}</span>`
        : `<span style="color:var(--text-muted);font-style:italic">anonyme</span>`;

      return `<tr>
        <td style="white-space:nowrap;font-family:monospace;font-size:11px;color:var(--text-muted)">${a.created_at ? new Date(a.created_at).toLocaleString('fr') : '—'}</td>
        <td>${userHtml}</td>
        <td><span style="display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;background:${actionColor}22;color:${actionColor};border:1px solid ${actionColor}44">${this._esc(a.action)}</span></td>
        <td style="font-size:12px;color:var(--text-secondary);max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${this._esc(a.details || '')}">${this._esc(a.details || '—')}</td>
      </tr>`;
    }).join('') || `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--text-muted)"><i class="fas fa-inbox"></i> Aucune activité récente</td></tr>`;

    // Builds error log rows, capped at 50 entries; falls back to an all-clear row
    const errRows = (this._logs.errors || []).slice(0, 50).map(e => {
      const userHtml = e.user
        ? `<span style="color:var(--text-primary);font-weight:500">${this._esc(e.user.name)}</span>
           <br><span style="font-size:11px;color:var(--text-muted);font-family:monospace">${this._esc(e.user.email)}</span>`
        : `<span style="color:var(--text-muted);font-style:italic">anonyme</span>`;

      return `<tr>
        <td style="white-space:nowrap;font-family:monospace;font-size:11px;color:var(--text-muted)">${e.created_at ? new Date(e.created_at).toLocaleString('fr') : '—'}</td>
        <td style="font-size:12px;color:var(--red-400);font-family:monospace">${this._esc(e.message)}</td>
        <td style="font-size:11px;color:var(--text-muted)">${this._esc(e.page || '—')}</td>
        <td>${userHtml}</td>
      </tr>`;
    }).join('') || `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--text-muted)"><i class="fas fa-check-circle" style="color:var(--green-400)"></i> Aucune erreur récente</td></tr>`;

    return `
<div class="page-wrapper">

  <!-- Sticky zone: page header, KPI cards, and summary charts -->
  <div class="adm-sticky-top">

    <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin-bottom:14px">
      <div>
        <h1 style="margin:0;color:var(--text-primary)">
          <i class="fas fa-tachometer-alt" style="color:var(--amber-400)"></i>
          ${t('admin.dashboard.title', 'Tableau de bord admin')}
        </h1>
        <p style="margin:4px 0 0;color:var(--text-muted);font-size:13px">
          Données en temps réel depuis SQLite · Mise à jour : ${now}
        </p>
      </div>
      <button id="adm-refresh-btn" style="display:flex;align-items:center;gap:6px;padding:8px 16px;background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:var(--radius-sm);color:var(--text-secondary);font-size:13px;cursor:pointer">
        <i class="fas fa-rotate"></i> Actualiser
      </button>
    </div>

    <!-- Six KPI cards covering users, daily/monthly activity, and reports -->
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:14px">
      ${kpi('fa-users',      'amber',  'Inscrits',      d.total_users,    'total')}
      ${kpi('fa-user-check', 'teal',   'Actifs/jour',   d.active_today,   "aujourd'hui")}
      ${kpi('fa-chart-line', 'blue',   'Analyses/jour', d.analyses_today, "aujourd'hui")}
      ${kpi('fa-chart-bar',  'purple', 'Analyses/mois', d.analyses_month, 'ce mois')}
      ${kpi('fa-file-pdf',   'red',    'Rapports/jour', d.reports_today,  "aujourd'hui")}
      ${kpi('fa-file-alt',   'green',  'Rapports/mois', d.reports_month,  'ce mois')}
    </div>

    <!-- Three-column chart row: registrations trend, plan breakdown, top wilayas -->
    <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:14px">

      <div class="card">
        <div class="card-header" style="padding:10px 14px">
          <h3 style="margin:0;color:var(--text-primary);font-size:13px">
            <i class="fas fa-user-plus" style="color:var(--teal-400);margin-right:6px"></i>
            Inscriptions — 30 derniers jours
          </h3>
        </div>
        <div class="card-body" style="padding:10px 14px">
          <div style="position:relative;height:110px"><canvas id="adm-reg-chart"></canvas></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header" style="padding:10px 14px">
          <h3 style="margin:0;color:var(--text-primary);font-size:13px">
            <i class="fas fa-layer-group" style="color:var(--amber-400);margin-right:6px"></i>
            Plans
          </h3>
        </div>
        <div class="card-body" style="padding:10px 14px">
          <div style="position:relative;height:70px"><canvas id="adm-plan-chart"></canvas></div>
          <div style="margin-top:6px;border-top:1px solid var(--border-color);padding-top:6px">
            ${planBadge('free',       d.plan_distribution?.free       ?? 0)}
            ${planBadge('pro',        d.plan_distribution?.pro        ?? 0)}
            ${planBadge('enterprise', d.plan_distribution?.enterprise ?? 0)}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header" style="padding:10px 14px">
          <h3 style="margin:0;color:var(--text-primary);font-size:13px">
            <i class="fas fa-map-marker-alt" style="color:var(--amber-400);margin-right:6px"></i>
            Top 5 wilayas
          </h3>
        </div>
        <div class="card-body" style="padding:10px 14px">
          ${(d.top_wilayas && d.top_wilayas.length)
            ? `<div style="position:relative;height:110px"><canvas id="adm-top-wilayas"></canvas></div>`
            : `<div style="text-align:center;padding:16px;color:var(--text-muted);font-size:12px"><i class="fas fa-database" style="font-size:18px;margin-bottom:6px;display:block"></i>Aucune analyse ce mois</div>`
          }
        </div>
      </div>

    </div>
  </div>
  <!-- End sticky zone -->

  <!-- Log tables scroll normally below the sticky header -->
  <div style="display:grid;grid-template-columns:1fr;gap:18px;margin-top:18px">

    <div class="card">
      <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
        <h3 style="margin:0;color:var(--text-primary);font-size:15px">
          <i class="fas fa-list-check" style="color:var(--teal-400);margin-right:6px"></i>
          Dernières actions <span style="color:var(--text-muted);font-weight:400;font-size:12px">(50 dernières)</span>
        </h3>
        <span style="font-size:11px;color:var(--text-muted)">activity_logs</span>
      </div>
      <div class="card-body" style="padding:0;overflow-x:auto">
        <table class="adm-log-table">
          <thead>
            <tr>
              <th>Date</th><th>Utilisateur</th><th>Action</th><th>Détails</th>
            </tr>
          </thead>
          <tbody>${actRows}</tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
        <h3 style="margin:0;color:var(--text-primary);font-size:15px">
          <i class="fas fa-triangle-exclamation" style="color:var(--red-400);margin-right:6px"></i>
          Dernières erreurs <span style="color:var(--text-muted);font-weight:400;font-size:12px">(50 dernières)</span>
        </h3>
        <span style="font-size:11px;color:var(--text-muted)">error_logs</span>
      </div>
      <div class="card-body" style="padding:0;overflow-x:auto">
        <table class="adm-log-table">
          <thead>
            <tr>
              <th>Date</th><th>Message</th><th>Page</th><th>Utilisateur</th>
            </tr>
          </thead>
          <tbody>${errRows}</tbody>
        </table>
      </div>
    </div>

  </div>
</div>

<style>
/* KPI card base + per-color top accent bar */
.kpi-card { background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-md);padding:18px 20px;position:relative;overflow:hidden }
.kpi-card::before { content:'';position:absolute;top:0;left:0;right:0;height:3px }
.kpi-card.amber::before  { background:linear-gradient(90deg,var(--amber-500),var(--amber-300)) }
.kpi-card.teal::before   { background:linear-gradient(90deg,var(--teal-500),var(--teal-300)) }
.kpi-card.blue::before   { background:linear-gradient(90deg,var(--blue-300),#60a5fa) }
.kpi-card.purple::before { background:linear-gradient(90deg,var(--purple-500),#a78bfa) }
.kpi-card.red::before    { background:linear-gradient(90deg,var(--red-400),#f87171) }
.kpi-card.green::before  { background:linear-gradient(90deg,var(--green-400),#34d399) }

/* KPI card internal layout */
.kpi-header { display:flex;justify-content:space-between;align-items:center;margin-bottom:10px }
.kpi-label  { font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);font-weight:600 }
.kpi-icon   { width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px }
.kpi-icon.amber  { background:rgba(245,158,11,.15);color:var(--amber-400) }
.kpi-icon.teal   { background:rgba(20,184,166,.15);color:var(--teal-400) }
.kpi-icon.blue   { background:rgba(59,130,246,.15);color:var(--blue-300) }
.kpi-icon.purple { background:rgba(139,92,246,.15);color:var(--purple-500) }
.kpi-icon.red    { background:rgba(239,68,68,.15);color:var(--red-400) }
.kpi-icon.green  { background:rgba(34,197,94,.15);color:var(--green-400) }
.kpi-value { font-size:28px;font-weight:800;color:var(--text-primary);line-height:1 }
.kpi-sub   { font-size:11px;color:var(--text-muted);margin-top:4px }

/* Shared log table styles for both activity and error panels */
.adm-log-table { width:100%;border-collapse:collapse;font-size:13px }
.adm-log-table th { padding:10px 14px;background:var(--bg-elevated);color:var(--text-secondary);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;text-align:left;white-space:nowrap }
.adm-log-table td { padding:10px 14px;border-bottom:1px solid var(--border-color);color:var(--text-primary);vertical-align:middle }
.adm-log-table tbody tr:hover { background:rgba(255,255,255,.03) }
.adm-log-table tbody tr:last-child td { border-bottom:none }

/* Sticky header zone sits above scrollable log tables */
.adm-sticky-top {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--bg-page, var(--bg-primary, #0f172a));
  padding-bottom: 10px;
  margin-bottom: 0;
  box-shadow: 0 4px 16px rgba(0,0,0,0.35);
}

/* Compact KPI sizing inside the sticky zone to save vertical space */
.adm-sticky-top .kpi-card  { padding: 12px 14px }
.adm-sticky-top .kpi-value { font-size: 22px }
</style>`;
  },

  // Instantiates the three Chart.js charts: registrations line, plan donut, and wilayas bar
  _renderCharts() {
    if (typeof Chart === 'undefined') return;
    this._destroyCharts();

    const gridCol = 'rgba(255,255,255,0.06)';
    const tickCol = '#9ca3af';

    // 30-day registration trend — date labels are reformatted to DD/MM for readability
    const regCtx = document.getElementById('adm-reg-chart');
    if (regCtx && this._ana?.labels?.length) {
      const labels = this._ana.labels.map(d => {
        const [, m, day] = d.split('-');
        return `${day}/${m}`;
      });
      this._charts.reg = new Chart(regCtx, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'Inscriptions',
            data: this._ana.registrations || [],
            borderColor: '#14b8a6',
            backgroundColor: 'rgba(20,184,166,0.12)',
            borderWidth: 2,
            pointRadius: 3,
            pointHoverRadius: 5,
            pointBackgroundColor: '#14b8a6',
            fill: true,
            tension: 0.4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { color: tickCol, stepSize: 1 }, grid: { color: gridCol } },
            x: { ticks: { color: tickCol, maxTicksLimit: 10 }, grid: { color: 'transparent' } },
          },
        },
      });
    }

    // Doughnut chart showing the free / pro / enterprise user split
    const planCtx = document.getElementById('adm-plan-chart');
    if (planCtx && this._stats?.plan_distribution) {
      const pd = this._stats.plan_distribution;
      this._charts.plan = new Chart(planCtx, {
        type: 'doughnut',
        data: {
          labels: ['Free', 'Pro', 'Enterprise'],
          datasets: [{
            data: [pd.free || 0, pd.pro || 0, pd.enterprise || 0],
            backgroundColor: ['rgba(107,114,128,0.6)', 'rgba(20,184,166,0.7)', 'rgba(245,158,11,0.7)'],
            borderColor: ['#6b7280', '#14b8a6', '#f59e0b'],
            borderWidth: 1.5,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '68%',
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: c => ` ${c.label} : ${c.parsed}` } },
          },
        },
      });
    }

    // Horizontal bar chart for the top 5 wilayas by analysis count
    const topCtx = document.getElementById('adm-top-wilayas');
    if (topCtx && this._stats?.top_wilayas?.length) {
      const tw = this._stats.top_wilayas;
      this._charts.top = new Chart(topCtx, {
        type: 'bar',
        data: {
          labels: tw.map(w => w.wilaya),
          datasets: [{
            data: tw.map(w => w.count),
            backgroundColor: [
              'rgba(245,158,11,0.7)', 'rgba(20,184,166,0.7)',
              'rgba(139,92,246,0.7)', 'rgba(59,130,246,0.7)',
              'rgba(239,68,68,0.7)',
            ],
            borderColor: ['#f59e0b', '#14b8a6', '#8b5cf6', '#3b82f6', '#ef4444'],
            borderWidth: 1.5,
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: 'y',
          plugins: { legend: { display: false } },
          scales: {
            x: { beginAtZero: true, ticks: { color: tickCol, stepSize: 1 }, grid: { color: gridCol } },
            y: { ticks: { color: tickCol } },
          },
        },
      });
    }
  },

  // Wires the manual refresh button; disables it and shows a spinner during the fetch
  _bindRefreshBtn() {
    const btn = document.getElementById('adm-refresh-btn');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Actualisation…';
      await this._refresh();
    });
  },

  // Escapes HTML special characters to prevent XSS when rendering user-supplied data
  _esc(v) {
    return (v == null) ? '' : String(v).replace(/</g, '&lt;').replace(/>/g, '&gt;');
  },
};

window.AdminDashboardPage = AdminDashboardPage;