const App = {
  currentPage: null,
  currentParams: {},
  pageHistory: [],
  _navigatingBack: false,
  charts: {}, // Chart.js instance registry for cleanup

  _capturePageState(page) {
    const hooks = {
      ranking:    () => (typeof RankingPage    !== 'undefined' && RankingPage.getState    ? RankingPage.getState()    : null),
      wilaya:     () => (typeof WilayaDashboard !== 'undefined' && WilayaDashboard.getState ? WilayaDashboard.getState() : null),
      zone:       () => (typeof ZoneAnalysis   !== 'undefined' && ZoneAnalysis.getState   ? ZoneAnalysis.getState()   : null),
      comparison: () => (typeof ComparisonPage !== 'undefined' && ComparisonPage.getState ? ComparisonPage.getState() : null),
      forecast:   () => (typeof ForecastPage   !== 'undefined' && ForecastPage.getState   ? ForecastPage.getState()   : null),
      roi:        () => (typeof ROIPage        !== 'undefined' && ROIPage.getState        ? ROIPage.getState()        : null),
    };
    return hooks[page] ? hooks[page]() : null;
  },

  _persistOutgoingPage() {
    if (!this.currentPage) return;
    const state = this._capturePageState(this.currentPage);
    if (typeof AppState !== 'undefined') {
      AppState.savePage(this.currentPage, {
        params: { ...this.currentParams },
        state: state || {},
      });
    }
  },

  openPage(page) {
    if (page === this.currentPage) {
      if (typeof Components !== 'undefined' && Components.closeSidebar) Components.closeSidebar();
      return;
    }
    const params = typeof AppState !== 'undefined'
      ? AppState.mergeNavParams(page, {})
      : {};
    this.navigate(page, params);
  },

  pages: {
    landing:    { title: 'Accueil',               render: (p)    => LandingPage.render(p) },
    ranking:    { title: 'Classement National',    render: (p, s) => RankingPage.render(p, s) },
    wilaya:     { title: 'Dashboard Wilaya',        render: (p, s) => WilayaDashboard.render(p, s) },
    zone:       { title: 'Analyse de Zone',         render: (p, s) => ZoneAnalysis.render(p, s) },
    comparison: { title: 'Comparaison de Sites',    render: (p, s) => ComparisonPage.render(p, s) },
    forecast:   { title: 'Prévisions IA',           render: (p, s) => ForecastPage.render(p, s) },
    roi:        { title: 'Analyse ROI',             render: (p, s) => ROIPage.render(p, s) },
    reports:    { title: 'Rapports',                render: (p)    => ReportsPage.render(p) },
    history:    { title: 'Historique',              render: (p)    => HistoryPage.render(p) },
    offline:    { title: 'Centre Hors-Ligne',        render: (p)    => OfflinePage.render(p) },
    login:      { title: 'Connexion',               render: (p)    => LoginPage.render(p) },
    register:   { title: 'Inscription',             render: (p)    => RegisterPage.render(p) },
    profile:    { title: 'Profil',                  render: (p)    => ProfilePage.render(p) },
    pricing:    { title: 'Tarification',             render: (p)    => PricingPage.render(p) },
    'admin-dashboard': { title: 'Admin — Dashboard',     render: (p, s) => AdminDashboardPage.render(p, s) },
    'admin-users':     { title: 'Admin — Utilisateurs',  render: (p, s) => AdminUsersPage.render(p, s) },
    // Phase 3+: admin sub-pages all redirect to admin-dashboard
    'admin-analytics': { title: 'Admin — Dashboard',     render: (p, s) => AdminDashboardPage.render(p, s) },
    'admin-logs':      { title: 'Admin — Dashboard',     render: (p, s) => AdminDashboardPage.render(p, s) },
    'admin-reports':   { title: 'Admin — Dashboard',     render: (p, s) => AdminDashboardPage.render(p, s) },
  },

  async init() {
    try { if (window.I18N_READY) await window.I18N_READY; } catch (e) {}

    await new Promise(r => setTimeout(r, 600));

    if (window.Plan && typeof Plan.refresh === 'function') {
      Plan.refresh().catch(() => {});
    }

    Components.renderAppShell();

    if (!document.getElementById('toast-container')) {
      const tc = document.createElement('div');
      tc.id = 'toast-container';
      document.body.appendChild(tc);
    }

    window.addEventListener('online', () => {
      const badge = document.getElementById('connection-badge');
      if (badge) { badge.className = 'connection-badge online'; badge.textContent = 'En ligne'; }
      API.syncPendingActions().catch(err => console.warn('Offline sync failed:', err));
      Utils.toast('success', 'Connexion rétablie', 'Synchronisation en cours...');
    });

    window.addEventListener('offline', () => {
      const badge = document.getElementById('connection-badge');
      if (badge) { badge.className = 'connection-badge offline'; badge.textContent = 'Hors ligne'; }
      Utils.toast('warning', 'Mode hors-ligne', 'Utilisation des données en cache');
    });

    const splash = document.getElementById('splash-screen');
    if (splash) {
      setTimeout(() => { splash.classList.add('hidden'); }, 300);
    }

    try {
      const wilayaRes = await API.getWilayas();
      window.ALL_WILAYAS = wilayaRes?.data?.length ? wilayaRes.data : MOCK_DATA.wilayas;
    } catch (err) {
      window.ALL_WILAYAS = MOCK_DATA.wilayas;
    }

    // Verify existing session before rendering protected pages
    const cachedUser = sessionStorage.getItem('user');
    if (cachedUser) {
      const verifyRes = await API.verify();
      if (!verifyRes?.authenticated) {
        // Token expired or user deleted — clear session and force re-login
        sessionStorage.removeItem('user');
        sessionStorage.removeItem('auth_token');
        if (window.Components) Components.renderAppShell();
        this.navigate('login', {}, { replaceHistory: true });
        return;
      }
    }

    setTimeout(() => {
      const hash = window.location.hash.slice(1);
      if (hash) {
        const [page, queryStr] = hash.split('?');
        const params = {};
        if (queryStr) {
          new URLSearchParams(queryStr).forEach((v, k) => { params[k] = v; });
        }
        if (this.pages[page]) {
          this.navigate(page, params, { replaceHistory: true });
          return;
        }
      }
      this.navigate('landing', {}, { replaceHistory: true });
    }, 500);
  },

  async navigate(page, params = {}, options = {}) {
    const publicPages = ['landing', 'login', 'register', 'pricing'];

    if (!publicPages.includes(page) && !API.isAuthenticated()) {
      localStorage.setItem('intendedPage', page);
      localStorage.setItem('intendedParams', JSON.stringify(params));
      if (window.Utils && window.I18N) {
        Utils.toast('warning', I18N.t('common.error'), I18N.t('auth.login_required'));
      }
      page = 'login';
      params = {};
    }

    if (page && page.startsWith('admin-')) {
      const isAdmin = (window.Auth && Auth.isAdmin && Auth.isAdmin());
      if (!isAdmin) {
        if (window.Utils && window.I18N) {
          Utils.toast('warning', I18N.t('common.error') || 'Erreur',
                      I18N.t('admin.required') || 'Accès administrateur requis');
        }
        page = 'landing';
        params = {};
      }
    }

    // TODO: restore plan-based access restrictions when testing is complete

    const pageDef = this.pages[page];
    if (!pageDef) {
      console.warn(`Page "${page}" not found`);
      this.navigate('landing');
      return;
    }

    const mergedParams = typeof AppState !== 'undefined'
      ? AppState.mergeNavParams(page, params)
      : { ...params };

    const savedSnapshot = typeof AppState !== 'undefined' ? AppState.getPage(page) : null;
    const restoreState = options.restoreState !== false ? (savedSnapshot?.state || {}) : {};

    if (!this._navigatingBack && this.currentPage && this.currentPage !== page) {
      this._persistOutgoingPage();
      this.pageHistory.push({ page: this.currentPage, params: { ...this.currentParams } });
      if (this.pageHistory.length > 20) this.pageHistory.shift();
    }

    this.cleanupCharts();

    // Call cleanup() on outgoing admin page if defined (e.g. polling timers)
    try {
      if (this.currentPage && this.currentPage.startsWith('admin-')) {
        const mod = (this.currentPage === 'admin-dashboard' && window.AdminDashboardPage) ||
                    (this.currentPage === 'admin-users'     && window.AdminUsersPage)     ||
                    (this.currentPage === 'admin-analytics' && window.AdminAnalyticsPage) ||
                    (this.currentPage === 'admin-logs'      && window.AdminLogsPage)      ||
                    (this.currentPage === 'admin-reports'   && window.AdminReportsPage)   || null;
        if (mod && typeof mod.cleanup === 'function') mod.cleanup();
      }
    } catch (_) {}

    const pageContent = document.getElementById('page-content');
    if (pageContent) pageContent.scrollTop = 0;

    this.currentPage = page;
    this.currentParams = mergedParams;

    Components.setActivePage(page);
    this.updateTopbar(pageDef.title, page);

    if (typeof Components !== 'undefined' && Components.closeSidebar) {
      Components.closeSidebar();
    }

    const hash = `#${page}${Object.keys(mergedParams).length ? '?' + new URLSearchParams(mergedParams).toString() : ''}`;
    if (!this._navigatingBack && !options.replaceHistory) {
      history.pushState({ page, params: mergedParams }, '', hash);
    } else {
      history.replaceState({ page, params: mergedParams }, '', hash);
    }

    try {
      await pageDef.render(mergedParams, restoreState);
      if (window.I18N?.applyDom) I18N.applyDom();
    } catch (err) {
      console.error(`Error rendering page "${page}":`, err);
      this.renderErrorPage(page, err);
    } finally {
      this._navigatingBack = false;
    }
  },

  updateTopbar(title, page) {
    const topbar = document.getElementById('topbar');
    if (!topbar) return;

    const existing = topbar.querySelector('.topbar-breadcrumb');
    if (existing) existing.remove();

    const breadcrumb = document.createElement('div');
    breadcrumb.className = 'topbar-breadcrumb';
    breadcrumb.innerHTML = `
      <span onclick="App.navigate('landing')" style="cursor:pointer">SolarDecide DZ</span>
      <span class="sep">/</span>
      <span class="current">${title}</span>
    `;

    const spacer = topbar.querySelector('.topbar-spacer');
    if (spacer) topbar.insertBefore(breadcrumb, spacer);

    document.title = `${title} — SolarDecide DZ`;
  },

  renderErrorPage(page, error) {
    const content = document.getElementById('page-content');
    if (!content) return;
    content.innerHTML = `
      <div class="page-wrapper">
        <div class="card" style="max-width:500px;margin:40px auto">
          <div class="card-body text-center">
            ${Components.emptyState(
              'fa-exclamation-triangle',
              `Erreur lors du chargement de "${page}"`,
              error?.message || 'Une erreur inattendue s\'est produite.',
              `<button class="btn btn-primary" onclick="App.navigate('landing')">
                <i class="fas fa-home"></i> Retour à l'accueil
              </button>`
            )}
          </div>
        </div>
      </div>
    `;
  },

  cleanupCharts() {
    // Destroy all Chart.js instances to prevent memory leaks between page navigations
    if (typeof Chart !== 'undefined') {
      Chart.helpers?.each(Chart.instances, function(instance) {
        try { instance.destroy(); } catch(e) {}
      });
    }
  },

  goBack() {
    if (this.pageHistory.length > 0) {
      const prev = this.pageHistory.pop();
      this._navigatingBack = true;
      this.navigate(prev.page, prev.params, { replaceHistory: true });
    } else if (window.history.length > 1) {
      window.history.back();
    } else {
      this.navigate('landing');
    }
  },
};

// Sync browser back/forward buttons with internal navigation state
window.addEventListener('popstate', (event) => {
  const state = event.state;
  if (state?.page && App.pages[state.page]) {
    App._navigatingBack = true;
    App.navigate(state.page, state.params || {}, { replaceHistory: true });
    return;
  }
  const hash = window.location.hash.slice(1);
  if (!hash) return;
  const [page, queryStr] = hash.split('?');
  const params = {};
  if (queryStr) {
    new URLSearchParams(queryStr).forEach((v, k) => { params[k] = v; });
  }
  if (App.pages[page]) {
    App._navigatingBack = true;
    App.navigate(page, params, { replaceHistory: true });
  }
});

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

window.App = App;