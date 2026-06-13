const ForecastPage = {
  // Full wilaya list loaded once from the API and reused across renders
  wilayas:         [],
  selectedWilaya:  '',

  // Forecast type: 'ghi' for solar irradiation, 'demand' for electricity demand in MW
  selectedType:    'ghi',
  selectedHorizon: '24h',

  // Last successful API payloads for GHI and demand forecasts respectively
  forecastResult:  null,
  demandResult:    null,

  // Active Chart.js instances; keyed by chart ID for targeted destruction
  charts:  {},

  // Tracks whether at least one forecast has been run in the current session
  hasRun:  false,

  // Horizon options for each forecast type; label and sub-label are shown in the UI buttons
  horizonOptionsGHI: [
    { id: '24h', label: '24 heures', sub: 'Prochaines 24 h',      icon: 'fa-clock'         },
    { id: '7j',  label: 'Semaine',   sub: '7 prochains jours',    icon: 'fa-calendar-week'  },
    { id: '30j', label: 'Mois',      sub: '30 prochains jours',   icon: 'fa-calendar-alt'   },
  ],

  horizonOptionsDemand: [
    { id: 'daily',   label: '24h',     sub: 'Prochains 30 jours',     icon: 'fa-clock'         },
    { id: 'weekly',  label: 'Semaine', sub: '16 prochaines semaines', icon: 'fa-calendar-week'  },
    { id: 'monthly', label: 'Mois',    sub: '12 prochains mois',      icon: 'fa-calendar-alt'   },
  ],

  // Returns the sensible default horizon when the forecast type changes
  _defaultHorizon(type) {
    return type === 'demand' ? 'monthly' : '24h';
  },

  // Returns the horizon options relevant to the currently selected forecast type
  get horizonOptions() {
    return this.selectedType === 'demand'
      ? this.horizonOptionsDemand
      : this.horizonOptionsGHI;
  },

  // Resolves the API base URL from the global config or falls back to localhost
  apiBase() {
    return (window.API && API.BASE_URL) ? API.BASE_URL : 'http://localhost:5000/api';
  },

  // Generic authenticated JSON fetch; extracts error messages from non-2xx responses
  async fetchJson(endpoint) {
    try {
      const res = await fetch(`${this.apiBase()}${endpoint}`, { credentials: 'include' });
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { msg = (await res.json()).error || msg; } catch (_) {}
        throw new Error(msg);
      }
      return await res.json();
    } catch (err) {
      console.error('ForecastPage fetch error', endpoint, err);
      throw err;
    }
  },

  // Bootstraps the page: resets state, loads the wilaya list, then renders the form shell
  async render(params = {}) {
    const content = document.getElementById('page-content');
    content.innerHTML = `
      <div class="page-wrapper">
        ${Components.loading('', 'Chargement des wilayas…')}
      </div>`;

    this.destroyCharts();
    this.hasRun        = false;
    this.forecastResult = null;
    this.demandResult   = null;

    try {
      await this._loadWilayas();

      // Apply URL params if provided, otherwise keep the current selection or default to the first wilaya
      const init = params.wilaya || this.selectedWilaya || this.wilayas[0]?.name || '';
      this.selectedWilaya = init;

      if (params.type && ['ghi', 'demand'].includes(params.type))
        this.selectedType = params.type;

      if (params.horizon) {
        const opts = this.horizonOptions;
        if (opts.some(h => h.id === params.horizon))
          this.selectedHorizon = params.horizon;
      } else {
        this.selectedHorizon = this._defaultHorizon(this.selectedType);
      }

      content.innerHTML = this._renderShell();

    } catch (err) {
      content.innerHTML = `
        <div class="page-wrapper">
          <div class="card" style="max-width:640px;margin:40px auto">
            <div class="card-body text-center">
              ${Components.emptyState('fa-exclamation-triangle', 'Page indisponible',
                err?.message || 'Impossible de charger les wilayas.',
                `<button class="btn btn-primary" onclick="App.navigate('landing')">
                   <i class="fas fa-home"></i> Retour
                 </button>`)}
            </div>
          </div>
        </div>`;
    }
  },

  // Fetches, normalises, and sorts the wilaya list; no-ops if already loaded
  async _loadWilayas() {
    if (this.wilayas.length) return;
    const res  = await this.fetchJson('/wilayas');
    const data = Array.isArray(res?.data) ? res.data : [];
    if (!data.length) throw new Error('Aucune wilaya disponible.');
    this.wilayas = data
      .map(d => ({
        code:   String(d.code ?? d.id ?? '').padStart(2, '0'),
        name:   d.nom || d.name,
        region: d.region || '—',
        lat:    d.lat ?? null,
        lon:    d.lon ?? null,
      }))
      .filter(d => d.name)
      .sort((a, b) => a.name.localeCompare(b.name, 'fr'));
  },

  // Destroys all active Chart.js instances to prevent canvas reuse errors
  destroyCharts() {
    Object.values(this.charts).forEach(c => { try { c.destroy(); } catch (_) {} });
    this.charts = {};
  },

  // Renders the full page shell: wilaya selector, type/horizon buttons, and results placeholder
  _renderShell() {
    const opts = this.wilayas.map(w =>
      `<option value="${this._e(w.name)}" ${w.name === this.selectedWilaya ? 'selected' : ''}>
         ${this._e(w.name)}
       </option>`
    ).join('');

    return `
      <div class="page-wrapper">

        ${Components.pageHeader(
          'fa-chart-line',
          'Prévision énergétique',
          'Rayonnement solaire (GHI) et demande électrique (MW) par wilaya'
        )}

        <div class="card mb-5">
          <div class="card-header">
            <div class="card-title">
              <i class="fas fa-sliders-h"></i> Paramètres de la prévision
            </div>
          </div>
          <div class="card-body">
            <div style="display:grid;grid-template-columns:1fr;gap:20px">

              <!-- Wilaya dropdown -->
              <div>
                <label class="form-label" for="fc-wilaya">
                  <i class="fas fa-map-marker-alt"></i> Wilaya à analyser
                </label>
                <select id="fc-wilaya" class="form-select"
                        onchange="ForecastPage.setWilaya(this.value)">
                  ${opts}
                </select>
              </div>

              <!-- Forecast type toggle: GHI or demand MW -->
              <div>
                <label class="form-label">
                  <i class="fas fa-layer-group"></i> Type de prévision
                </label>
                <div style="display:flex;gap:12px;flex-wrap:wrap" id="fc-type-btns">
                  ${this._typeBtn('ghi',    'fa-sun',  'Potentiel solaire',  'GHI — Irradiation globale')}
                  ${this._typeBtn('demand', 'fa-bolt', 'Demande électrique', 'Demand_MW — Consommation')}
                </div>
              </div>

              <!-- Horizon / granularity selector; rebuilt when the type changes -->
              <div id="fc-horizon-wrap">
                <label class="form-label">
                  <i class="fas fa-clock"></i> Horizon / Granularité
                </label>
                <div style="display:flex;gap:10px;flex-wrap:wrap" id="fc-horizon-btns">
                  ${this._renderHorizonBtns()}
                </div>
              </div>

              <button class="btn btn-primary"
                      onclick="ForecastPage.runForecast(true)"
                      style="width:100%;padding:14px;font-size:16px;font-weight:700">
                <i class="fas fa-bolt"></i> Lancer la prévision
              </button>

            </div>
          </div>
        </div>

        <div id="fc-results">${this._renderWelcome()}</div>

      </div>`;
  },

  // Returns the HTML for a single forecast-type toggle button
  _typeBtn(type, icon, label, sub) {
    const active = this.selectedType === type;
    const color  = type === 'demand' ? 'var(--blue-400)' : 'var(--amber-400)';
    return `
      <button type="button"
        class="btn ${active ? 'btn-primary' : 'btn-secondary'} btn-sm"
        style="flex:1;min-width:180px;padding:14px 18px;text-align:left;
               ${active ? `border-left:4px solid ${color}` : ''}"
        onclick="ForecastPage.setType('${type}')"
        data-type="${type}">
        <div style="display:flex;align-items:center;gap:10px">
          <i class="fas ${icon}" style="font-size:18px;color:${active ? color : 'var(--text-muted)'}"></i>
          <div>
            <div style="font-weight:700;font-size:14px">${label}</div>
            <div style="font-size:11px;opacity:0.7;margin-top:2px">${sub}</div>
          </div>
        </div>
      </button>`;
  },

  // Returns the HTML for all horizon buttons matching the active forecast type
  _renderHorizonBtns() {
    return this.horizonOptions.map(o => `
      <button type="button"
        class="btn ${o.id === this.selectedHorizon ? 'btn-primary' : 'btn-secondary'} btn-sm"
        style="flex:1;min-width:130px;padding:10px 14px"
        onclick="ForecastPage.setHorizon('${o.id}')"
        data-horizon="${o.id}">
        <i class="fas ${o.icon}" style="margin-bottom:4px"></i>
        <div style="font-weight:700">${o.label}</div>
        <div style="font-size:10px;opacity:0.8;margin-top:2px">${o.sub}</div>
      </button>`).join('');
  },

  // Returns the empty-state card shown before the first forecast is run
  _renderWelcome() {
    return `
      <div class="card" style="
        text-align:center;padding:52px 30px;
        background:linear-gradient(135deg,rgba(245,158,11,.06),rgba(59,130,246,.06))">
        <div style="font-size:52px;margin-bottom:16px">⚡</div>
        <h3 style="margin:0 0 10px;font-size:22px;color:var(--text-primary)">
          Prêt à analyser l'énergie de votre wilaya
        </h3>
        <p style="max-width:560px;margin:0 auto;color:var(--text-secondary);
                  font-size:14px;line-height:1.7">
          Sélectionnez une <strong>wilaya</strong>, choisissez le type de prévision
          (<strong>GHI solaire</strong> ou <strong>demande électrique</strong>),
          définissez l'horizon, puis cliquez sur <strong>Lancer la prévision</strong>.
        </p>
        <div style="display:flex;justify-content:center;gap:28px;margin-top:32px;flex-wrap:wrap">
          ${[['☀️','Rayonnement GHI'], ['⚡','Demande MW'],
             ['📈','Meilleure période'], ['🤖','IA ML entraînée']].map(([ic, lb]) => `
            <div style="text-align:center">
              <div style="font-size:28px">${ic}</div>
              <div style="font-size:11px;color:var(--text-secondary);margin-top:6px">${lb}</div>
            </div>`).join('')}
        </div>
      </div>`;
  },

  // Updates the active type, resets the horizon to the type's default, and clears results
  setType(type) {
    if (!['ghi', 'demand'].includes(type)) return;
    this.selectedType    = type;
    this.selectedHorizon = this._defaultHorizon(type);

    // Reflect the new active state on all type toggle buttons
    document.querySelectorAll('[data-type]').forEach(btn => {
      const t      = btn.getAttribute('data-type');
      const active = t === type;
      const color  = t === 'demand' ? 'var(--blue-400)' : 'var(--amber-400)';
      btn.classList.toggle('btn-primary',   active);
      btn.classList.toggle('btn-secondary', !active);
      btn.style.borderLeft = active ? `4px solid ${color}` : '';
      const icon = btn.querySelector('i.fas');
      if (icon) icon.style.color = active ? color : 'var(--text-muted)';
    });

    // Rebuild horizon buttons for the new type
    const wrap = document.getElementById('fc-horizon-btns');
    if (wrap) wrap.innerHTML = this._renderHorizonBtns();

    // Reset the results area to the welcome state
    this.destroyCharts();
    this.hasRun = false;
    const resEl = document.getElementById('fc-results');
    if (resEl) resEl.innerHTML = this._renderWelcome();
  },

  // Updates the selected horizon and toggles the active class on horizon buttons
  setHorizon(id) {
    if (!this.horizonOptions.some(h => h.id === id)) return;
    this.selectedHorizon = id;
    document.querySelectorAll('[data-horizon]').forEach(btn => {
      const h = btn.getAttribute('data-horizon');
      btn.classList.toggle('btn-primary',   h === id);
      btn.classList.toggle('btn-secondary', h !== id);
    });
  },

  // Updates the selected wilaya when the dropdown value changes
  setWilaya(name) {
    if (name) this.selectedWilaya = name;
  },

  // Entry point for running a forecast; routes to the GHI or demand handler based on type
  async runForecast(showToast = false) {
    if (!this.selectedWilaya) {
      window.Utils?.toast?.('warning', 'Sélection', "Choisissez d'abord une wilaya.");
      return;
    }

    const resEl = document.getElementById('fc-results');
    if (resEl) resEl.innerHTML = Components.loading('',
      `Prévision <strong>${this.selectedType === 'demand' ? 'demande MW' : 'GHI'}</strong>
       pour <strong>${this._e(this.selectedWilaya)}</strong>…`);
    this.destroyCharts();

    try {
      if (this.selectedType === 'demand') {
        await this._runDemandForecast(showToast, resEl);
      } else {
        await this._runGHIForecast(showToast, resEl);
      }
    } catch (err) {
      console.error('ForecastPage error:', err);
      if (resEl) resEl.innerHTML = `
        <div class="card">
          <div class="card-body text-center">
            ${Components.emptyState('fa-exclamation-circle', 'Calcul impossible',
              err?.message || 'Impossible de calculer la prévision.',
              `<button class="btn btn-secondary btn-sm"
                       onclick="ForecastPage.runForecast(true)">
                 <i class="fas fa-redo"></i> Réessayer
               </button>`)}
          </div>
        </div>`;
    }
  },

  // Fetches GHI forecast data and renders the solar potential results panel
  async _runGHIForecast(showToast, resEl) {
    const enc   = encodeURIComponent(this.selectedWilaya);
    const fcRes = await this.fetchJson(`/forecast-simple/${enc}?horizon=${this.selectedHorizon}`);
    this.forecastResult = fcRes?.data || null;
    this.hasRun = true;
    if (!this.forecastResult)
      throw new Error('Prévision GHI indisponible pour cette wilaya.');
    if (resEl) resEl.innerHTML = this._renderGHIResults();
    this._initForecastChart();
    if (showToast && window.Utils?.toast)
      Utils.toast('success', 'Prévision GHI prête',
        `${this.selectedWilaya} • ${this.forecastResult.horizon_label}`);
  },

  // Fetches demand forecast data and renders the electricity consumption results panel
  async _runDemandForecast(showToast, resEl) {
    const enc = encodeURIComponent(this.selectedWilaya);
    const res = await this.fetchJson(`/forecast-demand/${enc}?horizon=${this.selectedHorizon}`);
    this.demandResult = res?.data || null;
    this.hasRun = true;
    if (!this.demandResult)
      throw new Error('Prévision demande indisponible pour cette wilaya.');
    if (resEl) resEl.innerHTML = this._renderDemandResults();
    this._initDemandCharts();
    if (showToast && window.Utils?.toast)
      Utils.toast('success', 'Prévision demande prête',
        `${this.selectedWilaya} • ${this.demandResult.horizon_label}`);
  },

  // Builds the GHI results HTML: bar chart canvas, production KPI cards, best/worst period cards
  _renderGHIResults() {
    const d     = this.forecastResult;
    const total = Number(d.total_production_kwh || 0);
    const best  = d.best_period  || { label: '—', production_kwh: 0 };
    const worst = d.worst_period || { label: '—', production_kwh: 0 };
    const ghi   = Number(d.ghi_predicted_wm2 || 0);

    const xAxisLabel = {
      '24h': 'Heure de la journée',
      '7j':  'Jour de la semaine',
      '30j': 'Jour du mois',
    }[this.selectedHorizon] || 'Période';

    return `
      <div class="card mb-5">
        <div class="card-header">
          <div class="card-title">
            <i class="fas fa-sun"></i>
            Potentiel solaire prévu —
            <strong style="color:var(--amber-400)">${this._e(this.selectedWilaya)}</strong>
            · ${this._e(d.horizon_label)}
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="badge badge-blue">${d.production_kwh?.length || 0} points</span>
            ${ghi ? `<span class="badge badge-measured">GHI moy. ${ghi} W/m²</span>` : ''}
          </div>
        </div>
        <div class="card-body">
          <div style="font-size:13px;color:var(--text-secondary);
                      margin-bottom:16px;line-height:1.8;
                      display:flex;flex-wrap:wrap;gap:16px;align-items:center">
            <span>
              <i class="fas fa-bolt" style="color:var(--amber-400)"></i>
              Production estimée (kWh) — <strong>${xAxisLabel.toLowerCase()}</strong>
            </span>
            <span><span style="color:var(--green-400);font-size:16px">●</span> Meilleure période</span>
            <span><span style="color:var(--blue-400);font-size:16px">●</span> Période la plus faible</span>
            <span><span style="color:var(--amber-400);font-size:16px">●</span> Période standard</span>
          </div>
          <div style="height:360px;position:relative">
            <canvas id="chart-fc-prod"></canvas>
          </div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
                  gap:14px;margin-bottom:20px">
        ${this._card('⚡ Production totale estimée',
            `${Utils.formatNumber(total, 0)} kWh`,
            `sur ${this._e(d.horizon_label.toLowerCase())}`,
            'var(--amber-400)', 'fa-bolt')}
        ${ghi ? this._card('☀️ Rayonnement solaire (GHI)',
            `${ghi} W/m²`,
            'irradiation globale horizontale prédite',
            'var(--orange-400)', 'fa-sun') : ''}
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px">
        <div class="card" style="border-left:4px solid var(--green-400)">
          <div class="card-body">
            <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;
                        font-weight:600;margin-bottom:8px">🌟 Meilleure période</div>
            <div style="font-size:22px;font-weight:800;color:var(--green-400)">${this._e(best.label)}</div>
            <div style="font-size:13px;color:var(--text-secondary);margin-top:6px">
              <i class="fas fa-bolt"></i> ${Utils.formatNumber(best.production_kwh, 1)} kWh estimés
            </div>
          </div>
        </div>
        <div class="card" style="border-left:4px solid var(--blue-400)">
          <div class="card-body">
            <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;
                        font-weight:600;margin-bottom:8px">📉 Période la plus faible</div>
            <div style="font-size:22px;font-weight:800;color:var(--blue-400)">${this._e(worst.label)}</div>
            <div style="font-size:13px;color:var(--text-secondary);margin-top:6px">
              <i class="fas fa-bolt"></i> ${Utils.formatNumber(worst.production_kwh, 1)} kWh estimés
            </div>
          </div>
        </div>
      </div>`;
  },

  // Builds the demand results HTML: bar chart, KPI cards, peak/trough cards,
  // optional forecast-vs-historical line chart, and model metadata panel
  _renderDemandResults() {
    const d     = this.demandResult;
    const vals  = d.demand_mw || [];
    const total = vals.reduce((s, v) => s + v, 0);
    const best  = d.best_period  || { label: '—', demand_mw: 0 };
    const worst = d.worst_period || { label: '—', demand_mw: 0 };
    const m     = d.model_metrics || {};

    const horizonLabel = d.horizon_label || this.selectedHorizon;
    const xLabel = {
      daily:   'Jour',
      weekly:  'Semaine',
      monthly: 'Mois',
    }[this.selectedHorizon] || 'Période';

    return `
      <div class="card mb-5">
        <div class="card-header">
          <div class="card-title">
            <i class="fas fa-bolt"></i>
            Prévision demande électrique —
            <strong style="color:var(--blue-400)">${this._e(this.selectedWilaya)}</strong>
            · ${this._e(horizonLabel)}
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="badge badge-blue">${vals.length} points</span>
            <span class="badge" style="background:rgba(59,130,246,.15);color:var(--blue-400)">
              ${this._e(d.model_name || 'ML')}
            </span>
          </div>
        </div>
        <div class="card-body">
          <div style="font-size:13px;color:var(--text-secondary);
                      margin-bottom:16px;line-height:1.8;
                      display:flex;flex-wrap:wrap;gap:16px;align-items:center">
            <span>
              <i class="fas fa-bolt" style="color:var(--blue-400)"></i>
              Demande électrique estimée (MW) — <strong>${xLabel.toLowerCase()}</strong>
            </span>
            <span><span style="color:var(--green-400);font-size:16px">●</span> Pic de consommation</span>
            <span><span style="color:var(--red-400,#f87171);font-size:16px">●</span> Consommation minimale</span>
            <span><span style="color:var(--blue-400);font-size:16px">●</span> Consommation standard</span>
          </div>
          <div style="height:360px;position:relative">
            <canvas id="chart-demand-bar"></canvas>
          </div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
                  gap:14px;margin-bottom:20px">
        ${this._card('⚡ Consommation totale',
            `${Utils.formatNumber(total, 1)} MW`,
            `cumulé sur ${this._e(horizonLabel.toLowerCase())}`,
            'var(--blue-400)', 'fa-bolt')}
        ${this._card('📊 Consommation moyenne',
            `${Utils.formatNumber(vals.length ? total / vals.length : 0, 2)} MW`,
            'par période prévue',
            'var(--indigo-400,#818cf8)', 'fa-chart-bar')}
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
                  gap:14px;margin-bottom:20px">
        <div class="card" style="border-left:4px solid var(--green-400)">
          <div class="card-body">
            <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;
                        font-weight:600;margin-bottom:8px">⚡ Pic de consommation</div>
            <div style="font-size:22px;font-weight:800;color:var(--green-400)">${this._e(best.label)}</div>
            <div style="font-size:13px;color:var(--text-secondary);margin-top:6px">
              ${Utils.formatNumber(best.demand_mw, 2)} MW
            </div>
          </div>
        </div>
        <div class="card" style="border-left:4px solid #f87171">
          <div class="card-body">
            <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;
                        font-weight:600;margin-bottom:8px">📉 Consommation minimale</div>
            <div style="font-size:22px;font-weight:800;color:#f87171">${this._e(worst.label)}</div>
            <div style="font-size:13px;color:var(--text-secondary);margin-top:6px">
              ${Utils.formatNumber(worst.demand_mw, 2)} MW
            </div>
          </div>
        </div>
      </div>

      <!-- Comparison chart rendered only when the API provides a historical average baseline -->
      ${d.historical_avg != null ? `
      <div class="card mb-5">
        <div class="card-header">
          <div class="card-title">
            <i class="fas fa-chart-line"></i>
            Comparaison prévision vs moyenne historique
          </div>
        </div>
        <div class="card-body">
          <div style="height:280px;position:relative">
            <canvas id="chart-demand-compare"></canvas>
          </div>
        </div>
      </div>` : ''}

      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <i class="fas fa-robot"></i> Informations sur le modèle
          </div>
        </div>
        <div class="card-body">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
            ${this._infoItem('Modèle IA',        d.model_name || '—')}
            ${this._infoItem('Cible',             'Demand_MW (MW)')}
            ${this._infoItem('Fenêtre look-back', d.look_back != null ? `${d.look_back} périodes` : '—')}
            ${this._infoItem('Entraîné sur',      d.train_period || '2019–2022')}
            ${this._infoItem('Testé sur',         d.test_period  || '2023')}
            ${m.R2 != null ? this._infoItem('R²', (m.R2 * 100).toFixed(2) + '%') : ''}
          </div>
        </div>
      </div>`;
  },

  // Returns a small labelled value tile used inside the model metadata grid
  _infoItem(label, value) {
    return `
      <div style="background:rgba(255,255,255,.04);border-radius:8px;padding:12px">
        <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;
                    font-weight:600;margin-bottom:4px">${label}</div>
        <div style="font-size:14px;font-weight:700;color:var(--text-primary)">${this._e(String(value))}</div>
      </div>`;
  },

  // Returns a KPI card with a coloured top border, icon, primary value, and sub-label
  _card(label, value, sub, color, icon) {
    return `
      <div class="card" style="border-top:3px solid ${color}">
        <div class="card-body">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <i class="fas ${icon}" style="color:${color};font-size:18px"></i>
            <span style="font-size:11px;color:var(--text-muted);
                         text-transform:uppercase;letter-spacing:.05em;
                         font-weight:600">${label}</span>
          </div>
          <div style="font-size:24px;font-weight:800;color:${color};line-height:1.2">${value}</div>
          <div style="font-size:12px;color:var(--text-secondary);margin-top:6px">${sub}</div>
        </div>
      </div>`;
  },

  // Instantiates the GHI production bar chart; bars are colour-coded by best / worst / standard period
  _initForecastChart() {
    const d      = this.forecastResult;
    const labels = d.labels         || [];
    const values = d.production_kwh || [];
    const best   = d.best_period    || {};
    const worst  = d.worst_period   || {};

    const xLabel = {
      '24h': 'Heure',
      '7j':  'Jour',
      '30j': 'Jour du mois',
    }[this.selectedHorizon] || 'Période';

    const colors = values.map((_, i) => {
      const lbl = labels[i];
      if (lbl === best.label)  return 'rgba(74,222,128,.85)';
      if (lbl === worst.label) return 'rgba(96,165,250,.85)';
      return 'rgba(245,158,11,.75)';
    });

    const ctx = document.getElementById('chart-fc-prod');
    if (!ctx) return;

    this.charts['fc-prod'] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label:           'Production (kWh)',
          data:            values,
          backgroundColor: colors,
          borderRadius:    5,
          borderSkipped:   false,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: items => `${xLabel} : ${items[0].label}`,
              label: ctx   => ` ${Utils.formatNumber(ctx.parsed.y, 2)} kWh`,
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: xLabel, color: '#e2e8f0', font: { size: 12, weight: '600' }, padding: { top: 8 } },
            grid:  { color: 'rgba(255,255,255,.06)' },
            ticks: { color: '#e2e8f0', maxRotation: 45, autoSkip: true, maxTicksLimit: 16 },
          },
          y: {
            title: { display: true, text: 'Production (kWh)', color: '#e2e8f0', font: { size: 12, weight: '600' }, padding: { bottom: 8 } },
            grid:  { color: 'rgba(255,255,255,.06)' },
            beginAtZero: true,
            ticks: { color: '#e2e8f0', callback: v => `${Utils.formatNumber(v, 0)} kWh` },
          },
        },
      },
    });
  },

  // Instantiates both demand charts: a bar chart for absolute values and,
  // when a historical baseline is available, a line chart for forecast vs historical comparison
  _initDemandCharts() {
    const d      = this.demandResult;
    const labels = d.labels     || [];
    const values = d.demand_mw  || [];
    const best   = d.best_period  || {};
    const worst  = d.worst_period || {};

    const xLabel = {
      daily:   'Jour',
      weekly:  'Semaine',
      monthly: 'Mois',
    }[this.selectedHorizon] || 'Période';

    // Peak bar = green, trough bar = red, all other bars = blue
    const colors = values.map((_, i) => {
      const lbl = labels[i];
      if (lbl === best.label)  return 'rgba(74,222,128,.85)';
      if (lbl === worst.label) return 'rgba(248,113,113,.85)';
      return 'rgba(96,165,250,.75)';
    });

    // Demand bar chart
    const ctx1 = document.getElementById('chart-demand-bar');
    if (ctx1) {
      this.charts['demand-bar'] = new Chart(ctx1, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label:           'Demande (MW)',
            data:            values,
            backgroundColor: colors,
            borderRadius:    5,
            borderSkipped:   false,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: items => `${xLabel} : ${items[0].label}`,
                label: ctx   => ` ${Utils.formatNumber(ctx.parsed.y, 2)} MW`,
              },
            },
          },
          scales: {
            x: {
              title: { display: true, text: xLabel, color: '#e2e8f0', font: { size: 12, weight: '600' }, padding: { top: 8 } },
              grid:  { color: 'rgba(255,255,255,.06)' },
              ticks: { color: '#e2e8f0', maxRotation: 45, autoSkip: true, maxTicksLimit: 20 },
            },
            y: {
              title: { display: true, text: 'Demande (MW)', color: '#e2e8f0', font: { size: 12, weight: '600' }, padding: { bottom: 8 } },
              grid:  { color: 'rgba(255,255,255,.06)' },
              beginAtZero: false,
              ticks: { color: '#e2e8f0', callback: v => `${Utils.formatNumber(v, 1)} MW` },
            },
          },
        },
      });
    }

    // Forecast vs historical average line chart; skipped when no baseline is provided
    const ctx2 = document.getElementById('chart-demand-compare');
    if (ctx2 && d.historical_avg != null) {
      const histVals = Array(values.length).fill(d.historical_avg);
      this.charts['demand-compare'] = new Chart(ctx2, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label:           'Prévision ML',
              data:            values,
              borderColor:     'rgba(96,165,250,1)',
              backgroundColor: 'rgba(96,165,250,.12)',
              borderWidth:  2.5,
              pointRadius:  values.length <= 30 ? 4 : 2,
              fill:         true,
              tension:      0.35,
            },
            {
              label:       'Moyenne historique',
              data:        histVals,
              borderColor: 'rgba(245,158,11,.7)',
              borderDash:  [6, 4],
              borderWidth: 1.5,
              pointRadius: 0,
              fill:        false,
            },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              labels:  { color: '#e2e8f0', font: { size: 12 } },
            },
            tooltip: {
              callbacks: {
                label: ctx => ` ${ctx.dataset.label} : ${Utils.formatNumber(ctx.parsed.y, 2)} MW`,
              },
            },
          },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,.06)' }, ticks: { color: '#e2e8f0', autoSkip: true, maxTicksLimit: 16 } },
            y: { grid: { color: 'rgba(255,255,255,.06)' }, ticks: { color: '#e2e8f0', callback: v => `${Utils.formatNumber(v, 1)} MW` } },
          },
        },
      });
    }
  },

  // HTML-escapes a value before injecting it into the DOM to prevent XSS
  _e(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g,  '&amp;')
      .replace(/</g,  '&lt;')
      .replace(/>/g,  '&gt;')
      .replace(/"/g,  '&quot;');
  },
};