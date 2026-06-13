const RankingPage = {
  data:             [],
  regions:          [],
  climates:         [],
  selectedWilaya:   null,
  filters:          { region: '', climate: '', search: '', sort: 'score' },
  top10Criterion:   'score',
  _map:             null,
  _markers:         [],

  // ─── Helpers ─────────────────────────────────────────────────────────

  _scoreColor(s) {
    if (s >= 75) return '#22c55e';
    if (s >= 55) return '#f59e0b';
    if (s >= 35) return '#3b82f6';
    return '#9ca3af';
  },

  // Creates a temporary DOM node to leverage the browser's built-in HTML escaping
  _esc(v) {
    const el = document.createElement('div');
    el.textContent = v == null ? '' : String(v);
    return el.innerHTML;
  },

  _fmtNumber(v, digits = 2) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return n.toFixed(digits);
  },

  // Returns a pill badge showing GHI delta vs the national mean, coloured by direction
  _deltaBadge(delta) {
    if (delta == null || !Number.isFinite(Number(delta))) return '';
    const d     = Number(delta);
    const sign  = d > 0 ? '+' : '';
    const color = d > 0.5 ? '#22c55e' : (d < -0.5 ? '#ef4444' : '#94a3b8');
    const bg    = d > 0.5 ? 'rgba(34,197,94,0.12)' : (d < -0.5 ? 'rgba(239,68,68,0.12)' : 'rgba(148,163,184,0.12)');
    return `<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;
                          font-size:11px;font-weight:700;background:${bg};color:${color}">
              ${sign}${d.toFixed(1)}%
            </span>`;
  },

  getState() {
    return {
      filters:            { ...this.filters },
      top10Criterion:     this.top10Criterion,
      selectedWilayaName: this.selectedWilaya?.wilaya_name || '',
    };
  },

  // ─── Rendering ───────────────────────────────────────────────────────

  async render(params = {}, restoreState = {}) {
    if (restoreState.filters)        this.filters        = { ...this.filters, ...restoreState.filters };
    if (restoreState.top10Criterion) this.top10Criterion = restoreState.top10Criterion;

    const T       = (k) => I18N.t(k);
    const content = document.getElementById('page-content');

    content.innerHTML = `
      <div class="page-wrapper">
        ${Components.pageHeader(
          'fa-trophy',
          T('ranking.title'),
          T('ranking.subtitle'),
          `<button class="btn btn-secondary btn-sm" onclick="RankingPage.exportCSV()">
             <i class="fas fa-download"></i> <span data-i18n="ranking.export_csv">${T('ranking.export_csv')}</span>
           </button>
           <button class="btn btn-primary btn-sm" onclick="App.navigate('comparison')">
             <i class="fas fa-columns"></i> <span data-i18n="ranking.compare">${T('ranking.compare')}</span>
           </button>`
        )}

        <div id="ranking-loading" class="card" style="padding:40px;text-align:center">
          <i class="fas fa-spinner fa-spin" style="font-size:24px;color:var(--text-muted)"></i>
          <p style="margin-top:12px;color:var(--text-secondary)" data-i18n="ranking.loading">${T('ranking.loading')}</p>
        </div>

        <div id="ranking-body" style="display:none">
          <div class="card" style="padding:14px 16px;margin-bottom:16px">
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;align-items:end">
              <div>
                <label style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em" data-i18n="ranking.filter_search">${T('ranking.filter_search')}</label>
                <input id="rk-search" type="text" class="input" placeholder="${T('ranking.filter_search')}" data-i18n-placeholder="ranking.filter_search"
                       oninput="RankingPage.onFilterChange()" style="width:100%;margin-top:6px"/>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em" data-i18n="ranking.filter_region">${T('ranking.filter_region')}</label>
                <select id="rk-region" class="select" onchange="RankingPage.onFilterChange()" style="width:100%;margin-top:6px">
                  <option value="" data-i18n="ranking.filter_all">${T('ranking.filter_all')}</option>
                </select>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em" data-i18n="ranking.filter_climate">${T('ranking.filter_climate')}</label>
                <select id="rk-climate" class="select" onchange="RankingPage.onFilterChange()" style="width:100%;margin-top:6px">
                  <option value="" data-i18n="ranking.filter_all">${T('ranking.filter_all')}</option>
                </select>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em" data-i18n="ranking.sort_by">${T('ranking.sort_by')}</label>
                <select id="rk-sort" class="select" onchange="RankingPage.onFilterChange()" style="width:100%;margin-top:6px">
                  <option value="score"     data-i18n="ranking.sort_score">${T('ranking.sort_score')}</option>
                  <option value="ghi"       data-i18n="ranking.sort_ghi">${T('ranking.sort_ghi')}</option>
                  <option value="potentiel" data-i18n="ranking.sort_potential">${T('ranking.sort_potential')}</option>
                </select>
              </div>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:16px">
            <div class="card" style="overflow:hidden">
              <div class="card-header">
                <div class="card-title"><i class="fas fa-list-ol"></i> <span data-i18n="ranking.table_title">${T('ranking.table_title')}</span></div>
                <span id="rk-count" class="badge badge-amber"></span>
              </div>
              <div id="rk-table-wrap" style="max-height:560px;overflow:auto"></div>
            </div>

            <div style="display:flex;flex-direction:column;gap:16px">
              <div class="card" id="rk-selected-card" style="padding:16px">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                  <i class="fas fa-map-marker-alt" style="color:var(--amber-400)"></i>
                  <span style="font-size:11px;letter-spacing:.06em;color:var(--text-muted);text-transform:uppercase;font-weight:600" data-i18n="ranking.selected_card">${T('ranking.selected_card')}</span>
                </div>
                <div id="rk-selected-content" style="font-size:13px;color:var(--text-secondary)" data-i18n="ranking.select_a_wilaya">${T('ranking.select_a_wilaya')}</div>
              </div>

              <div class="card">
                <div class="card-header">
                  <div class="card-title"><i class="fas fa-medal"></i> <span data-i18n="ranking.top10_card_title">${T('ranking.top10_card_title')}</span></div>
                  <select id="rk-top10-metric" class="select select-sm" onchange="RankingPage.onTop10Change()">
                    <option value="score"     data-i18n="ranking.top10_by_score">${T('ranking.top10_by_score')}</option>
                    <option value="ghi"       data-i18n="ranking.top10_by_ghi">${T('ranking.top10_by_ghi')}</option>
                    <option value="potentiel" data-i18n="ranking.top10_by_potential">${T('ranking.top10_by_potential')}</option>
                  </select>
                </div>
                <div id="rk-top10" style="padding:8px 12px"></div>
              </div>

              <div class="card">
                <div class="card-header">
                  <div class="card-title"><i class="fas fa-globe-africa"></i> <span data-i18n="ranking.regions_card_title">${T('ranking.regions_card_title')}</span></div>
                </div>
                <div id="rk-regions" style="padding:8px 12px"></div>
              </div>
            </div>
          </div>

          <div class="card" style="margin-top:16px">
            <div class="card-header">
              <div class="card-title"><i class="fas fa-globe-africa"></i> <span data-i18n="ranking.map_title">${T('ranking.map_title')}</span></div>
              <button class="btn btn-secondary btn-sm" onclick="App.navigate('comparison')">
                <i class="fas fa-columns"></i> <span data-i18n="ranking.compare">${T('ranking.compare')}</span>
              </button>
            </div>
            <div id="rk-map" style="height:420px;background:rgba(255,255,255,0.02)"></div>
            <div id="rk-map-error" style="display:none;padding:24px;text-align:center;color:var(--text-secondary)">
              <i class="fas fa-exclamation-triangle" style="color:var(--amber-400);font-size:20px"></i>
              <div style="margin:8px 0" data-i18n="ranking.map_load_error">${T('ranking.map_load_error')}</div>
              <button class="btn btn-secondary btn-sm" onclick="RankingPage._initMap()" data-i18n="ranking.map_retry">${T('ranking.map_retry')}</button>
            </div>
          </div>
        </div>
      </div>
    `;

    try {
      await this._loadData();

      // Restore filter inputs to their previous values after the DOM is ready
      const sEl   = document.getElementById('rk-search');
      if (sEl   && this.filters.search)  sEl.value   = this.filters.search;
      const rEl   = document.getElementById('rk-region');
      if (rEl   && this.filters.region)  rEl.value   = this.filters.region;
      const cEl   = document.getElementById('rk-climate');
      if (cEl   && this.filters.climate) cEl.value   = this.filters.climate;
      const sortEl = document.getElementById('rk-sort');
      if (sortEl) sortEl.value = this.filters.sort;
      const t10El  = document.getElementById('rk-top10-metric');
      if (t10El)  t10El.value = this.top10Criterion;

      this._renderAll();

      // Re-select the previously highlighted wilaya if navigating back
      if (restoreState.selectedWilayaName) {
        const w = this.data.find(x => x.wilaya_name === restoreState.selectedWilayaName);
        if (w) this.selectWilaya(w.wilaya_name);
      }

      document.getElementById('ranking-loading').style.display = 'none';
      document.getElementById('ranking-body').style.display    = '';

      // Defer map init so the container has a measured height before Leaflet runs
      setTimeout(() => this._initMap(), 80);
    } catch (err) {
      console.error('RankingPage load error:', err);
      const lo = document.getElementById('ranking-loading');
      if (lo) lo.innerHTML = `
        <i class="fas fa-exclamation-triangle" style="color:var(--amber-400);font-size:20px"></i>
        <p style="margin-top:8px" data-i18n="ranking.error">${T('ranking.error')}</p>
        <button class="btn btn-secondary btn-sm" onclick="App.navigate('ranking')" data-i18n="common.retry">${T('common.retry')}</button>
      `;
    }
  },

  // ─── Data loading ─────────────────────────────────────────────────────

  async _loadData() {
    // Request all three sources in parallel; Leaflet map markers depend on ranking data
    const [ranking, regions, climates] = await Promise.all([
      DataService.getRanking({ metric: this.filters.sort || 'score', limit: 58 }),
      DataService.getRegionsList(),
      DataService.getClimateZones(),
    ]);

    this.data     = Array.isArray(ranking)  ? ranking  : [];
    this.regions  = Array.isArray(regions)  ? regions  : [];
    this.climates = Array.isArray(climates) ? climates : [];

    // Append fetched options rather than replacing so the default "All" option is preserved
    const rEl = document.getElementById('rk-region');
    if (rEl) {
      const opts = this.regions.map(r => `<option value="${this._esc(r)}">${this._esc(r)}</option>`).join('');
      rEl.insertAdjacentHTML('beforeend', opts);
    }
    const cEl = document.getElementById('rk-climate');
    if (cEl) {
      const opts = this.climates.map(c => `<option value="${this._esc(c.climate)}">${this._esc(c.climate)} — ${this._fmtNumber(c.ghi_annuel_kwh_m2, 2)} kWh/m²</option>`).join('');
      cEl.insertAdjacentHTML('beforeend', opts);
    }
  },

  async _refetchRanking() {
    this.data = await DataService.getRanking({
      metric:  this.filters.sort || 'score',
      limit:   58,
      region:  this.filters.region,
      climate: this.filters.climate,
      search:  this.filters.search,
    });
    this._renderAll();
    this._updateMapMarkers();
  },

  // ─── Render pieces ────────────────────────────────────────────────────

  _renderAll() {
    this._renderTable();
    this._renderTop10();
    this._renderRegions();
    this._renderSelected();
    this._updateCount();
  },

  _renderTable() {
    const wrap = document.getElementById('rk-table-wrap');
    if (!wrap) return;

    if (!this.data.length) {
      wrap.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-muted)" data-i18n="ranking.no_results">${I18N.t('ranking.no_results')}</div>`;
      return;
    }

    const T    = (k) => I18N.t(k);
    const rows = this.data.map((w) => {
      const score = Number(w.score_composite || 0);
      const sc    = this._scoreColor(score);
      const isSel = this.selectedWilaya?.wilaya_name === w.wilaya_name;
      const rowBg = isSel ? 'background:rgba(245,158,11,0.10)' : '';

      return `
        <tr onclick="RankingPage.selectWilaya('${this._esc(w.wilaya_name)}')"
            style="cursor:pointer;${rowBg}">
          <td style="padding:8px 10px;font-weight:700;color:var(--text-secondary);width:38px">#${w.rank}</td>
          <td style="padding:8px 10px">
            <div style="font-weight:700;font-size:13px">${this._esc(w.wilaya_name)}</div>
            <div style="font-size:11px;color:var(--text-muted)">${this._esc(w.region || '—')} · ${this._esc(w.climate_label || w.climate || '—')}</div>
          </td>
          <td style="padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums">
            <div style="font-weight:600">${this._fmtNumber(w.ghi_annuel_kwh_m2, 2)}</div>
            <div style="margin-top:4px">${this._deltaBadge(w.delta_vs_national)}</div>
          </td>
          <td style="padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums;font-weight:600">${this._fmtNumber(w.potentiel_mw, 0)}</td>
          <td style="padding:8px 10px;text-align:right">
            <span style="display:inline-block;min-width:54px;padding:3px 10px;border-radius:999px;
                         font-weight:700;font-size:12px;background:${sc}22;color:${sc};border:1px solid ${sc}55">
              ${this._fmtNumber(score, 1)}
            </span>
          </td>
          <td style="padding:8px 10px;text-align:right;width:36px">
            <button class="btn btn-ghost btn-xs"
                    onclick="event.stopPropagation();App.navigate('wilaya',{code:'${String(w.wilaya_code || '').padStart(2,'0')}',name:'${this._esc(w.wilaya_name)}'})"
                    title="${T('ranking.open_dashboard')}" data-i18n-title="ranking.open_dashboard">
              <i class="fas fa-arrow-right"></i>
            </button>
          </td>
        </tr>
      `;
    }).join('');

    wrap.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead style="position:sticky;top:0;background:var(--bg-card);z-index:5">
          <tr style="font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);border-bottom:1px solid var(--border-color)">
            <th style="padding:10px;text-align:left"  data-i18n="ranking.rank">${T('ranking.rank')}</th>
            <th style="padding:10px;text-align:left"  data-i18n="ranking.wilaya">${T('ranking.wilaya')}</th>
            <th style="padding:10px;text-align:right" data-i18n="ranking.ghi_annual">${T('ranking.ghi_annual')}</th>
            <th style="padding:10px;text-align:right" data-i18n="ranking.potential_mw">${T('ranking.potential_mw')}</th>
            <th style="padding:10px;text-align:right" data-i18n="ranking.score">${T('ranking.score')}</th>
            <th style="padding:10px"></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  _renderTop10() {
    const el = document.getElementById('rk-top10');
    if (!el) return;

    const metric   = this.top10Criterion;
    const valueOf  = (w) => {
      if (metric === 'ghi')       return Number(w.ghi_annuel_kwh_m2 || 0);
      if (metric === 'potentiel') return Number(w.potentiel_mw      || 0);
      return Number(w.score_composite || 0);
    };
    const unitOf  = () => metric === 'ghi' ? ' kWh/m²' : metric === 'potentiel' ? ' MW' : '';
    const digits  = () => metric === 'ghi' ? 2 : metric === 'potentiel' ? 0 : 1;

    const sorted = [...this.data].sort((a, b) => valueOf(b) - valueOf(a)).slice(0, 10);
    if (!sorted.length) { el.innerHTML = `<div style="padding:14px;color:var(--text-muted)">—</div>`; return; }

    el.innerHTML = sorted.map((w, i) => {
      const v   = valueOf(w);
      const max = valueOf(sorted[0]) || 1;
      // Bar width floored at 2% so even the lowest value shows a visible sliver
      const pct = Math.max(2, Math.round((v / max) * 100));
      const sc  = this._scoreColor(Number(w.score_composite || 0));

      return `
        <div style="display:flex;align-items:center;gap:8px;padding:6px 0;cursor:pointer"
             onclick="RankingPage.selectWilaya('${this._esc(w.wilaya_name)}')">
          <span style="width:18px;font-size:11px;color:var(--text-muted);font-weight:700">#${i + 1}</span>
          <div style="flex:1;min-width:0">
            <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${this._esc(w.wilaya_name)}</div>
            <div style="height:4px;background:rgba(255,255,255,0.05);border-radius:999px;margin-top:4px;overflow:hidden">
              <div style="height:100%;width:${pct}%;background:${sc};border-radius:999px"></div>
            </div>
          </div>
          <span style="font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;color:${sc};min-width:60px;text-align:right">
            ${this._fmtNumber(v, digits())}${unitOf()}
          </span>
        </div>
      `;
    }).join('');
  },

  async _renderRegions() {
    const el = document.getElementById('rk-regions');
    if (!el) return;

    const regions = await DataService.getRegionsBreakdown();
    if (!regions.length) { el.innerHTML = `<div style="padding:14px;color:var(--text-muted)">—</div>`; return; }

    const T = (k) => I18N.t(k);
    el.innerHTML = regions.map(r => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px dashed var(--border-color);cursor:pointer"
           onclick="RankingPage.filterByRegion('${this._esc(r.region)}')">
        <div>
          <div style="font-size:13px;font-weight:700">${this._esc(r.region)}</div>
          <div style="font-size:11px;color:var(--text-muted)">${r.n_wilayas} ${T('ranking.regions_n_wilayas')} · ${T('ranking.regions_ghi_mean')} ${this._fmtNumber(r.ghi_moyen_kwh_m2, 2)}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:13px;font-weight:700;color:var(--amber-400)">${this._fmtNumber(r.potentiel_mw_total, 0)} MW</div>
          <div style="font-size:11px;color:var(--text-muted)">${T('ranking.regions_potential')}</div>
        </div>
      </div>
    `).join('');
  },

  _renderSelected() {
    const el = document.getElementById('rk-selected-content');
    if (!el) return;

    const w = this.selectedWilaya;
    const T = (k) => I18N.t(k);

    if (!w) {
      el.innerHTML = `<div style="font-size:13px;color:var(--text-secondary)" data-i18n="ranking.select_a_wilaya">${T('ranking.select_a_wilaya')}</div>`;
      return;
    }

    const sc    = this._scoreColor(Number(w.score_composite || 0));
    const cells = [
      { key: 'ranking.ghi_annual',    val: `${this._fmtNumber(w.ghi_annuel_kwh_m2, 2)} kWh/m²` },
      { key: 'ranking.potential_mw',  val: `${this._fmtNumber(w.potentiel_mw, 0)} MW`           },
      { key: 'ranking.communes_count',val: String(w.n_communes ?? '—')                          },
      { key: 'ranking.climate_label', val: this._esc(w.climate_label || w.climate || '—')       },
    ];

    el.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <h3 style="margin:0;font-size:18px">${this._esc(w.wilaya_name)}</h3>
        <span style="padding:3px 10px;border-radius:999px;font-weight:700;font-size:11px;background:${sc}22;color:${sc};border:1px solid ${sc}55">
          #${w.rank} · ${this._fmtNumber(w.score_composite, 1)}
        </span>
      </div>
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px">${this._esc(w.region || '—')} · ${this._esc(w.climate || '—')}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
        ${cells.map(c => `
          <div style="padding:8px 10px;background:rgba(255,255,255,0.04);border:1px solid var(--border-color);border-radius:8px">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted)" data-i18n="${c.key}">${T(c.key)}</div>
            <div style="font-size:13px;font-weight:700;margin-top:2px">${c.val}</div>
          </div>
        `).join('')}
      </div>
      <div style="font-size:11px;color:var(--text-secondary);margin-bottom:10px">
        ${this._deltaBadge(w.delta_vs_national)}
        <span style="margin-left:6px">${Number(w.delta_vs_national || 0) >= 0 ? T('ranking.above_average') : T('ranking.below_average')}</span>
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-primary btn-sm" style="flex:1"
                onclick="App.navigate('wilaya',{code:'${String(w.wilaya_code || '').padStart(2,'0')}',name:'${this._esc(w.wilaya_name)}'})">
          <i class="fas fa-chart-bar"></i> <span data-i18n="ranking.open_dashboard">${T('ranking.open_dashboard')}</span>
        </button>
        <button class="btn btn-secondary btn-sm" style="flex:1"
                onclick="App.navigate('zone',{wilaya:'${this._esc(w.wilaya_name)}'})">
          <i class="fas fa-crosshairs"></i> <span data-i18n="ranking.see_zones">${T('ranking.see_zones')}</span>
        </button>
      </div>
    `;
  },

  _updateCount() {
    const el = document.getElementById('rk-count');
    if (el) el.textContent = `${this.data.length} / 58`;
  },

  // ─── Map ──────────────────────────────────────────────────────────────

  _initMap() {
    const el    = document.getElementById('rk-map');
    const errEl = document.getElementById('rk-map-error');
    if (!el) return;

    try {
      if (typeof L === 'undefined') throw new Error('Leaflet not loaded');

      // Destroy any existing instance before re-initialising
      if (this._map) { try { this._map.remove(); } catch (_) {} this._map = null; }

      this._map = L.map('rk-map', {
        center: [28.0, 2.5],
        zoom: 5,
        zoomControl: true,
        scrollWheelZoom: false,
      });

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap',
        maxZoom: 18,
      }).addTo(this._map);

      this._updateMapMarkers();
      el.style.display    = '';
      if (errEl) errEl.style.display = 'none';
    } catch (err) {
      console.warn('Ranking map init error:', err);
      el.style.display    = 'none';
      if (errEl) errEl.style.display = '';
    }
  },

  _updateMapMarkers() {
    if (!this._map) return;

    // Remove stale markers before placing the updated set
    if (this._markers) this._markers.forEach(m => { try { this._map.removeLayer(m); } catch (_) {} });
    this._markers = [];

    this.data.forEach(w => {
      if (!Number.isFinite(Number(w.latitude)) || !Number.isFinite(Number(w.longitude))) return;

      const sc     = this._scoreColor(Number(w.score_composite || 0));
      const marker = L.circleMarker([w.latitude, w.longitude], {
        radius: 7, fillColor: sc, color: sc, weight: 1.5, opacity: 0.9, fillOpacity: 0.65,
      }).addTo(this._map);

      const safeName = this._esc(w.wilaya_name);
      marker.bindPopup(`
        <div style="min-width:200px">
          <div style="font-weight:700;font-size:13px;margin-bottom:6px">${safeName}</div>
          <div style="display:flex;justify-content:space-between"><span style="font-size:11px;color:#9ca3af">${I18N.t('ranking.score')}</span><span style="font-weight:700;color:${sc}">${this._fmtNumber(w.score_composite, 1)}</span></div>
          <div style="display:flex;justify-content:space-between"><span style="font-size:11px;color:#9ca3af">GHI</span><span style="font-weight:600">${this._fmtNumber(w.ghi_annuel_kwh_m2, 2)} kWh/m²</span></div>
          <div style="display:flex;justify-content:space-between"><span style="font-size:11px;color:#9ca3af">${I18N.t('ranking.potential_mw')}</span><span style="font-weight:600">${this._fmtNumber(w.potentiel_mw, 0)} MW</span></div>
          <button onclick="App.navigate('wilaya',{code:'${String(w.wilaya_code || '').padStart(2, '0')}',name:'${safeName}'})"
                  style="width:100%;margin-top:8px;background:var(--amber-500);color:white;border:none;border-radius:6px;padding:6px;font-size:12px;font-weight:600;cursor:pointer">
            ${I18N.t('ranking.open_dashboard')} →
          </button>
        </div>
      `);

      marker.on('click', () => this.selectWilaya(w.wilaya_name));
      this._markers.push(marker);
    });
  },

  // ─── Event handlers ───────────────────────────────────────────────────

  onFilterChange() {
    this.filters.search  = (document.getElementById('rk-search')?.value  || '').trim();
    this.filters.region  =  document.getElementById('rk-region')?.value  || '';
    this.filters.climate =  document.getElementById('rk-climate')?.value || '';
    this.filters.sort    =  document.getElementById('rk-sort')?.value    || 'score';
    this._refetchRanking();
  },

  onTop10Change() {
    this.top10Criterion = document.getElementById('rk-top10-metric')?.value || 'score';
    this._renderTop10();
  },

  filterByRegion(region) {
    const sel = document.getElementById('rk-region');
    if (sel) {
      sel.value = region;
      this.onFilterChange();
    }
  },

  selectWilaya(name) {
    this.selectedWilaya = this.data.find(w => w.wilaya_name === name) || null;
    this._renderTable();
    this._renderSelected();
  },

  // ─── CSV export (plan-gated) ──────────────────────────────────────────

  exportCSV() {
    if (window.Plan && !Plan.canAccess('action.export_csv_ranking')) {
      PlanGate.open('pro', 'action.export_csv_ranking');
      return;
    }

    // Use fetch + blob so 402 (plan gate) and 429 responses can be intercepted before download
    const url     = DataService.csvExportUrl();
    const headers = {};
    const tok     = sessionStorage.getItem('auth_token');
    if (tok) headers['Authorization'] = `Bearer ${tok}`;

    fetch(url, { credentials: 'include', headers })
      .then(async (res) => {
        if (res.status === 402) {
          const body = await res.json().catch(() => ({}));
          PlanGate.intercept(body);
          return null;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        if (!blob) return;
        const dl   = document.createElement('a');
        dl.href     = URL.createObjectURL(blob);
        dl.download = 'solardecide-classement.csv';
        document.body.appendChild(dl);
        dl.click();
        dl.remove();
        // Revoke the object URL after a generous delay to ensure the download has started
        setTimeout(() => URL.revokeObjectURL(dl.href), 10_000);
        Utils.toast('success', 'CSV', 'classement.csv');
      })
      .catch((err) => {
        console.error('CSV export failed:', err);
        Utils.toast('error', I18N.t('common.error'), err.message || 'Network error');
      });
  },
};

window.RankingPage = RankingPage;