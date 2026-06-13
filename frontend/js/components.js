const Components = {

  renderAppShell() {
    const appEl = document.getElementById('app');
    if (!appEl) return;

    appEl.innerHTML = `
      <div id="app-layout">
        ${this.renderSidebar()}
        <div id="main-area">
          ${this.renderTopbar()}
          <div id="page-content"></div>
        </div>
      </div>
      <div id="toast-container"></div>
      ${this.renderMobileOverlay()}
    `;
    this.bindSidebar();
  },

  renderSidebar() {
    const isAdmin = (window.Auth && Auth.isAdmin && Auth.isAdmin())
                 || (window.AppState && AppState.user && (AppState.user.role || '').toLowerCase() === 'admin');

    const navSections = [
      {
        label: I18N.t('nav.analysis'),
        items: [
          { page: 'landing',    icon: 'fa-home',      label: I18N.t('nav.home') },
          { page: 'ranking',    icon: 'fa-trophy',    label: I18N.t('nav.ranking') },
          { page: 'wilaya',     icon: 'fa-map',       label: I18N.t('nav.wilaya') },
          { page: 'zone',       icon: 'fa-crosshairs',label: I18N.t('nav.zone') },
          { page: 'comparison', icon: 'fa-columns',   label: I18N.t('nav.comparison') },
        ]
      },
      {
        label: I18N.t('nav.intelligence'),
        items: [
          { page: 'forecast', icon: 'fa-chart-line', label: I18N.t('nav.forecast') },
        ]
      },
      {
        label: I18N.t('nav.planning'),
        items: [
          { page: 'roi',     icon: 'fa-dollar-sign', label: I18N.t('nav.roi') },
          { page: 'reports', icon: 'fa-file-pdf',    label: I18N.t('nav.reports') },
          { page: 'pricing', icon: 'fa-tags',        label: I18N.t('nav.pricing') },
        ]
      }
    ];

    // Admin section only visible to admin users
    if (isAdmin) {
      navSections.push({
        label: I18N.t('admin.section_label') || 'Administration',
        items: [
          { page: 'admin-dashboard', icon: 'fa-tachometer-alt',
            label: I18N.t('admin.nav.dashboard') || 'Tableau de bord' },
          { page: 'admin-users', icon: 'fa-users',
            label: I18N.t('admin.nav.users') || 'Gérer utilisateurs' },
          // analytics/logs/reports are consolidated into admin-dashboard
        ]
      });
    }

    const sectionsHTML = navSections.map(section => `
      <div class="nav-section">
        <div class="nav-section-label">${section.label}</div>
        ${section.items.map(item => `
          <div class="nav-item" data-page="${item.page}" onclick="App.openPage('${item.page}')">
            <span class="nav-icon"><i class="fas ${item.icon}"></i></span>
            <span class="nav-label">${item.label}</span>
            ${item.badge ? `<span class="nav-badge" ${item.badgeId ? `id="${item.badgeId}" style="display:none"` : ''}>${item.badge}</span>` : ''}
          </div>
        `).join('')}
      </div>
    `).join('');

    return `
      <nav id="sidebar">
        <div class="sidebar-header">
          <div class="sidebar-logo" onclick="App.navigate('landing')" style="cursor:pointer">
            <div class="logo-icon"><i class="fas fa-sun"></i></div>
            <div class="logo-text">
              <div class="brand">SolarDecide <span style="color:var(--amber-400)">DZ</span></div>
              <div class="sub">AI Solar Platform</div>
            </div>
          </div>
          <button class="sidebar-toggle" id="sidebar-toggle" onclick="Components.closeSidebar()" data-tooltip="Fermer">
            <i class="fas fa-times" id="sidebar-toggle-icon"></i>
          </button>
        </div>
        <div class="sidebar-nav">${sectionsHTML}</div>
        <div class="sidebar-footer">
          ${API.isAuthenticated() ? `
            <div class="sidebar-footer-btn" onclick="App.navigate('profile')">
              <i class="fas fa-user"></i><span>Profil</span>
            </div>
            <div class="sidebar-footer-btn" onclick="API.logout()">
              <i class="fas fa-sign-out-alt"></i><span>Déconnexion</span>
            </div>
          ` : `
            <div class="sidebar-footer-btn" onclick="App.navigate('login')">
              <i class="fas fa-sign-in-alt"></i><span>Connexion</span>
            </div>
          `}
        </div>
      </nav>
    `;
  },

  renderTopbar() {
    const planHtml = (window.Plan && API.isAuthenticated()) ? Plan.badgeHtml() : '';
    return `
      <header id="topbar">
        <button class="mobile-menu-btn" id="mobile-menu-btn" onclick="Components.toggleMobileMenu()">
          <i class="fas fa-bars"></i>
        </button>
        <div class="topbar-search">
          <i class="fas fa-search" style="color:var(--text-muted);font-size:13px;flex-shrink:0"></i>
          <input type="text" data-i18n-placeholder="topbar.search"
                 placeholder="${I18N.t('topbar.search')}" id="global-search" autocomplete="off" />
        </div>
        <div class="topbar-spacer"></div>
        <div class="topbar-actions">
          <div class="connection-badge online" id="connection-badge" data-i18n="topbar.online">
            ${I18N.t('topbar.online')}
          </div>
          ${planHtml}
          <!-- FR <-> EN only; AR disabled with "coming soon" tooltip -->
          <div class="lang-selector" onclick="Components.cycleLang()" id="lang-selector"
               data-i18n-tooltip="topbar.language" data-tooltip="${I18N.t('topbar.language')}">
            <i class="fas fa-globe" style="font-size:11px"></i>
            <span id="lang-label">${(I18N.currentLang || 'fr').toUpperCase()}</span>
          </div>
          <div class="lang-selector" id="lang-ar-disabled"
               style="opacity:0.45;cursor:not-allowed;pointer-events:auto"
               data-i18n-tooltip="topbar.ar_soon"
               data-tooltip="${I18N.t('topbar.ar_soon')}"
               onclick="Utils.toast('info', I18N.t('topbar.ar_soon'), '');">
            <i class="fas fa-globe" style="font-size:11px"></i>
            <span>AR</span>
          </div>
          ${API.isAuthenticated() ? `
            <div class="user-avatar" data-tooltip="${I18N.t('topbar.profile')}" onclick="Components.toggleProfileMenu(event)" id="user-avatar-btn">
              ${(() => {
                let user = sessionStorage.getItem('user') || localStorage.getItem('user');
                if (user) {
                  try {
                    const userObj = JSON.parse(user);
                    if (userObj.profile_picture) {
                      return `<img src="${userObj.profile_picture}" alt="Profile" class="user-img">`;
                    }
                    const name = userObj.name || userObj.email || '';
                    if (name) {
                      const initials = name.split(' ').map(part => part[0]).join('').toUpperCase().substring(0, 2);
                      return `<div class="user-initials">${initials}</div>`;
                    }
                  } catch (e) {}
                  return '<div class="user-initials">?</div>';
                }
                return '<div class="user-initials">?</div>';
              })()}
            </div>
          ` : `
            <div class="user-avatar" data-tooltip="${I18N.t('topbar.login')}" onclick="App.navigate('login')">
              <i class="fas fa-user"></i>
            </div>
          `}
        </div>
      </header>
    `;
  },

  renderSidebarBackdrop() {
    return `<div id="sidebar-backdrop" onclick="Components.closeSidebar()"></div>`;
  },

  // Alias for backward compatibility
  renderMobileOverlay() {
    return Components.renderSidebarBackdrop();
  },

  bindSidebar() {
    // Debounced global search
    const searchInput = document.getElementById('global-search');
    if (searchInput) {
      searchInput.addEventListener('input', Utils.debounce(async (e) => {
        const q = e.target.value.trim();
        if (q.length < 2) return Components.hideSearchResults();
        const res = await API.search(q);
        Components.showSearchResults(res.data);
      }, 250));

      searchInput.addEventListener('blur', () => {
        setTimeout(() => Components.hideSearchResults(), 200);
      });
    }
  },

  // Sidebar is overlay-only (no icon-collapsed mode), so toggle just closes it
  toggleSidebar() {
    Components.closeSidebar();
  },

  openSidebar() {
    document.body.classList.add('sidebar-open');
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.add('mobile-open');
  },

  closeSidebar() {
    document.body.classList.remove('sidebar-open');
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.remove('mobile-open');
  },

  toggleMobileMenu() {
    if (document.body.classList.contains('sidebar-open')) {
      Components.closeSidebar();
    } else {
      Components.openSidebar();
    }
  },

  setActivePage(page) {
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.page === page);
    });
  },

  showSearchResults(results) {
    Components.hideSearchResults();
    if (!results.length) return;

    const dropdown = document.createElement('div');
    dropdown.id = 'search-dropdown';
    dropdown.style.cssText = `
      position:absolute; top:100%; left:0; right:0;
      background:var(--bg-card); border:1px solid var(--border-color);
      border-radius:var(--radius-md); margin-top:4px;
      z-index:200; overflow:hidden; box-shadow:var(--shadow-lg);
    `;

    dropdown.innerHTML = results.slice(0, 8).map(r => `
      <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;transition:background 0.15s"
        onmouseover="this.style.background='var(--bg-elevated)'" onmouseout="this.style.background=''"
        onclick="App.navigate('${r.type === 'wilaya' ? 'wilaya' : 'zone'}', ${r.type === 'wilaya' ? `{code:'${r.id}'}` : `{zoneId:'${r.id}'}`})">
        <i class="fas ${r.type === 'wilaya' ? 'fa-map-marker-alt' : 'fa-crosshairs'}" style="color:var(--amber-400);font-size:12px;width:14px"></i>
        <div>
          <div style="font-size:13px;font-weight:600;color:var(--text-primary)">${r.name}</div>
          <div style="font-size:11px;color:var(--text-muted)">${r.subtitle}</div>
        </div>
        <span class="badge ${r.type === 'wilaya' ? 'badge-amber' : 'badge-teal'}" style="margin-left:auto;font-size:10px">${r.type}</span>
      </div>
    `).join('');

    const searchWrap = document.querySelector('.topbar-search');
    if (searchWrap) {
      searchWrap.style.position = 'relative';
      searchWrap.appendChild(dropdown);
    }
  },

  hideSearchResults() {
    const el = document.getElementById('search-dropdown');
    if (el) el.remove();
  },

  async cycleLang() {
    const langs = I18N.availableLangs; // ['fr', 'en']
    const idx = langs.indexOf(I18N.currentLang);
    const next = langs[(idx + 1) % langs.length];
    await I18N.setLang(next);
    const label = document.getElementById('lang-label');
    if (label) label.textContent = next.toUpperCase();
  },

  // no-op stub — notifications removed; kept to avoid call-site errors
  showNotifications() {},

  async toggleProfileMenu(evt) {
    if (evt) { evt.stopPropagation(); }

    const existing = document.getElementById('profile-dropdown');
    if (existing) { existing.remove(); return; }

    if (!API.isAuthenticated()) {
      App.navigate('login');
      return;
    }

    let user = null;
    try { user = await API.getCurrentUser(); } catch (e) {}
    if (!user) {
      try { user = JSON.parse(sessionStorage.getItem('user') || 'null'); } catch (e) { user = null; }
    }
    user = user || {};

    const joined = user.created_at
      ? new Date(user.created_at).toLocaleDateString(I18N.currentLang === 'en' ? 'en-GB' : 'fr-FR')
      : '—';

    const dropdown = document.createElement('div');
    dropdown.id = 'profile-dropdown';
    dropdown.style.cssText = `
      position:fixed; top:64px; right:16px;
      width:280px; background:var(--bg-card);
      border:1px solid var(--border-color);
      border-radius:var(--radius-xl);
      z-index:1100; box-shadow:var(--shadow-lg);
      overflow:hidden; animation:scaleIn 0.18s ease;
    `;
    dropdown.innerHTML = `
      <div style="padding:14px 16px;border-bottom:1px solid var(--border-color);display:flex;align-items:center;gap:12px">
        <div class="user-initials" style="width:38px;height:38px;border-radius:50%;background:var(--amber-500);color:#000;display:flex;align-items:center;justify-content:center;font-weight:700">
          ${((user.name || user.email || '?').charAt(0) || '?').toUpperCase()}
        </div>
        <div style="min-width:0">
          <div style="font-weight:700;font-size:14px;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${user.name || '—'}</div>
          <div style="font-size:11px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${user.email || '—'}</div>
        </div>
      </div>
      <div style="padding:10px 16px;border-bottom:1px solid var(--border-color);font-size:12px;color:var(--text-secondary)">
        <div style="display:flex;justify-content:space-between;padding:4px 0">
          <span>${I18N.t('profile.menu.name')}</span>
          <span style="color:var(--text-primary);font-weight:600">${user.name || '—'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:4px 0">
          <span>${I18N.t('profile.menu.email')}</span>
          <span style="color:var(--text-primary);font-weight:600">${user.email || '—'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:4px 0">
          <span>${I18N.t('profile.menu.joined')}</span>
          <span style="color:var(--text-primary);font-weight:600">${joined}</span>
        </div>
      </div>
      <div style="padding:8px">
        <button class="btn btn-ghost btn-sm" style="width:100%;justify-content:flex-start" onclick="document.getElementById('profile-dropdown').remove();App.navigate('profile')">
          <i class="fas fa-user"></i> ${I18N.t('profile.menu.full')}
        </button>
        <button class="btn btn-ghost btn-sm" style="width:100%;justify-content:flex-start;color:var(--red-400)" onclick="document.getElementById('profile-dropdown').remove();API.logout()">
          <i class="fas fa-sign-out-alt"></i> ${I18N.t('profile.menu.logout')}
        </button>
      </div>
    `;
    document.body.appendChild(dropdown);

    // Close on outside click, excluding the avatar button itself
    setTimeout(() => {
      document.addEventListener('click', function close(e) {
        if (!dropdown.contains(e.target) && !e.target.closest('#user-avatar-btn')) {
          dropdown.remove();
          document.removeEventListener('click', close);
        }
      });
    }, 50);
  },

  showSettings() {
    this.showModal('Paramètres', `
      <div class="form-group">
        <label class="form-label">Langue de l'interface</label>
        <select class="form-select" onchange="I18N.setLang(this.value)">
          <option value="fr" ${I18N.currentLang==='fr'?'selected':''}>Français 🇫🇷</option>
          <option value="en" ${I18N.currentLang==='en'?'selected':''}>English 🇬🇧</option>
          <option value="ar" ${I18N.currentLang==='ar'?'selected':''}>العربية 🇩🇿</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Unités d'irradiance</label>
        <select class="form-select">
          <option selected>kWh/m²/an</option>
          <option>MJ/m²/jour</option>
          <option>W/m²</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Devise</label>
        <select class="form-select">
          <option selected>USD ($)</option>
          <option>EUR (€)</option>
          <option>DZD (دج)</option>
        </select>
      </div>
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-color)">
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Version: 1.0.0-beta • Build: 2025.03</div>
        <div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary)">
          <i class="fas fa-graduation-cap" style="color:var(--amber-400)"></i>
          Thèse de Master — Université des Sciences et Technologies d'Oran
        </div>
      </div>
    `);
  },

  showModal(title, content, actions = '') {
    const existing = document.getElementById('modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal">
        <div class="modal-header">
          <div class="modal-title">${title}</div>
          <button class="modal-close" onclick="document.getElementById('modal-overlay').remove()">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">${content}</div>
        ${actions ? `<div class="modal-footer" style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-color);display:flex;gap:8px;justify-content:flex-end">${actions}</div>` : ''}
      </div>
    `;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
    return overlay;
  },

  closeModal() {
    const el = document.getElementById('modal-overlay');
    if (el) el.remove();
  },

  kpiCard({ icon, iconClass = 'amber', label, value, sub, trend, trendDir = 'up', colorClass = '' }) {
    return `
      <div class="kpi-card ${colorClass}">
        <div class="kpi-top">
          <div class="kpi-icon ${iconClass}"><i class="fas ${icon}"></i></div>
          ${trend !== undefined ? `
            <div class="kpi-trend ${trendDir}">
              <i class="fas fa-arrow-${trendDir}"></i>${trend}
            </div>
          ` : ''}
        </div>
        <div class="kpi-value">${value}</div>
        <div class="kpi-label">${label}</div>
        ${sub ? `<div class="kpi-sub">${sub}</div>` : ''}
      </div>
    `;
  },

  scoreBreakdown(scores) {
    const items = [
      { label: 'Qualité solaire',     key: 'solar_score',     color: 'amber'  },
      { label: 'Stabilité ressource', key: 'stability_score', color: 'teal'   },
      { label: 'Terrain',             key: 'terrain_score',   color: 'green'  },
      { label: 'Distance réseau',     key: 'grid_score',      color: 'blue'   },
      { label: 'Demande locale',      key: 'demand_score',    color: 'purple' },
    ];

    return `
      <div class="score-breakdown">
        ${items.map(item => `
          <div class="score-item">
            <div class="score-item-header">
              <span class="score-item-label">${item.label}</span>
              <span class="score-item-val">${scores[item.key] || 0}/100</span>
            </div>
            <div class="score-item-bar">
              <div class="score-item-fill ${item.color}" style="width:${scores[item.key] || 0}%"></div>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  },

  riskGrid(risks) {
    return `
      <div class="risk-grid">
        ${risks.map(r => `
          <div class="risk-item">
            <div class="risk-header">
              <span class="risk-label">${r.type}</span>
              ${Utils.riskBadge(r.level)}
            </div>
            <div class="risk-desc">${r.detail}</div>
          </div>
        `).join('')}
      </div>
    `;
  },

  loading(containerId, message = 'Chargement...') {
    const markup = `
      <div style="display:flex;align-items:center;justify-content:center;padding:48px;flex-direction:column;gap:12px">
        <div style="width:32px;height:32px;border:3px solid var(--bg-elevated);border-top-color:var(--amber-400);border-radius:50%;animation:spin 0.8s linear infinite"></div>
        <p style="color:var(--text-muted);font-size:13px">${message}</p>
      </div>
      <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
    `;
    const el = containerId ? document.getElementById(containerId) : null;
    if (el) el.innerHTML = markup;
    return markup;
  },

  pageHeader(icon, title, subtitle, actions = '') {
    return `
      <div class="page-header">
        <div class="page-header-row">
          <div>
            <h1><i class="fas ${icon}"></i> ${title}</h1>
            ${subtitle ? `<p>${subtitle}</p>` : ''}
          </div>
          ${actions ? `<div style="display:flex;gap:8px;flex-wrap:wrap">${actions}</div>` : ''}
        </div>
      </div>
    `;
  },

  provenanceLegend() {
    return `
      <div class="provenance-legend">
        <span style="font-size:11px;color:var(--text-muted);margin-right:4px">Sources:</span>
        <span class="badge badge-measured">✅ Mesuré</span>
        <span class="badge badge-estimated">⚠️ Estimé</span>
        <span class="badge badge-synthetic">🧪 Synthétique</span>
        <span class="badge badge-predicted">🤖 Prédit</span>
      </div>
    `;
  },

  wilayaSelect(id, value = '') {
    const rawWilayas = (window.ALL_WILAYAS && window.ALL_WILAYAS.length)
      ? window.ALL_WILAYAS
      : MOCK_DATA.wilayas;

    const wilayas = [...rawWilayas]
      .map(w => ({
        code: String(w.code ?? w.wilaya_code ?? '').padStart(2, '0'),
        name: w.name || w.wilaya_name || `Wilaya ${String(w.code ?? w.wilaya_code ?? '').padStart(2,'0')}`
      }))
      .sort((a, b) => Number(a.code) - Number(b.code));

    const options = wilayas.map(w =>
      `<option value="${w.code}" ${w.code === value ? 'selected' : ''}>${w.name} (${w.code})</option>`
    ).join('');
    return `<select id="${id}" class="form-select">${options}</select>`;
  },

  explainPanel(zone) {
    return `
      <div class="card">
        <div class="card-header">
          <div class="card-title"><i class="fas fa-brain"></i> Pourquoi cette zone ?</div>
          <span class="badge badge-thesis">IA Explicable</span>
        </div>
        <div class="card-body">
          <div style="margin-bottom:14px">
            ${(zone.rationale || []).map((r, i) => `
              <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
                <div style="width:22px;height:22px;border-radius:50%;background:rgba(245,158,11,0.15);color:var(--amber-400);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">${i+1}</div>
                <div style="font-size:13px;color:var(--text-primary)">${r}</div>
              </div>
            `).join('')}
          </div>
          <div class="info-panel">
            <div class="info-panel-title"><i class="fas fa-exclamation-circle"></i> Note sur les données</div>
            <div class="info-panel-text">Score calculé sur la base de ${Utils.dataBadge(zone.data_source)}. Les projections de production sont des estimations basées sur des modèles physiques.</div>
          </div>
        </div>
      </div>
    `;
  },

  emptyState(icon, title, desc, action = '') {
    return `
      <div class="empty-state">
        <i class="fas ${icon}"></i>
        <h3>${title}</h3>
        <p>${desc}</p>
        ${action}
      </div>
    `;
  },

  statPair(label, value, unit = '', color = '') {
    return `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
        <span style="font-size:12px;color:var(--text-secondary)">${label}</span>
        <span style="font-size:14px;font-weight:700;color:${color || 'var(--text-primary)'}">${value} <span style="font-size:11px;font-weight:400;color:var(--text-muted)">${unit}</span></span>
      </div>
    `;
  },
};

window.Components = Components;