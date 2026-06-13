const ROIPage = {

  // ── Constantes (identiques backend) ──────────────────────────────────
  CAPEX: { residentiel: 75_000, industriel: 65_000, ferme: 58_000 },
  TARIF: { residentiel: 5.00,   industriel: 10.00,  ferme: 12.00  },
  OPEX:  { residentiel: 0.010,  industriel: 0.012,  ferme: 0.015  },
  PR:    { residentiel: 0.78,   industriel: 0.82,   ferme: 0.85   },

  PANELS: [
    { wc: 100, prix: 14_500 },
    { wc: 150, prix: 21_500 },
    { wc: 250, prix: 27_000 },
    { wc: 400, prix: 22_500 },
    { wc: 500, prix: 30_000 },
    { wc: 600, prix: 35_000 },
  ],

  TYPES: [
    { id: 'residentiel', labelKey: 'roi.types.residentiel', icon: '🏠', fallback: 'Résidentiel' },
    { id: 'industriel',  labelKey: 'roi.types.industriel',  icon: '🏭', fallback: 'Industriel' },
    { id: 'ferme',       labelKey: 'roi.types.ferme',       icon: '⚡', fallback: 'Ferme solaire' },
  ],

  YEARS:   5,
  DEGR:    0.005,
  CO2K:    0.600,
  HH_KWH:  3_800,
  TREE_KG: 21,
  KM_KG:   0.12,

  // ── État ──────────────────────────────────────────────────────────────
  state: {
    type:       'residentiel',
    panelWc:    400,
    panelPrix:  22_500,
    nbPanneaux: 10,
    inflation:  3,            // pourcentage entier (0..10)
    wilaya:     '',
    wilayas:    [],
    ghiMap:     {},
    hasResult:  false,
    lastHistoryId: null,
  },

  _charts:  {},
  _syncing: false,   // anti-boucle sync budget ↔ nb

  // ── Helpers API ───────────────────────────────────────────────────────
  apiBase() {
    return (window.API && window.API.BASE_URL) || (window.BACKEND_URL) || 'http://localhost:5000/api';
  },

  async _get(ep) {
    try {
      const headers = { 'Content-Type': 'application/json' };
      const tok = sessionStorage.getItem('auth_token');
      if (tok) headers['Authorization'] = `Bearer ${tok}`;
      const r = await fetch(`${this.apiBase()}${ep}`, { credentials: 'include', headers });
      return r.ok ? r.json() : null;
    } catch { return null; }
  },

  async _post(ep, body) {
    try {
      const headers = { 'Content-Type': 'application/json' };
      const tok = sessionStorage.getItem('auth_token');
      if (tok) headers['Authorization'] = `Bearer ${tok}`;
      const r = await fetch(`${this.apiBase()}${ep}`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify(body || {}),
      });
      return r.ok ? r.json() : null;
    } catch { return null; }
  },

  // ── i18n helper (utilise le système I18N existant) ────────────────────
  t(key, fallback) {
    if (typeof window.I18N !== 'undefined' && typeof window.I18N.t === 'function') {
      const v = window.I18N.t(key);
      if (v !== undefined && v !== key) return v;
    }
    return fallback != null ? fallback : key;
  },

  getState() {
    return {
      type:       this.state.type,
      wilaya:     this.state.wilaya,
      inflation:  this.state.inflation,
      panelWc:    this.state.panelWc,
      nbPanneaux: this.state.nbPanneaux,
      hasResult:  this.state.hasResult,
    };
  },

  // ── Rendu principal ───────────────────────────────────────────────────
  async render(params = {}, restoreState = {}) {
    const root = document.getElementById('page-content');
    root.innerHTML = `<div class="roi-loading"><span class="roi-spin">☀</span> ${this.t('roi.loading', 'Chargement du calcul ROI...')}</div>`;
    this._destroyCharts();

    // Réapplique un état précédemment sauvegardé (navigation interne)
    if (restoreState.type)       this.state.type       = restoreState.type;
    if (restoreState.wilaya)     this.state.wilaya     = restoreState.wilaya;
    if (restoreState.inflation !== undefined) this.state.inflation = restoreState.inflation;
    if (restoreState.panelWc)    this.state.panelWc    = restoreState.panelWc;
    if (restoreState.nbPanneaux) this.state.nbPanneaux = restoreState.nbPanneaux;

    // Charge la liste des wilayas une seule fois
    if (!this.state.wilayas.length) {
      const res  = await this._get('/wilayas');
      const data = Array.isArray(res?.data) ? res.data : [];
      this.state.wilayas = data
        .map(w => ({ code: String(w.code ?? w.id ?? '').padStart(2, '0'), name: w.nom || w.name }))
        .filter(w => w.name)
        .sort((a, b) => a.name.localeCompare(b.name, 'fr'));
    }
    if (!this.state.wilaya && this.state.wilayas.length)
      this.state.wilaya = this.state.wilayas[0].name;
    if (params.type   && this.TYPES.some(t => t.id === params.type))             this.state.type   = params.type;
    if (params.wilaya && this.state.wilayas.some(w => w.name === params.wilaya)) this.state.wilaya = params.wilaya;

    // Vérifie le plan de l'utilisateur ; si l'endpoint est inaccessible,
    // on retombe sur "free" par sécurité (accès le plus restrictif).
    const planRes = await this._get('/plan/info');
    const plan    = planRes?.data?.plan ?? 'free';

    root.innerHTML = `<div class="roi-wrap">${this._htmlForm()}<div id="roi-results"></div></div>`;

    if (plan === 'free') {
      this._applyFreeOverlay();
    } else {
      this._bind();
    }
  },

  // ── Overlay plan gratuit ──────────────────────────────────────────────
  _applyFreeOverlay() {
    const wrap = document.querySelector('.roi-wrap');
    if (!wrap) return;
    wrap.style.position = 'relative';
    const overlay = document.createElement('div');
    overlay.className = 'roi-free-overlay';
    overlay.innerHTML = `
      <div class="roi-free-box">
        <div class="roi-free-icon">🔒</div>
        <div class="roi-free-title">${this.t('roi.gating.title', 'Calcul ROI réservé au plan Pro')}</div>
        <div class="roi-free-desc">${this.t('roi.gating.desc', 'Calcul ROI disponible avec le plan Pro — 4 000 DA/mois')}</div>
        <a href="#pricing" class="roi-free-btn" onclick="App.navigate('pricing');return false;">${this.t('roi.gating.cta', 'Voir les plans')}</a>
      </div>`;
    wrap.appendChild(overlay);
    // Désactive et grise le formulaire pour les utilisateurs non-Pro
    const form = wrap.querySelector('.roi-section');
    if (form) { form.style.opacity = '0.35'; form.style.pointerEvents = 'none'; }
  },

  // ── Formulaire HTML ───────────────────────────────────────────────────
  _htmlForm() {
    const s        = this.state;
    const wilaOpts = s.wilayas.map(w =>
      `<option value="${w.name}" ${w.name === s.wilaya ? 'selected' : ''}>${w.name}</option>`
    ).join('');
    const panelOpts = this.PANELS.map(p =>
      `<option value="${p.wc}" data-prix="${p.prix}" ${p.wc === s.panelWc ? 'selected' : ''}>
        ${p.wc} W – ${p.prix.toLocaleString('fr')} DA
      </option>`
    ).join('');
    const typeLabel = (t) => this.t(t.labelKey, t.fallback);
    const typesBtns = this.TYPES.map(t => `
      <button class="roi-type-btn ${t.id === s.type ? 'active' : ''}" data-type="${t.id}">
        ${t.icon} ${typeLabel(t)}
      </button>`).join('');
    const kwc    = (s.nbPanneaux * s.panelWc / 1000).toFixed(1);
    const budget = s.nbPanneaux * s.panelPrix;
    const tarif  = this.TARIF[s.type];
    const currentTypeLabel = typeLabel(this.TYPES.find(t => t.id === s.type)).toLowerCase();

    return `
<div class="roi-section">
  <div class="roi-section-title">${this.t('roi.form.projectType', 'Type de projet')}</div>
  <div class="roi-type-row">${typesBtns}</div>
  <div class="roi-tarif-badge" id="roi-tarif-badge">
    ⚡ ${this.t('roi.form.tarif', 'Tarif')} ${currentTypeLabel} : ${tarif} DA/kWh
  </div>

  <div class="roi-cols">
    <div class="roi-group">
      <div class="roi-group-title">${this.t('roi.form.panels', 'Panneaux')}</div>
      <div class="roi-field">
        <label>${this.t('roi.form.panelPower', 'Puissance panneau')}</label>
        <select id="roi-panel-sel">${panelOpts}</select>
      </div>
      <div class="roi-field">
        <label>${this.t('roi.form.nbPanels', 'Nombre de panneaux')}</label>
        <div class="roi-input-row">
          <input id="roi-nb" type="number" min="1" max="10000" value="${s.nbPanneaux}">
          <span class="roi-badge" id="roi-kwc-badge">${kwc} kWc</span>
        </div>
      </div>
      <div class="roi-field">
        <label>${this.t('roi.form.budget', 'Budget (DA)')}</label>
        <div class="roi-input-row">
          <input id="roi-budget" type="number" min="0" step="10000" value="${budget}">
          <span class="roi-unit">DA</span>
        </div>
      </div>
    </div>

    <div class="roi-group">
      <div class="roi-group-title">${this.t('roi.form.params', 'Paramètres')}</div>
      <div class="roi-field">
        <label>${this.t('roi.form.wilaya', 'Wilaya')}</label>
        <select id="roi-wilaya">${wilaOpts || '<option>Alger</option>'}</select>
      </div>
      <div class="roi-slider-field">
        <div class="roi-slider-top">
          <label>${this.t('roi.form.inflation', 'Inflation des charges')}</label>
          <span id="roi-inf-val" class="roi-slider-val">${s.inflation}%</span>
        </div>
        <input id="roi-inflation" type="range" min="0" max="10" step="0.5" value="${s.inflation}">
        <div class="roi-inf-note">${this.t('roi.form.inflationNote', 'Inflation ↑ ⟹ OPEX ↑ ⟹ ROI ↓')}</div>
      </div>
    </div>
  </div>

  <button id="roi-btn" class="roi-btn-calc">⚡ ${this.t('roi.form.calculate', 'Calculer le ROI')}</button>
</div>`;
  },

  // ── Binding événements ────────────────────────────────────────────────
  _bind() {
    // Sélection du type de projet
    document.querySelectorAll('.roi-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.roi-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.state.type = btn.dataset.type;
        // Met à jour le badge affichant le tarif du type sélectionné
        const tarif = this.TARIF[this.state.type];
        const typeObj = this.TYPES.find(t => t.id === this.state.type);
        const lbl = this.t(typeObj.labelKey, typeObj.fallback).toLowerCase();
        const badge = document.getElementById('roi-tarif-badge');
        if (badge) badge.textContent = `⚡ ${this.t('roi.form.tarif', 'Tarif')} ${lbl} : ${tarif} DA/kWh`;
        // Le CAPEX dépend du type : on recalcule le nombre de panneaux à partir du budget courant
        this._recalcNbFromBudget();
        this._liveUpdate();
      });
    });

    // Changement de modèle de panneau : met à jour le budget et le kWc
    document.getElementById('roi-panel-sel')?.addEventListener('change', e => {
      const opt = e.target.selectedOptions[0];
      this.state.panelWc   = +e.target.value;
      this.state.panelPrix = +opt.dataset.prix;
      this._syncBudgetFromNb();
      this._liveUpdate();
    });

    // Nombre de panneaux modifié manuellement → recalcule le budget
    document.getElementById('roi-nb')?.addEventListener('input', e => {
      if (this._syncing) return;
      this.state.nbPanneaux = Math.max(1, +e.target.value || 1);
      this._syncBudgetFromNb();
      this._liveUpdate();
    });

    // Budget modifié manuellement → déduit le nombre de panneaux et le kWc
    document.getElementById('roi-budget')?.addEventListener('input', e => {
      if (this._syncing) return;
      const budget = Math.max(0, +e.target.value || 0);
      this._syncNbAndKwcFromBudget(budget);
      this._liveUpdate();
    });

    // Changement de wilaya → charge le GHI/température correspondants
    document.getElementById('roi-wilaya')?.addEventListener('change', async e => {
      this.state.wilaya = e.target.value;
      await this._ensureGhi(this.state.wilaya);
      this._liveUpdate();
    });

    // Curseur d'inflation
    document.getElementById('roi-inflation')?.addEventListener('input', e => {
      this.state.inflation = +e.target.value;
      const el = document.getElementById('roi-inf-val');
      if (el) el.textContent = `${e.target.value}%`;
      this._liveUpdate();
    });

    // Premier calcul : affiche les résultats et sauvegarde l'historique côté backend
    document.getElementById('roi-btn')?.addEventListener('click', () => this._calc());
  },

  // ── Sync helpers ──────────────────────────────────────────────────────

  /** Recalcule le budget et le kWc à partir du nombre de panneaux et du modèle choisi */
  _syncBudgetFromNb() {
    if (this._syncing) return;
    this._syncing = true;
    const budget = this.state.nbPanneaux * this.state.panelPrix;
    const kwc    = (this.state.nbPanneaux * this.state.panelWc / 1000).toFixed(1);
    const budgetEl = document.getElementById('roi-budget');
    const badge    = document.getElementById('roi-kwc-badge');
    if (budgetEl) budgetEl.value = budget;
    if (badge)    badge.textContent = `${kwc} kWc`;
    this._syncing = false;
  },

  /** Déduit le nombre de panneaux (approximatif) et le kWc (basé sur le CAPEX réel) à partir d'un budget */
  _syncNbAndKwcFromBudget(budget) {
    if (this._syncing) return;
    this._syncing = true;
    const nb  = Math.max(1, Math.round(budget / this.state.panelPrix));
    const kwc = (budget / this.CAPEX[this.state.type]).toFixed(1);
    this.state.nbPanneaux = nb;
    const nbEl  = document.getElementById('roi-nb');
    const badge = document.getElementById('roi-kwc-badge');
    if (nbEl)  nbEl.value = nb;
    if (badge) badge.textContent = `${kwc} kWc`;
    this._syncing = false;
  },

  /** Recalcule le nombre de panneaux à partir du budget courant (après changement de type de projet) */
  _recalcNbFromBudget() {
    const budgetEl = document.getElementById('roi-budget');
    if (!budgetEl) return;
    const budget = +budgetEl.value || 0;
    if (budget > 0) this._syncNbAndKwcFromBudget(budget);
  },

  // ── Chargement GHI wilaya ─────────────────────────────────────────────
  async _ensureGhi(key) {
    if (!key || this.state.ghiMap[key]) return;
    const wd = await this._get(`/wilaya/${encodeURIComponent(key)}`);
    if (wd?.data) {
      const d = wd.data;
      // Le backend renvoie le GHI annuel (kWh/m²/an) et la température moyenne (°C)
      // sous différents noms de champs selon la version du dataset.
      this.state.ghiMap[key] = {
        ghi:  +(d.ghi_annuel_kwh_m2 ?? d.ghi_annual_kwh_m2 ?? 2400),
        temp: +(d.temperature_mean ?? d.t_mean ?? d.t2m_moyen ?? d.mean_t2m ?? d.temp_avg ?? 25),
      };
    }
  },

  // ── Live update (recalcul complet si hasResult) ───────────────────────
  _liveUpdate() {
    if (!this.state.hasResult) return;
    const budgetEl = document.getElementById('roi-budget');
    const budget   = Math.max(0, +(budgetEl?.value) || 0);
    if (budget <= 0) return;
    const result = this._computeAll(budget);
    this.state._lastResult = result;
    this.state._lastBudget = budget;
    this._renderResults(budget, result);
  },

  // ── Premier calcul (bouton) ───────────────────────────────────────────
  async _calc() {
    const budgetEl = document.getElementById('roi-budget');
    const budget   = Math.max(0, +(budgetEl?.value) || 0);
    if (budget <= 0) {
      alert(this.t('roi.error.budgetRequired', 'Veuillez saisir un budget valide.'));
      return;
    }

    await this._ensureGhi(this.state.wilaya);

    const result = this._computeAll(budget);
    this.state.hasResult    = true;
    this.state._lastResult  = result;
    this.state._lastBudget  = budget;
    this._renderResults(budget, result);

    // Sauvegarde le calcul côté serveur pour permettre l'export PDF plus tard.
    // N'empêche pas l'affichage des résultats en cas d'échec.
    try {
      const resp = await this._post('/roi', {
        budget_da:      budget,
        project_type:   this.state.type,
        wilaya:         this.state.wilaya,
        inflation_rate: (this.state.inflation || 0) / 100,
      });
      if (resp && resp.history_id) {
        this.state.lastHistoryId = resp.history_id;
      }
    } catch (e) {
      console.warn('[ROI] sauvegarde POST /api/roi échouée:', e);
    }
  },

  // ── Calcul complet (formules identiques backend Python) ───────────────
  _computeAll(budget) {
    const t        = this.state.type;
    // Le kWc est dérivé de la configuration réelle de panneaux (nb × Wc)
    // afin que le ROI reflète tout changement de prix ou de quantité.
    // Si aucun panneau n'est défini, on retombe sur budget / CAPEX.
    const kwcFromPanels = (this.state.nbPanneaux * this.state.panelWc) / 1000;
    const kwcFromBudget = budget / this.CAPEX[t];
    const kwc      = kwcFromPanels > 0 ? kwcFromPanels : kwcFromBudget;
    const tar      = this.TARIF[t];
    const pr       = this.PR[t];
    const inf      = (this.state.inflation || 0) / 100;
    const opexBase = budget * this.OPEX[t];
    const key      = this.state.wilaya;
    const { ghi = 2400, temp = 25 } = this.state.ghiMap[key] || {};

    const tc  = 1 - Math.max(0, (temp - 25) * 0.0035);
    const kY1 = ghi * kwc * pr * tc;

    // Projection sur 5 ans avec dégradation annuelle des panneaux et inflation des charges
    const years = [];
    let cumul = 0;
    for (let y = 1; y <= this.YEARS; y++) {
      const prod  = kY1 * (1 - this.DEGR) ** (y - 1);
      const rev   = prod * tar;
      const opexY = opexBase * (1 + inf) ** (y - 1);
      const ncf   = rev - opexY;
      cumul += ncf;
      years.push({ y, prod, rev, opexY, ncf, cumul });
    }

    const cumul5   = years[4].cumul;
    const kwh5     = years.reduce((s, y) => s + y.prod, 0);
    const gainNet5 = cumul5 - budget;
    const roi1     = +(years[0].ncf / budget * 100).toFixed(1);
    const roi5     = +(gainNet5 / budget * 100).toFixed(1);
    const eco5     = years.reduce((s, y) => s + y.rev, 0);
    const nbPanels = Math.max(1, Math.floor(kwc * 1000 / this.state.panelWc));

    // Calcul du payback par interpolation linéaire entre les flux cumulés
    let pb = null;
    let cc = 0;
    for (let i = 0; i < years.length; i++) {
      const prev = cc;
      cc += years[i].ncf;
      if (prev < budget && cc >= budget && (cc - prev) > 0) {
        const frac = (budget - prev) / (cc - prev);
        const py   = (i + 1) + frac; // durée en années (1-based)
        const pYr  = Math.floor(py);
        let   pMo  = Math.round((py - pYr) * 12);
        if (pMo === 12) { pb = { yr: pYr + 1, mo: 0 }; }
        else             { pb = { yr: pYr,     mo: pMo }; }
        break;
      }
    }
    // Si le payback dépasse 5 ans, on extrapole de manière linéaire,
    // mais uniquement si le flux net de l'année 1 est positif.
    if (!pb && years[0].ncf > 0) {
      const py  = budget / years[0].ncf;
      const pYr = Math.floor(py);
      let   pMo = Math.round((py - pYr) * 12);
      if (pMo === 12) { pb = { yr: pYr + 1, mo: 0 }; }
      else             { pb = { yr: pYr,     mo: pMo }; }
    }
    // Si le flux net de l'année 1 est négatif ou nul, le projet n'est pas rentable
    // et le payback reste indéfini (pb = null).

    // Impact environnemental (CO2 évité, équivalences)
    const co2Y1 = +(kY1  * this.CO2K / 1000).toFixed(2);
    const co25y = +(kwh5 * this.CO2K / 1000).toFixed(1);
    const trees = Math.floor(co2Y1 * 1000 / this.TREE_KG);
    const kmCar = Math.floor(co2Y1 * 1000 / this.KM_KG);
    const hh    = Math.floor(kY1 / this.HH_KWH);

    return {
      kwc, nbPanels, kY1, kwh5, eco5, gainNet5,
      roi1, roi5, pb, years,
      co2Y1, co25y, trees, kmCar, hh,
      ghi, temp, tc,
    };
  },

  // ── Rendu des résultats ───────────────────────────────────────────────
  _renderResults(budget, r) {
    this._destroyCharts();

    const pbStr = r.pb
      ? `${r.pb.yr} ${this.t('roi.result.years', 'ans')} ${r.pb.mo} ${this.t('roi.result.months', 'mois')}`
      : this.t('roi.result.paybackNotReached', 'Non atteint sur 5 ans');

    const roi1Color  = r.roi1 > 0 ? 'color:#10b981' : 'color:#ef4444';
    const fmtDA      = n => Math.round(n).toLocaleString('fr') + ' DA';
    const fmtN       = n => Math.round(n).toLocaleString('fr');

    // Génère les lignes du tableau annuel, en mettant en évidence
    // l'année à partir de laquelle le cumul dépasse le budget initial
    const rowsHtml = r.years.map(y => {
      const green = y.cumul >= budget ? 'roi-row-green' : '';
      return `<tr class="${green}">
        <td>${y.y}</td>
        <td>${fmtN(y.prod)}</td>
        <td>${fmtN(y.rev)}</td>
        <td>${fmtN(y.opexY)}</td>
        <td>${fmtN(y.ncf)}</td>
        <td>${fmtN(y.cumul)}</td>
      </tr>`;
    }).join('');

    const exportBtn = `
      <div class="roi-actions-row">
        <button id="roi-export-pdf" class="roi-btn-export">
          📄 ${this.t('roi.result.exportPdf', 'Exporter le rapport PDF')}
        </button>
        <button id="roi-btn-rapport" class="roi-btn-rapport">
          📊 ${this.t('roi.result.generateReport', 'Générer rapport investisseur')}
        </button>
      </div>`;

    document.getElementById('roi-results').innerHTML = `
<div class="roi-results-wrap">

  <!-- KPIs principaux -->
  <div class="roi-kpis">
    <div class="roi-kpi">
      <div class="roi-kpi-val" style="${roi1Color}">${r.roi1}%</div>
      <div class="roi-kpi-lbl">${this.t('roi.result.roi1', 'ROI Année 1')}</div>
    </div>
    <div class="roi-kpi">
      <div class="roi-kpi-val">${r.roi5}%</div>
      <div class="roi-kpi-lbl">${this.t('roi.result.roi5', 'ROI 5 ans')}</div>
    </div>
    <div class="roi-kpi">
      <div class="roi-kpi-val roi-kpi-val--sm">${pbStr}</div>
      <div class="roi-kpi-lbl">${this.t('roi.result.payback', 'Retour sur investissement')}</div>
    </div>
    <div class="roi-kpi">
      <div class="roi-kpi-val roi-kpi-val--sm">${fmtDA(r.gainNet5)}</div>
      <div class="roi-kpi-lbl">${this.t('roi.result.gainNet5', 'Gain net 5 ans')}</div>
    </div>
  </div>

  <!-- Paramètres utilisés -->
  <div class="roi-params-used">
    <div class="roi-params-title">${this.t('roi.result.paramsUsed', 'Paramètres utilisés')}</div>
    <div class="roi-params-grid">
      <span>📍 ${this.state.wilaya} — <strong>${fmtN(r.ghi)} kWh/m²/an</strong></span>
      <span>⚡ ${r.kwc.toFixed(2)} kWc ${this.t('roi.result.installed', 'installés')}</span>
      <span>🔆 ${r.nbPanels} × ${this.state.panelWc} W</span>
      <span>💰 ${this.TARIF[this.state.type]} DA/kWh</span>
      <span>📈 ${this.t('roi.result.inflation', 'Inflation')} : ${this.state.inflation}%/an</span>
      <span>🌡 ${this.t('roi.result.tempAvg', 'Temp. moy.')} : ${r.temp}°C (corr. ${r.tc.toFixed(4)})</span>
    </div>
  </div>

  <!-- Tableau annuel -->
  <div class="roi-table-wrap">
    <div class="roi-section-title">${this.t('roi.result.annualTable', 'Tableau annuel (5 ans)')}</div>
    <table class="roi-table">
      <thead>
        <tr>
          <th>${this.t('roi.table.year', 'Année')}</th>
          <th>${this.t('roi.table.production', 'Production (kWh)')}</th>
          <th>${this.t('roi.table.revenue', 'Revenus (DA)')}</th>
          <th>${this.t('roi.table.opex', 'Charges (DA)')}</th>
          <th>${this.t('roi.table.netCf', 'Flux net (DA)')}</th>
          <th>${this.t('roi.table.cumul', 'Cumul (DA)')}</th>
        </tr>
      </thead>
      <tbody>${rowsHtml}</tbody>
    </table>
  </div>

  <!-- Graphiques -->
  <div class="roi-charts">
    <div class="roi-chart-box">
      <div class="roi-chart-title">${this.t('roi.chart.cashflow', 'Flux de trésorerie cumulé')}</div>
      <canvas id="roi-chart-cf"></canvas>
    </div>
    <div class="roi-chart-box">
      <div class="roi-chart-title">${this.t('roi.chart.production', 'Production annuelle')}</div>
      <canvas id="roi-chart-prod"></canvas>
    </div>
  </div>

  <!-- Impact environnemental -->
  <div class="roi-env">
    <div class="roi-section-title">🌱 ${this.t('roi.result.envImpact', 'Impact environnemental')}</div>
    <div class="roi-env-grid">
      <div class="roi-env-item">
        <div class="roi-env-val">${r.co2Y1} t</div>
        <div class="roi-env-lbl">${this.t('roi.env.co2Year', 'CO₂ évité / an')}</div>
      </div>
      <div class="roi-env-item">
        <div class="roi-env-val">${r.co25y} t</div>
        <div class="roi-env-lbl">${this.t('roi.env.co25y', 'CO₂ évité sur 5 ans')}</div>
      </div>
      <div class="roi-env-item">
        <div class="roi-env-val">${fmtN(r.trees)}</div>
        <div class="roi-env-lbl">${this.t('roi.env.trees', 'Arbres équivalents')}</div>
      </div>
      <div class="roi-env-item">
        <div class="roi-env-val">${fmtN(r.kmCar)}</div>
        <div class="roi-env-lbl">${this.t('roi.env.kmCar', 'km voiture évités')}</div>
      </div>
      <div class="roi-env-item">
        <div class="roi-env-val">${r.hh}</div>
        <div class="roi-env-lbl">${this.t('roi.env.households', 'Foyers alimentés')}</div>
      </div>
    </div>
  </div>

  ${exportBtn}
</div>`;

    this._renderCharts(budget, r);
    this._bindExportPdf();
  },

  // ── Graphiques ────────────────────────────────────────────────────────
  _renderCharts(budget, r) {
    const labels = r.years.map(y => `${this.t('roi.chart.year', 'Année')} ${y.y}`);

    // Flux de trésorerie cumulé, avec une ligne pointillée marquant le seuil de rentabilité
    const cfCtx = document.getElementById('roi-chart-cf')?.getContext('2d');
    if (cfCtx) {
      this._charts.cf = new Chart(cfCtx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: this.t('roi.chart.cumulLabel', 'Flux cumulé (DA)'),
              data: r.years.map(y => Math.round(y.cumul)),
              borderColor: '#10b981',
              backgroundColor: 'rgba(16,185,129,0.1)',
              tension: 0.3,
              fill: true,
            },
            {
              label: this.t('roi.chart.thresholdLabel', 'Seuil rentabilité (budget)'),
              data: r.years.map(() => Math.round(budget)),
              borderColor: '#f59e0b',
              borderDash: [6, 4],
              pointRadius: 0,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'top' },
            tooltip: {
              callbacks: {
                label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString('fr')} DA`,
              },
            },
          },
          scales: {
            y: { ticks: { callback: v => v.toLocaleString('fr') + ' DA' } },
          },
        },
      });
    }

    // Production annuelle estimée
    const prodCtx = document.getElementById('roi-chart-prod')?.getContext('2d');
    if (prodCtx) {
      this._charts.prod = new Chart(prodCtx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: this.t('roi.chart.prodLabel', 'Production (kWh)'),
            data: r.years.map(y => Math.round(y.prod)),
            backgroundColor: 'rgba(245,158,11,0.7)',
            borderColor: '#f59e0b',
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            y: { ticks: { callback: v => v.toLocaleString('fr') + ' kWh' } },
          },
        },
      });
    }
  },

  // ── Export PDF ────────────────────────────────────────────────────────
  _bindExportPdf() {
    document.getElementById('roi-export-pdf')?.addEventListener('click', async () => {
      // Réutilise l'historique sauvegardé lors du dernier calcul, si disponible
      let id = this.state.lastHistoryId;
      if (!id) {
        // Sinon, récupère le dernier calcul de l'historique utilisateur
        const histRes = await this._get('/roi/history');
        const history = histRes?.data ?? [];
        if (!history.length) {
          alert(this.t(
            'roi.error.noHistory',
            "Aucun calcul sauvegardé. Reconnectez-vous puis relancez le calcul."
          ));
          return;
        }
        id = history[0].id;
      }
      window.open(`${this.apiBase()}/roi/export-pdf/${id}`, '_blank');
    });

    // Envoie les résultats du calcul ROI vers la page Rapports pour générer le rapport investisseur
    document.getElementById('roi-btn-rapport')?.addEventListener('click', () => {
      if (!this.state.hasResult || !this.state._lastResult) return;

      const r      = this.state._lastResult;
      const budget = this.state._lastBudget;

      // Convertit le payback en nombre d'années décimales
      const pbYears = r.pb ? (r.pb.yr + r.pb.mo / 12) : null;

      // Format attendu par ReportsPage.extractIncomingParams()
      const navParams = {
        source:              'roi',
        wilaya:              this.state.wilaya,
        puissance_kwc:       r.kwc.toFixed(2),
        investissement_da:   budget,
        production_an1_kwh:  Math.round(r.kY1),
        economie_an1_da:     Math.round(r.years[0]?.rev ?? 0),
        payback_annees:      pbYears !== null ? pbYears.toFixed(2) : '',
        benefice_25_da:      Math.round(r.gainNet5),
        co2_tonnes_an:       r.co2Y1,
      };

      App.navigate('reports', navParams);
    });
  },

  // ── Destroy graphiques ────────────────────────────────────────────────
  _destroyCharts() {
    Object.values(this._charts).forEach(c => { try { c.destroy(); } catch {} });
    this._charts = {};
  },
};

window.ROIPage = ROIPage;