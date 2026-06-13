const LandingPage = {
  _stats: {
    twh_potentiel_total: null,
    n_wilayas:           58,
    n_communes:          291,
    annees_de_donnees:   5,
  },
  _wilayas:       [],
  _climateZones:  [],
  _wow:           null,
  _analysesTotal: null,

  async render() {
    const T       = (k) => I18N.t(k);
    const content = document.getElementById('page-content');

    content.innerHTML = `
      <section class="hero">
        <div class="hero-bg"></div>
        <div class="hero-particles" id="hero-particles"></div>

        <h1>
          <span data-i18n="landing.hero_title_1">${T('landing.hero_title_1')}</span>
          <span class="gradient" data-i18n="landing.hero_title_accent">${T('landing.hero_title_accent')}</span><br/>
          <span data-i18n="landing.hero_title_2">${T('landing.hero_title_2')}</span>
        </h1>

        <p class="hero-sub" data-i18n="landing.hero_sub">${T('landing.hero_sub')}</p>

        <div class="hero-actions">
          <button class="btn btn-primary btn-lg" onclick="App.navigate('ranking')">
            <i class="fas fa-trophy"></i>
            <span data-i18n="landing.cta_ranking">${T('landing.cta_ranking')}</span>
          </button>
          <button class="btn btn-secondary btn-lg" onclick="App.navigate('zone')">
            <i class="fas fa-crosshairs"></i>
            <span data-i18n="landing.cta_zone">${T('landing.cta_zone')}</span>
          </button>
        </div>

        <div class="hero-stats">
          <div class="hero-stat">
            <div class="stat-val" id="hero-stat-twh">${this._fmtTWh(this._stats.twh_potentiel_total)}</div>
            <div class="stat-label" data-i18n="landing.stat_twh">${T('landing.stat_twh')}</div>
          </div>
          <div class="hero-stat">
            <div class="stat-val" id="hero-stat-wilayas">${this._stats.n_wilayas}</div>
            <div class="stat-label" data-i18n="landing.stat_wilayas">${T('landing.stat_wilayas')}</div>
          </div>
          <div class="hero-stat">
            <div class="stat-val" id="hero-stat-communes">${this._stats.n_communes}</div>
            <div class="stat-label" data-i18n="landing.stat_communes">${T('landing.stat_communes')}</div>
          </div>
          <div class="hero-stat">
            <div class="stat-val" id="hero-stat-years">${this._stats.annees_de_donnees}</div>
            <div class="stat-label" data-i18n="landing.stat_years">${T('landing.stat_years')}</div>
          </div>
        </div>

        <div class="hero-scroll-hint">
          <span data-i18n="landing.scroll_hint">${T('landing.scroll_hint')}</span>
          <i class="fas fa-chevron-down"></i>
        </div>
      </section>

      <section class="landing-section">
        <div style="text-align:center;margin-bottom:48px">
          <div class="hero-tag" style="margin-bottom:16px" data-i18n="landing.value_prop">${T('landing.value_prop')}</div>
          <h2>
            <span data-i18n="landing.value_h2_1">${T('landing.value_h2_1')}</span>
            <span class="grad-text" data-i18n="landing.value_h2_accent">${T('landing.value_h2_accent')}</span>
            <span data-i18n="landing.value_h2_2">${T('landing.value_h2_2')}</span>
          </h2>
          <p style="color:var(--text-secondary);font-size:16px;margin-top:12px;max-width:600px;margin-left:auto;margin-right:auto"
             data-i18n="landing.value_sub">${T('landing.value_sub')}</p>
        </div>
        <div class="feature-grid">
          ${[
            { icon: 'fa-map-pin',     color: 'amber',  qKey: 'landing.q_where',      aKey: 'landing.a_where'      },
            { icon: 'fa-brain',       color: 'teal',   qKey: 'landing.q_why',        aKey: 'landing.a_why'        },
            { icon: 'fa-sun',         color: 'green',  qKey: 'landing.q_production', aKey: 'landing.a_production' },
            { icon: 'fa-dollar-sign', color: 'purple', qKey: 'landing.q_roi',        aKey: 'landing.a_roi'        },
          ].map(f => `
            <div class="feature-card">
              <div class="feat-icon kpi-icon ${f.color}"><i class="fas ${f.icon}"></i></div>
              <h3 data-i18n="${f.qKey}">${T(f.qKey)}</h3>
              <p data-i18n="${f.aKey}">${T(f.aKey)}</p>
            </div>
          `).join('')}
        </div>
      </section>

      <section class="landing-section" style="padding-top:0">
        <div class="card" style="padding:32px;text-align:center;border-color:rgba(20,184,166,0.25);background:linear-gradient(135deg,rgba(20,184,166,0.06),rgba(245,158,11,0.04))">
          <div class="feat-icon kpi-icon teal" style="margin:0 auto 16px"><i class="fas fa-brain"></i></div>
          <h3 style="margin-bottom:10px" data-i18n="landing.ai_block_title">${T('landing.ai_block_title')}</h3>
          <p style="max-width:680px;margin:0 auto;color:var(--text-secondary);font-size:15px;line-height:1.6"
             data-i18n="landing.ai_block_text">${T('landing.ai_block_text')}</p>
        </div>
      </section>

      <section class="landing-section" style="padding-top:0">
        <div class="hero-row" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px">
          <div class="card" id="wow-card" style="padding:24px;display:flex;gap:18px;align-items:flex-start">
            <div class="feat-icon kpi-icon amber" style="flex-shrink:0;width:48px;height:48px"><i class="fas fa-sun"></i></div>
            <div style="flex:1;min-width:0">
              <div style="font-size:11px;letter-spacing:.06em;color:var(--text-muted);text-transform:uppercase;font-weight:600" data-i18n="landing.wow_title">${T('landing.wow_title')}</div>
              <h3 id="wow-name" style="margin:4px 0;font-size:22px;line-height:1.2">…</h3>
              <p style="font-size:12px;color:var(--text-secondary);margin:0 0 14px" data-i18n="landing.wow_sub">${T('landing.wow_sub')}</p>
              <div id="wow-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px"></div>
              <button id="wow-btn" class="btn btn-primary btn-sm" onclick="LandingPage._openWow()">
                <i class="fas fa-arrow-right" style="margin-right:6px"></i>
                <span data-i18n="landing.wow_open_dashboard">${T('landing.wow_open_dashboard')}</span>
              </button>
            </div>
          </div>

          <div class="card" id="counter-card" style="padding:24px;display:flex;gap:18px;align-items:center">
            <div class="feat-icon kpi-icon teal" style="flex-shrink:0;width:48px;height:48px"><i class="fas fa-chart-line"></i></div>
            <div style="flex:1">
              <div style="font-size:11px;letter-spacing:.06em;color:var(--text-muted);text-transform:uppercase;font-weight:600" data-i18n="landing.counter_title">${T('landing.counter_title')}</div>
              <div style="font-size:42px;font-weight:800;line-height:1;margin:8px 0;background:linear-gradient(135deg,var(--amber-400),var(--teal-400));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent" id="counter-value">0</div>
              <div style="font-size:12px;color:var(--text-muted)" data-i18n="landing.counter_sub">${T('landing.counter_sub')}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="landing-section" style="padding-top:0">
        <div class="card">
          <div class="card-header">
            <div class="card-title">
              <i class="fas fa-cloud-sun"></i>
              <span data-i18n="landing.climate_card_title">${T('landing.climate_card_title')}</span>
            </div>
            <div style="font-size:12px;color:var(--text-muted)" data-i18n="landing.climate_card_sub">${T('landing.climate_card_sub')}</div>
          </div>
          <div id="climate-grid"
               style="padding:18px;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px"></div>
        </div>
      </section>

      <section class="landing-section" style="padding-top:0">
        <div style="text-align:center;margin-bottom:40px">
          <h2>
            <span data-i18n="landing.users_h2_1">${T('landing.users_h2_1')}</span>
            <span class="grad-text" data-i18n="landing.users_h2_accent">${T('landing.users_h2_accent')}</span>
          </h2>
        </div>
        <div class="user-cards">
          ${[
            { icon: '💼', roleKey: 'landing.user_investors',  descKey: 'landing.user_investors_desc'  },
            { icon: '🏛️', roleKey: 'landing.user_government', descKey: 'landing.user_government_desc' },
            { icon: '⚡', roleKey: 'landing.user_sonelgaz',   descKey: 'landing.user_sonelgaz_desc'   },
            { icon: '🏗️', roleKey: 'landing.user_epc',        descKey: 'landing.user_epc_desc'        },
            { icon: '📡', roleKey: 'landing.user_field',      descKey: 'landing.user_field_desc'      },
          ].map(u => `
            <div class="user-card" onclick="LandingPage.showUserFlow('${T(u.roleKey)}')">
              <div class="user-icon">${u.icon}</div>
              <h3 data-i18n="${u.roleKey}">${T(u.roleKey)}</h3>
              <p data-i18n="${u.descKey}">${T(u.descKey)}</p>
            </div>
          `).join('')}
        </div>
      </section>

      <section class="landing-section" style="padding-top:0">
        <div class="card">
          <div class="card-header">
            <div class="card-title">
              <i class="fas fa-globe-africa"></i>
              <span data-i18n="landing.map_title">${T('landing.map_title')}</span>
            </div>
            <div class="flex gap-2">
              <button class="btn btn-secondary btn-sm" onclick="App.navigate('ranking')">
                <i class="fas fa-expand-arrows-alt"></i>
                <span data-i18n="landing.map_full_view">${T('landing.map_full_view')}</span>
              </button>
            </div>
          </div>
          <div id="landing-map" style="height:420px"></div>
          <div class="card-footer">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
              <div style="display:flex;gap:16px;font-size:12px;color:var(--text-secondary);flex-wrap:wrap">
                <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--green-400);margin-right:4px"></span><span data-i18n="landing.map_legend_excellent">${T('landing.map_legend_excellent')}</span></span>
                <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--amber-400);margin-right:4px"></span><span data-i18n="landing.map_legend_high">${T('landing.map_legend_high')}</span></span>
                <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--blue-400);margin-right:4px"></span><span data-i18n="landing.map_legend_good">${T('landing.map_legend_good')}</span></span>
                <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--gray-500);margin-right:4px"></span><span data-i18n="landing.map_legend_moderate">${T('landing.map_legend_moderate')}</span></span>
              </div>
              <span class="badge badge-measured">✅ <span data-i18n="landing.map_source">${T('landing.map_source')}</span> 2019-2023</span>
            </div>
          </div>
        </div>
      </section>

      <footer style="padding:24px 40px;border-top:1px solid var(--border-color);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
        <div style="display:flex;align-items:center;gap:8px">
          <div class="logo-icon" style="width:28px;height:28px;border-radius:6px;background:linear-gradient(135deg,var(--amber-500),var(--amber-600));display:flex;align-items:center;justify-content:center">
            <i class="fas fa-sun" style="color:white;font-size:13px"></i>
          </div>
          <span style="font-size:13px;font-weight:600">SolarDecide DZ</span>
          <span class="badge badge-experimental">Beta</span>
        </div>
        <div style="font-size:12px;color:var(--text-muted)" data-i18n="landing.footer">${T('landing.footer')}</div>
      </footer>
    `;

    // Delay map init to ensure the DOM element is fully painted
    setTimeout(() => this.initLandingMap(), 100);
    this.initParticles();
    this._refreshAll();
  },

  // ─── Formatting helpers ───────────────────────────────────────────────

  _fmtTWh(v) {
    if (v == null || !Number.isFinite(Number(v))) return '—';
    const n = Number(v);
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 1_000)     return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'k';
    if (n >= 10)        return Math.round(n).toString();
    if (n >= 1)         return n.toFixed(1);
    return n.toFixed(2);
  },

  // Returns a color hex based on composite score thresholds
  _scoreColor(s) {
    if (s >= 90) return '#22c55e';
    if (s >= 75) return '#f59e0b';
    if (s >= 60) return '#3b82f6';
    return '#9ca3af';
  },

  // Maps climate type to its brand color for tiles and map markers
  _climateColor(c) {
    return {
      Saharan:    '#f97316',
      Arid:       '#f59e0b',
      'Semi-Arid':'#fbbf24',
      Highland:   '#3b82f6',
      Coastal:    '#06b6d4',
    }[c] || '#9ca3af';
  },

  // Resolves a climate code to its i18n display label
  _climateLabel(c) {
    const key = ({
      Coastal:    'landing.climate_coastal',
      Saharan:    'landing.climate_saharan',
      Arid:       'landing.climate_arid',
      'Semi-Arid':'landing.climate_semi_arid',
      Highland:   'landing.climate_highland',
    })[c];
    return key ? I18N.t(key) : c;
  },

  // ─── Data orchestration ───────────────────────────────────────────────

  async _refreshAll() {
    if (typeof DataService === 'undefined') return;

    // Fetch all data sources in parallel to minimise load time
    const [stats, zones, wow, counter, wilayas] = await Promise.all([
      DataService.getNationalStats().catch(() => null),
      DataService.getClimateZones().catch(() => []),
      DataService.getWilayaOfTheWeek().catch(() => null),
      DataService.getAnalysesCount().catch(() => ({ total_analyses: 0 })),
      DataService.getTopWilayas('score_composite', 58).catch(() => []),
    ]);

    if (stats)              this._applyStats(stats);
    if (Array.isArray(zones)) this._applyClimateZones(zones);
    if (wow)                this._applyWow(wow);
    if (counter)            this._animateCounter(counter.total_analyses || 0);

    this._wilayas = wilayas;
    if (wilayas?.length)    this._renderMapMarkers();
  },

  // Patches hero KPI elements with live values from the API
  _applyStats(s) {
    this._stats = { ...this._stats, ...s };
    const map = {
      'hero-stat-twh':      this._fmtTWh(s.twh_potentiel_total),
      'hero-stat-wilayas':  String(s.n_wilayas    ?? this._stats.n_wilayas),
      'hero-stat-communes': String(s.n_communes   ?? this._stats.n_communes),
      'hero-stat-years':    String(s.annees_de_donnees ?? this._stats.annees_de_donnees),
    };
    Object.entries(map).forEach(([id, val]) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    });
  },

  _applyClimateZones(zones) {
    this._climateZones = zones;
    const grid = document.getElementById('climate-grid');
    if (!grid) return;

    if (!zones.length) {
      grid.innerHTML = `<div style="color:var(--text-muted);padding:14px">—</div>`;
      return;
    }

    grid.innerHTML = zones.map(z => {
      const color      = this._climateColor(z.climate);
      const label      = this._climateLabel(z.climate);
      const target     = z.representative_wilaya || '';
      // Escape single quotes so the value is safe inside an onclick attribute
      const safeTarget = String(target).replace(/'/g, "\\'");
      const ghi        = (z.ghi_annuel_kwh_m2 != null) ? Number(z.ghi_annuel_kwh_m2).toFixed(2) : '—';

      return `
        <button class="climate-tile" type="button"
                onclick="LandingPage._openClimateZone('${safeTarget}')"
                style="text-align:left;border:1px solid ${color}55;border-radius:12px;padding:14px;
                       background:linear-gradient(135deg, ${color}18, transparent);
                       cursor:${target ? 'pointer' : 'default'};transition:transform .15s ease, border-color .15s ease;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span style="width:10px;height:10px;border-radius:50%;background:${color};display:inline-block"></span>
            <span style="font-size:13px;font-weight:700;color:${color}">${label}</span>
          </div>
          <div style="font-size:24px;font-weight:800;line-height:1.05;color:var(--text-primary)">${ghi}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px">kWh/m² · ${z.n_wilayas} wilayas · ${z.n_communes} communes</div>
          ${target ? `<div style="font-size:11px;color:var(--text-secondary);margin-top:8px">→ ${target}</div>` : ''}
        </button>
      `;
    }).join('');
  },

  _applyWow(wow) {
    this._wow = wow;
    const name = document.getElementById('wow-name');
    if (name) name.textContent = wow.wilaya_name || '—';

    const grid = document.getElementById('wow-grid');
    if (!grid) return;

    // Reusable mini-cell renderer for the KPI grid
    const cell = (label, val) => `
      <div style="background:rgba(255,255,255,0.04);border:1px solid var(--border-color);border-radius:8px;padding:8px 10px">
        <div style="font-size:10px;text-transform:uppercase;color:var(--text-muted);letter-spacing:.04em">${label}</div>
        <div style="font-size:15px;font-weight:700;margin-top:2px">${val}</div>
      </div>`;

    const ghiHourly = (wow.ghi_week_kwh_m2_h != null)
      ? Number(wow.ghi_week_kwh_m2_h).toFixed(3)
      : '—';

    grid.innerHTML = [
      cell(I18N.t('landing.wow_ghi_week'), ghiHourly),
      cell(I18N.t('landing.wow_score'),    (wow.score_composite ?? '—').toString()),
      cell(I18N.t('landing.wow_rank'),     wow.rang_national ? `#${wow.rang_national}` : '—'),
    ].join('');
  },

  _openWow() {
    if (!this._wow) return;
    App.navigate('wilaya', {
      code: this._wow.wilaya_code != null ? String(this._wow.wilaya_code).padStart(2, '0') : '',
      name: this._wow.wilaya_name || '',
    });
  },

  _openClimateZone(wilayaName) {
    if (!wilayaName) return;
    App.navigate('wilaya', { name: wilayaName });
  },

  // Counts up from 0 to target using a cubic ease-out curve
  _animateCounter(target) {
    this._analysesTotal = Number(target) || 0;
    const el = document.getElementById('counter-value');
    if (!el) return;

    const dur     = 1200;
    const t0      = performance.now();
    const easeOut = (t) => 1 - Math.pow(1 - t, 3);

    const tick = (now) => {
      const t = Math.min(1, (now - t0) / dur);
      const v = Math.round((target) * easeOut(t));
      el.textContent = v.toLocaleString('fr-DZ');
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  },

  // ─── Map ──────────────────────────────────────────────────────────────

  async initLandingMap() {
    const mapEl = document.getElementById('landing-map');
    if (!mapEl || typeof L === 'undefined') return;

    // Destroy any existing Leaflet instance before re-initialising
    if (this._mapInstance) {
      try { this._mapInstance.remove(); } catch (_) {}
      this._mapInstance = null;
    }

    this._mapInstance = L.map('landing-map', {
      center: [28.0, 2.5],
      zoom: 5,
      zoomControl: true,
      scrollWheelZoom: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap',
      maxZoom: 18,
    }).addTo(this._mapInstance);

    if (this._wilayas?.length) this._renderMapMarkers();
  },

  _renderMapMarkers() {
    const map = this._mapInstance;
    if (!map) return;

    // Remove stale markers before adding the updated set
    if (this._markers) this._markers.forEach(m => map.removeLayer(m));
    this._markers = [];

    this._wilayas.forEach(w => {
      const color  = this._scoreColor(Number(w.score_composite || 0));
      const marker = L.circleMarker([w.latitude, w.longitude], {
        radius:      7,
        fillColor:   color,
        color:       color,
        weight:      1.5,
        opacity:     0.9,
        fillOpacity: 0.65,
      }).addTo(map);

      // Escape wilaya name so it is safe inside the onclick attribute string
      const safeName = String(w.wilaya_name || '').replace(/'/g, "\\'");
      const ghi      = (w.ghi_annuel_kwh_m2 != null) ? Number(w.ghi_annuel_kwh_m2).toFixed(2) : '—';

      marker.bindPopup(`
        <div style="min-width:200px">
          <div style="font-weight:700;font-size:13px;margin-bottom:6px">${w.wilaya_name}</div>
          <div style="display:flex;justify-content:space-between;margin-bottom:4px">
            <span style="font-size:11px;color:#9ca3af">${I18N.t('ranking.sort_score')}</span>
            <span style="font-size:12px;font-weight:700;color:${color}">${w.score_composite}/100</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:4px">
            <span style="font-size:11px;color:#9ca3af">GHI</span>
            <span style="font-size:12px;font-weight:600">${ghi} kWh/m²/an</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <span style="font-size:11px;color:#9ca3af">${I18N.t('ranking.potential_mw')}</span>
            <span style="font-size:12px;font-weight:600">${(w.potentiel_mw ?? '—')} MW</span>
          </div>
          <button onclick="App.navigate('wilaya',{code:'${String(w.wilaya_code || '').padStart(2,'0')}',name:'${safeName}'})"
            style="width:100%;background:var(--amber-500);color:white;border:none;border-radius:6px;padding:6px;font-size:12px;font-weight:600;cursor:pointer">
            ${I18N.t('landing.wow_open_dashboard')} →
          </button>
        </div>
      `);

      marker.on('mouseover', function() { this.openPopup(); });
      this._markers.push(marker);
    });
  },

  initParticles() {
    const container = document.getElementById('hero-particles');
    if (!container) return;
    container.innerHTML = '';

    for (let i = 0; i < 20; i++) {
      const dot  = document.createElement('div');
      const size = Math.random() * 3 + 1;
      dot.style.cssText = `
        position:absolute;width:${size}px;height:${size}px;
        background:rgba(245,158,11,${Math.random() * 0.4 + 0.1});
        border-radius:50%;left:${Math.random() * 100}%;top:${Math.random() * 100}%;
        animation:float ${Math.random() * 6 + 4}s ease-in-out infinite;
        animation-delay:${Math.random() * 4}s;
      `;
      container.appendChild(dot);
    }

    // Inject keyframes once — guard against duplicate style tags on re-render
    if (!document.getElementById('landing-particle-style')) {
      const style     = document.createElement('style');
      style.id        = 'landing-particle-style';
      style.textContent = `
        @keyframes float {
          0%,100%{transform:translateY(0) translateX(0);opacity:0.4}
          50%{transform:translateY(-30px) translateX(10px);opacity:1}
        }
      `;
      document.head.appendChild(style);
    }
  },

  showUserFlow(role) {
    Utils.toast('info', role, '');
  },
};

window.LandingPage = LandingPage;