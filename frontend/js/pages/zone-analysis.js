const ZoneAnalysisPage = {
  selectedWilaya: null, selectedCommune: null,
  analysis: null, monthly: null, wilayaStats: null,
  wilayasList: [], communesList: [], charts: {}, leafletMap: null,
  topNeighbor: null,

  getState() { return { wilaya: this.selectedWilaya, commune: this.selectedCommune }; },
  _t(k, f = '') { return (typeof I18N !== 'undefined' && I18N.t) ? (I18N.t(k) || f) : f; },
  _safe(v) { if (v === null || v === undefined) return '—'; return String(v).replace(/</g, '&lt;'); },
  isFree() { return (window.Plan && Plan.getPlan && Plan.getPlan() === 'free'); },

  /* ─────────────────────── RENDU PRINCIPAL ─────────────────────── */
  async render(params = {}, restoreState = {}) {
    const content = document.getElementById('page-content');
    content.innerHTML = `<div class="page-wrapper">${Components.loading('', this._t('common.loading', 'Chargement…'))}</div>`;
    this.selectedWilaya = params.wilaya || restoreState.wilaya || null;
    this.selectedCommune = params.commune || restoreState.commune || null;
    this.destroyVisuals();
    try {
      this.wilayasList = await DataService.getWilayas();
      content.innerHTML = this.template();
      this.bindForm();
      if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();
      if (this.selectedWilaya && this.selectedCommune) {
        await this.loadCommunes(this.selectedWilaya);
        await this.runAnalysis();
      } else if (this.selectedWilaya) {
        await this.loadCommunes(this.selectedWilaya);
      }
    } catch (e) {
      console.error('[zone-analysis]', e);
      content.innerHTML = `<div class="page-wrapper"><div class="card" style="max-width:640px;margin:40px auto"><div class="card-body text-center">
        <i class="fas fa-exclamation-triangle" style="font-size:42px;color:#f59e0b"></i>
        <h3 style="margin-top:14px;color:var(--text-primary)">${this._t('zone.title', 'Analyse de zone')}</h3>
        <p style="color:var(--text-secondary)">${e.message || ''}</p>
        <button class="btn btn-primary" onclick="App.navigate('landing')">${this._t('common.back', 'Retour')}</button>
      </div></div></div>`;
    }
  },

  /* ─────────────────────── FORMULAIRE DE SÉLECTION ─────────────────────── */
  template() {
    const t = (k, f = '') => this._t(k, f);
    const free = this.isFree();
    return `<div class="page-wrapper zone-analysis">
      <div class="page-header" style="margin-bottom:18px">
        <h1 style="margin:0;color:var(--text-primary)">
          <i class="fas fa-map-marker-alt" style="color:#f59e0b"></i>
          <span data-i18n="zone.title">${t('zone.title', 'Analyse de Zone')}</span>
        </h1>
        <p style="color:var(--text-secondary)" data-i18n="zone.subtitle">${t('zone.subtitle', 'Sélectionnez une wilaya puis une commune pour lancer l\'analyse')}</p>
      </div>
      ${free ? `<div style="background:rgba(245,158,11,0.12);border-left:4px solid #f59e0b;padding:14px 16px;border-radius:6px;margin-bottom:18px;display:flex;gap:12px;align-items:center">
        <i class="fas fa-lock" style="color:#f59e0b;font-size:20px"></i>
        <div style="flex:1"><strong style="color:#f59e0b">${t('zone.free_locked_banner', 'Analyse de zone réservée aux abonnés Pro')}</strong></div>
        <button class="btn btn-warning btn-sm" onclick="App.navigate('pricing')"><i class="fas fa-rocket"></i> <span>${t('zone.free_locked_cta', 'Upgrader')}</span></button>
      </div>` : ''}
      <div class="card" style="margin-bottom:18px"><div class="card-body">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;align-items:end">
          <div>
            <label style="display:block;font-size:13px;color:var(--text-secondary);font-weight:500;margin-bottom:4px">${t('zone.select_wilaya', 'Wilaya')}</label>
            <select id="za-wilaya" class="form-control">
              <option value="">${t('zone.choose_wilaya', '— Choisir une wilaya —')}</option>
              ${(this.wilayasList || []).map(w => { const n = w.name || w.wilaya_name; return `<option value="${this._safe(n)}" ${n === this.selectedWilaya ? 'selected' : ''}>${this._safe(n)}</option>`; }).join('')}
            </select>
          </div>
          <div>
            <label style="display:block;font-size:13px;color:var(--text-secondary);font-weight:500;margin-bottom:4px">${t('zone.select_commune', 'Commune')}</label>
            <select id="za-commune" class="form-control" ${this.communesList.length === 0 ? 'disabled' : ''}>
              <option value="">${t('zone.choose_commune', '— Choisir une commune —')}</option>
              ${(this.communesList || []).map(c => `<option value="${this._safe(c)}" ${c === this.selectedCommune ? 'selected' : ''}>${this._safe(c)}</option>`).join('')}
            </select>
          </div>
          <div>
            <button id="za-run" class="btn ${free ? 'btn-disabled' : 'btn-primary'}" ${free ? 'disabled' : ''}>
              <i class="fas fa-play"></i>
              <span data-i18n="zone.run_analysis">${t('zone.run_analysis', 'Lancer l\'analyse')}</span>
            </button>
          </div>
        </div>
      </div></div>
      <div id="za-results"></div>
    </div>`;
  },

  /* ─────────────────────── ÉVÉNEMENTS DU FORMULAIRE ─────────────────────── */
  bindForm() {
    const wSel = document.getElementById('za-wilaya');
    const cSel = document.getElementById('za-commune');
    const runBtn = document.getElementById('za-run');
    if (wSel) wSel.onchange = async () => { this.selectedWilaya = wSel.value || null; this.selectedCommune = null; await this.loadCommunes(this.selectedWilaya); };
    if (cSel) cSel.onchange = () => { this.selectedCommune = cSel.value || null; };
    if (runBtn && !this.isFree()) runBtn.onclick = () => this.runAnalysis();
  },

  async loadCommunes(wilaya) {
    const cSel = document.getElementById('za-commune');
    if (!wilaya) {
      this.communesList = [];
      if (cSel) { cSel.innerHTML = `<option value="">${this._t('zone.choose_commune', '— Commune —')}</option>`; cSel.disabled = true; }
      return;
    }
    try {
      const cs = await DataService.getCommunes(wilaya);
      this.communesList = cs || [];
      if (cSel) {
        cSel.disabled = false;
        cSel.innerHTML = `<option value="">${this._t('zone.choose_commune', '— Commune —')}</option>` +
          this.communesList.map(c => `<option value="${this._safe(c)}" ${c === this.selectedCommune ? 'selected' : ''}>${this._safe(c)}</option>`).join('');
      }
    } catch (e) { console.error('loadCommunes', e); }
  },

  /* ─────────────────────── LANCEMENT DE L'ANALYSE ─────────────────────── */
  async runAnalysis() {
    if (this.isFree()) { App.navigate('pricing'); return; }
    if (!this.selectedWilaya || !this.selectedCommune) {
      if (window.Components?.toast) Components.toast(this._t('zone.choose_commune', 'Veuillez sélectionner une commune'), 'warning');
      return;
    }
    const results = document.getElementById('za-results');
    if (results) results.innerHTML = Components.loading('', this._t('common.loading', 'Chargement…'));
    try {
      this.destroyVisuals();
      this.topNeighbor = null;

      const [analysis, monthly, wstats] = await Promise.all([
        DataService.getCommuneAnalysis(this.selectedWilaya, this.selectedCommune),
        DataService.getCommuneMonthly(this.selectedWilaya, this.selectedCommune),
        DataService.getWilayaStats(this.selectedWilaya),
      ]);
      if (!analysis) throw new Error('Commune inconnue : ' + this.selectedCommune);
      this.analysis = analysis;
      this.monthly = monthly;
      this.wilayaStats = wstats;

      // Cherche dans la même wilaya une commune avec un meilleur score que la commune sélectionnée
      try {
        const ranking = await DataService.getWilayaCommunes
          ? await DataService.getWilayaCommunes(this.selectedWilaya)
          : null;
        if (ranking && Array.isArray(ranking)) {
          const sorted = ranking
            .filter(c => (c.commune_name || c.name) !== this.selectedCommune && Number(c.score_commune || c.score || 0) > Number(analysis.score_commune || 0))
            .sort((a, b) => Number(b.score_commune || b.score || 0) - Number(a.score_commune || a.score || 0));
          this.topNeighbor = sorted[0] || null;
        }
      } catch (_) { this.topNeighbor = null; }

      results.innerHTML = this.resultTemplate();
      if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();
      await this.initVisuals();
      this.attachActions();
    } catch (e) {
      console.error(e);
      results.innerHTML = `<div style="padding:14px;background:rgba(239,68,68,0.12);color:#fca5a5;border-left:4px solid #ef4444;border-radius:6px">
        <i class="fas fa-times-circle"></i> ${e.message || 'Erreur'}</div>`;
    }
  },

  /* ─────────────────────── TEMPLATE DES RÉSULTATS ─────────────────────── */
  resultTemplate() {
    const a = this.analysis || {}, w = this.wilayaStats || {};
    const t = (k, f = '') => this._t(k, f);
    const tech = this.computeTechnicalParameters();
    const risks = this.computeRisks();
    const extra = this.computeExtraIndicators();
    const isFree = this.isFree();
    const maturity = this.computeMaturity(a, risks);

    return `
    <!-- ROW 1 : Carte + Score + Risques -->
    <div style="display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:18px;margin-bottom:18px">
      <!-- Carte -->
      <div class="card">
        <div class="card-header" style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">
          <h3 style="margin:0;color:var(--text-primary)"><i class="fas fa-map-marked-alt" style="color:#3b82f6"></i> ${t('zone.map.title', 'Carte de la zone sélectionnée')}</h3>
          <div style="display:flex;gap:8px;align-items:center">
            ${maturity.badge}
            <span style="padding:3px 8px;border-radius:10px;background:rgba(16,185,129,0.15);color:#10b981;font-size:11px;font-weight:600">✅ Dataset live</span>
          </div>
        </div>
        <div id="zone-map" style="height:380px;background:var(--bg-secondary);border-radius:0 0 8px 8px"></div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 14px;border-top:1px solid var(--border-color);background:var(--bg-elevated);border-radius:0 0 8px 8px">
          <div style="font-size:12px;color:var(--text-secondary)">Wilaya : <strong style="color:var(--text-primary)">${this._safe(a.wilaya_name)}</strong> · Commune : <strong style="color:var(--text-primary)">${this._safe(a.commune_name)}</strong></div>
          <div style="font-size:12px;color:var(--text-secondary)">
            GPS : <strong style="color:#f59e0b">${a.latitude && a.longitude ? `${Number(a.latitude).toFixed(5)}, ${Number(a.longitude).toFixed(5)}` : '—'}</strong>
            · GHI ${Number(a.ghi_annuel_kwh_m2 || 0).toFixed(2)} kWh/m²/an
          </div>
        </div>
      </div>

      <!-- Score + Risques -->
      <div style="display:flex;flex-direction:column;gap:14px">
        <div class="card">
          <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
            <h3 style="margin:0;color:var(--text-primary)"><i class="fas fa-star" style="color:#10b981"></i> ${t('zone.score.title', 'Score composite (local)')}</h3>
            <span style="font-family:'Space Grotesk',Inter,sans-serif;font-size:26px;font-weight:800;color:${this._scoreColor(a.score_commune)}">${Number(a.score_commune || 0).toFixed(2)}</span>
          </div>
          <div class="card-body">${this.renderScoreBlock(a)}</div>
        </div>
        <div class="card">
          <div class="card-header"><h3 style="margin:0;color:var(--text-primary)"><i class="fas fa-shield-alt" style="color:#ef4444"></i> ${t('zone.risk.title', 'Indicateurs de risque')}</h3></div>
          <div class="card-body">${this.renderRiskBlock(risks)}</div>
        </div>
      </div>
    </div>

    <!-- ROW 2 : Pourquoi + Paramètres techniques -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
      <!-- Pourquoi cette zone -->
      <div class="card">
        <div class="card-header"><h3 style="margin:0;color:var(--text-primary)"><i class="fas fa-comment-dots" style="color:#3b82f6"></i> ${t('zone.why.title', 'Pourquoi cette zone')}</h3></div>
        <div class="card-body">
          <p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:var(--text-secondary)">${this._safe(a.why_this_zone)}</p>
          <div style="display:flex;flex-direction:column;gap:8px">
            ${this.renderWhyZone(risks).map(text => `<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 12px;background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:6px">
              <i class="fas fa-check-circle" style="color:#10b981;margin-top:3px;font-size:12px"></i>
              <div style="font-size:13px;color:var(--text-secondary);line-height:1.5">${this._safe(text)}</div></div>`).join('')}
          </div>
          <div style="margin-top:14px;background:rgba(59,130,246,0.1);border-left:4px solid #3b82f6;padding:12px 14px;border-radius:4px">
            <strong style="color:#93c5fd">${t('zone.why.panel_reco', 'Recommandation panneaux')}</strong>
            <div style="margin-top:6px;color:var(--text-secondary);font-size:13px">${this._safe(a.panel_recommendation)}</div>
          </div>
        </div>
      </div>

      <!-- Paramètres techniques enrichis -->
      <div class="card">
        <div class="card-header" style="display:flex;align-items:center;justify-content:space-between">
          <h3 style="margin:0;color:var(--text-primary)"><i class="fas fa-solar-panel" style="color:#f59e0b"></i> ${t('zone.tech.title', 'Paramètres techniques')}</h3>
          <span style="padding:3px 8px;background:rgba(59,130,246,0.15);color:#93c5fd;border-radius:10px;font-size:11px;font-weight:600">${t('zone.tech.badge', 'Estimatif standard')}</span>
        </div>
        <div class="card-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 16px">
            <div>
              ${this._tp(t('zone.tech.surface', 'Surface recommandée'), `${tech.surface_m2.toLocaleString('fr-FR')} m²`, '#f59e0b')}
              ${this._tp(t('zone.tech.kwc', 'Puissance installable'), `${tech.power_kwc.toLocaleString('fr-FR')} kWc`, '#10b981')}
              ${this._tp(t('zone.tech.annual_mwh', 'Production annuelle'), `${tech.annual_mwh.toFixed(1)} MWh/an`, '#3b82f6')}
            </div>
            <div>
              ${this._tp('Peak Sun Hours (PSH)', `${extra.psh.toFixed(2)} h/j`, '#a855f7')}
              ${this._tp(t('zone.tech.ghi', 'GHI annuel'), `${Number(a.ghi_annuel_kwh_m2 || 0).toFixed(2)} kWh/m²/an`)}
              ${this._tp('Performance Ratio', '0.80')}
            </div>
          </div>
          <!-- Distance réseau bien visible -->
          <div style="margin-top:12px;padding:10px 14px;border-radius:6px;background:${risks.reseau.level === 'low' ? 'rgba(16,185,129,0.1)' : risks.reseau.level === 'medium' ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)'};border:1px solid ${risks.reseau.level === 'low' ? 'rgba(16,185,129,0.3)' : risks.reseau.level === 'medium' ? 'rgba(245,158,11,0.3)' : 'rgba(239,68,68,0.3)'}">
            <div style="display:flex;align-items:center;gap:8px">
              <i class="fas fa-plug" style="color:${risks.reseau.level === 'low' ? '#10b981' : risks.reseau.level === 'medium' ? '#f59e0b' : '#ef4444'}"></i>
              <span style="font-size:12px;font-weight:600;color:var(--text-primary)">Distance estimée au réseau électrique</span>
              <span style="font-size:14px;font-weight:800;color:${risks.reseau.level === 'low' ? '#10b981' : risks.reseau.level === 'medium' ? '#f59e0b' : '#ef4444'}">${risks.reseau.value}</span>
              ${this.renderRiskBadge(risks.reseau.level)}
            </div>
            <div style="font-size:11px;color:var(--text-secondary);margin-top:4px">${risks.reseau.detail}</div>
          </div>
          <div style="margin-top:10px;padding:10px;border-radius:6px;background:var(--bg-elevated);border:1px solid var(--border-color);font-size:11px;color:var(--text-secondary);line-height:1.6">
            <strong style="color:var(--text-primary)">Formules :</strong> puissance = surface/7 · production = GHI × kWc × 0,8 / 1000 · PSH = GHI annuel ÷ 365 ÷ 1
          </div>
        </div>
      </div>
    </div>

    <!-- ROW 4 : Paramètres dataset + Synthèse GPS -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
      <div class="card">
        <div class="card-header"><h3 style="margin:0;color:var(--text-primary)"><i class="fas fa-microscope" style="color:#6366f1"></i> ${t('zone.tech.dataset_title', 'Paramètres dataset (commune)')}</h3></div>
        <div class="card-body">
          ${this._dr('GHI annuel', Number(a.ghi_annuel_kwh_m2 || 0).toFixed(2), 'kWh/m²/an')}
          ${this._dr('DNI moyen', Number(a.dni_moyen || 0).toFixed(3), 'kWh/m²/h')}
          ${this._dr('Température moy.', Number(a.t2m_moyen || 0).toFixed(2), '°C')}
          ${this._dr('Temp. max', Number(a.t2m_max || 0).toFixed(2), '°C')}
          ${this._dr('Vent moyen', Number(a.vent_moyen_m_s || 0).toFixed(2), 'm/s')}
          ${this._dr('Humidité', Number(a.rh2m_moyen || 0).toFixed(1), '%')}
          ${this._dr('Indice de clarté (Kt)', Number(a.clearness_kt_moyen || 0).toFixed(3), '')}
          ${this._dr('Précipitations', Number(a.precip_mm_moyen || 0).toFixed(3), 'mm/h')}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><h3 style="margin:0;color:var(--text-primary)"><i class="fas fa-info-circle" style="color:#0ea5e9"></i> ${t('zone.summary.title', 'Synthèse & Localisation')}</h3></div>
        <div class="card-body">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
            ${this._sc('GHI annuel', Number(a.ghi_annuel_kwh_m2 || 0).toFixed(2), 'kWh/m²/an', '#f59e0b')}
            ${this._sc('Peak Sun Hours', extra.psh.toFixed(2) + ' h/j', 'Ensoleillement utile/jour', '#a855f7')}
            ${this._sc('Score composite', Number(a.score_commune || 0).toFixed(2), '/100', this._scoreColor(a.score_commune))}
            ${this._sc('Coordonnées GPS', a.latitude && a.longitude ? `${Number(a.latitude).toFixed(5)}` : '—', a.longitude ? `${Number(a.longitude).toFixed(5)}` : '', '#6366f1')}
          </div>
          <div style="margin-top:12px;padding:10px 14px;border-radius:6px;background:var(--bg-elevated);border:1px solid var(--border-color)">
            <div style="font-size:11px;color:var(--text-secondary);margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em">Localisation précise</div>
            <div style="font-size:13px;color:var(--text-primary)">
              <i class="fas fa-map-pin" style="color:#f59e0b;margin-right:6px"></i>
              <strong>${this._safe(a.commune_name)}</strong>, ${this._safe(a.wilaya_name)}
            </div>
            ${a.latitude && a.longitude ? `
            <div style="font-size:12px;color:var(--text-secondary);margin-top:4px">
              Latitude : <strong style="color:var(--text-primary)">${Number(a.latitude).toFixed(5)}°N</strong>
              &nbsp;·&nbsp; Longitude : <strong style="color:var(--text-primary)">${Number(a.longitude).toFixed(5)}°E</strong>
            </div>
            <a href="https://maps.google.com/?q=${Number(a.latitude).toFixed(5)},${Number(a.longitude).toFixed(5)}" target="_blank"
              style="display:inline-block;margin-top:6px;font-size:11px;color:#3b82f6;text-decoration:none">
              <i class="fas fa-external-link-alt"></i> Ouvrir dans Google Maps
            </a>` : ''}
          </div>
        </div>
      </div>
    </div>

    <!-- LIEN ROI : bouton de transition vers la page ROI pré-remplie -->
    <div style="margin-bottom:18px">
      <div class="card" style="border:1px solid rgba(16,185,129,0.35);background:rgba(16,185,129,0.06)">
        <div class="card-body" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;padding:16px 20px">
          <div>
            <div style="font-size:14px;font-weight:700;color:var(--text-primary)">
              <i class="fas fa-calculator" style="color:#10b981;margin-right:8px"></i>
              Calculer le ROI pour cette zone
            </div>
            <div style="font-size:12px;color:var(--text-secondary);margin-top:4px">
              Wilaya : <strong style="color:var(--text-primary)">${this._safe(a.wilaya_name)}</strong>
              &nbsp;·&nbsp; Puissance : <strong style="color:#10b981">${tech.power_kwc} kWc</strong>
              &nbsp;·&nbsp; GHI : <strong style="color:#f59e0b">${Number(a.ghi_annuel_kwh_m2||0).toFixed(2)} kWh/m²/an</strong>
              &nbsp;·&nbsp; Production : <strong style="color:#3b82f6">${tech.annual_mwh.toFixed(1)} MWh/an</strong>
            </div>
            <div style="font-size:11px;color:var(--text-secondary);margin-top:3px">
              Ces données seront automatiquement pré-remplies dans le formulaire ROI.
            </div>
          </div>
          <button class="btn btn-primary" style="white-space:nowrap;min-width:180px" onclick="ZoneAnalysisPage.goToROI()">
            <i class="fas fa-arrow-right"></i>&nbsp; Aller au calcul ROI
          </button>
        </div>
      </div>
    </div>

    <!-- ROW 6 : Graphiques production + Comparaison GHI -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
      <div class="card">
        <div class="card-header">
          <h3 style="margin:0;color:var(--text-primary)">${t('zone.chart.production', 'Production mensuelle estimée')}</h3>
          <small style="color:var(--text-secondary)">${t('zone.chart.production_desc', 'MWh/mois')}</small>
        </div>
        <div class="card-body"><canvas id="za-chart-prod" height="220"></canvas></div>
      </div>
      <div class="card">
        <div class="card-header">
          <h3 style="margin:0;color:var(--text-primary)">${t('zone.chart.compare', 'Ensoleillement : commune vs national')}</h3>
          <small style="color:var(--text-secondary)">${t('zone.chart.compare_desc', 'GHI mensuel kWh/m²/mois')}</small>
        </div>
        <div class="card-body"><canvas id="za-chart-cmp" height="220"></canvas></div>
      </div>
    </div>

    <!-- ROW 7 : Actions finales -->
    <div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin:24px 0">
      <button id="za-report-btn" class="btn ${isFree ? 'btn-disabled' : 'btn-warning'}" ${isFree ? 'disabled' : ''}>
        <i class="fas fa-file-pdf"></i> Générer le rapport investisseur
      </button>
      <button id="za-save-btn" class="btn ${isFree ? 'btn-disabled' : 'btn-success'}" ${isFree ? 'disabled' : ''}>
        <i class="fas fa-save"></i> <span>${t('zone.save_analysis', 'Sauvegarder l\'analyse')}</span>
      </button>
      <button class="btn btn-secondary" onclick="App.navigate('comparison')">
        <i class="fas fa-exchange-alt"></i> Comparer des sites
      </button>
    </div>`;
  },

  /* ─────────────────────── TABLEAU DES SURFACES PAR PUISSANCE ─────────────────────── */
  renderSurfaceTable(a, tech) {
    const ghi = Number(a.ghi_annuel_kwh_m2 || tech.annual_mwh / (tech.power_kwc * 0.8 / 1000) || 5.8);
    const PR = 0.80;
    const powers = [50, 100, 500]; // kWc
    // Prix marché algérien 2024 : ~135 000 DZD/kWc (fourniture + pose + onduleur)
    const CAPEX_DZD_KWC = 135000;
    const rows = powers.map(pkwc => {
      const surf = Math.round(pkwc * 7);
      const mwh = Number(((ghi * pkwc * PR) / 1000).toFixed(1));
      const capex_dzd = Math.round(pkwc * CAPEX_DZD_KWC);
      return { pkwc, surf, mwh, capex_dzd };
    });
    const headerStyle = `padding:10px 14px;background:var(--bg-elevated);font-size:11px;font-weight:700;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em;text-align:left;border-bottom:1px solid var(--border-color)`;
    const cellStyle = `padding:10px 14px;font-size:13px;color:var(--text-primary);border-bottom:1px solid var(--border-color)`;
    const hlStyle = `padding:10px 14px;font-size:13px;font-weight:700;border-bottom:1px solid var(--border-color)`;
    return `<table style="width:100%;border-collapse:collapse">
      <thead><tr>
        <th style="${headerStyle}">Puissance</th>
        <th style="${headerStyle}">Surface min.</th>
        <th style="${headerStyle}">Production/an</th>
        <th style="${headerStyle}">CAPEX estimé</th>
      </tr></thead>
      <tbody>
        ${rows.map((r, i) => `<tr style="${i === 1 ? 'background:rgba(245,158,11,0.06)' : ''}">
          <td style="${hlStyle}color:${i === 0 ? '#10b981' : i === 1 ? '#f59e0b' : '#3b82f6'}">${r.pkwc} kWc</td>
          <td style="${cellStyle}">${r.surf.toLocaleString('fr-FR')} m²</td>
          <td style="${cellStyle}">${r.mwh.toFixed(1)} MWh/an</td>
          <td style="${cellStyle}">${(r.capex_dzd/1000000).toFixed(2)} M DZD</td>
        </tr>`).join('')}
      </tbody>
    </table>
    <div style="padding:10px 14px;font-size:11px;color:var(--text-secondary)">
      Surface = kWc × 7 m² · CAPEX ~135 000 DZD/kWc (marché algérien 2024) · Production = GHI × kWc × 0,8 / 1000
    </div>`;
  },

  /* ─────────────────────── ANALYSE SAISONNIÈRE ─────────────────────── */
  renderSeasonalAnalysis(extra) {
    const months = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'];
    const { bestMonthIdx, worstMonthIdx, monthlyGhi, stableMonths } = extra.seasonal;
    const maxGhi = Math.max(...monthlyGhi);
    return `
    <div style="margin-bottom:12px">
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
        <div style="padding:8px 14px;border-radius:6px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3)">
          <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em">Mois optimal démarrage</div>
          <div style="font-size:16px;font-weight:700;color:#10b981"><i class="fas fa-sun"></i> ${months[bestMonthIdx]}</div>
          <div style="font-size:11px;color:var(--text-secondary)">GHI max : ${Number(monthlyGhi[bestMonthIdx] || 0).toFixed(1)} kWh/m²</div>
        </div>
        <div style="padding:8px 14px;border-radius:6px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2)">
          <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em">Mois le plus faible</div>
          <div style="font-size:16px;font-weight:700;color:#f87171"><i class="fas fa-cloud"></i> ${months[worstMonthIdx]}</div>
          <div style="font-size:11px;color:var(--text-secondary)">GHI min : ${Number(monthlyGhi[worstMonthIdx] || 0).toFixed(1)} kWh/m²</div>
        </div>
        <div style="padding:8px 14px;border-radius:6px;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.2)">
          <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em">Mois stables (GHI &gt; 80%)</div>
          <div style="font-size:16px;font-weight:700;color:#93c5fd">${stableMonths} / 12</div>
          <div style="font-size:11px;color:var(--text-secondary)">Fiabilité production</div>
        </div>
      </div>
      <!-- Mini barchart saisonnier -->
      <div style="display:flex;align-items:flex-end;gap:3px;height:50px;padding:4px 0">
        ${monthlyGhi.map((v, i) => {
          const pct = maxGhi > 0 ? (v / maxGhi) * 100 : 0;
          const isB = i === bestMonthIdx, isW = i === worstMonthIdx;
          const col = isB ? '#10b981' : isW ? '#ef4444' : '#3b82f6';
          return `<div title="${months[i]}: ${Number(v).toFixed(1)} kWh/m²" style="flex:1;height:${Math.max(4, pct)}%;background:${col};border-radius:2px 2px 0 0;opacity:${isB || isW ? 1 : 0.6};transition:opacity .2s"></div>`;
        }).join('')}
      </div>
      <div style="display:flex;gap:3px;margin-top:2px">
        ${months.map((m, i) => `<div style="flex:1;text-align:center;font-size:9px;color:${i === bestMonthIdx ? '#10b981' : i === worstMonthIdx ? '#ef4444' : 'var(--text-secondary)'};font-weight:${i === bestMonthIdx || i === worstMonthIdx ? '700' : '400'}">${m.substring(0, 1)}</div>`).join('')}
      </div>
    </div>
    <div style="font-size:12px;color:var(--text-secondary);padding:8px 10px;background:var(--bg-elevated);border-radius:6px;border:1px solid var(--border-color)">
      <i class="fas fa-lightbulb" style="color:#f59e0b"></i>
      Conseil : démarrer le chantier en <strong style="color:var(--text-primary)">${months[Math.max(0, bestMonthIdx - 2)]}</strong>
      pour être opérationnel avant le pic d'ensoleillement de <strong style="color:#10b981">${months[bestMonthIdx]}</strong>.
    </div>`;
  },

  /* ─────────────────────── MATURITÉ DU PROJET ─────────────────────── */
  computeMaturity(a, risks) {
    const score = Number(a.score_commune || 0);
    let level, label, color, icon;
    if (score >= 70 && risks.reseau.level !== 'high' && risks.climatique.level !== 'high') {
      level = 'feasible'; label = 'Faisable'; color = '#10b981'; icon = 'fa-check-circle';
    } else if (score >= 45) {
      level = 'study'; label = 'À étudier'; color = '#f59e0b'; icon = 'fa-search';
    } else {
      level = 'risky'; label = 'Risqué'; color = '#ef4444'; icon = 'fa-exclamation-triangle';
    }
    const badge = `<span style="padding:4px 12px;border-radius:20px;background:${level === 'feasible' ? 'rgba(16,185,129,0.15)' : level === 'study' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)'};color:${color};font-size:12px;font-weight:700;border:1px solid ${color}40">
      <i class="fas ${icon}"></i> ${label}
    </span>`;
    return { level, label, color, badge };
  },

  /* ─────────────────────── BLOC SCORE ─────────────────────── */
  renderScoreBlock(a) {
    const ghiNorm = this._normalizeGhi(Number(a.ghi_annuel_kwh_m2 || 0));
    const stab = Number(a.stabilite_pct || 0);
    const kt = Number(a.clearness_kt_moyen || 0) * 100;
    const cv = Number(a.risque_cv || 0);
    const riskInv = Math.max(0, Math.min(100, (1 - cv) * 100));
    const rows = [
      { label: 'GHI normalisé', weight: '40 %', value: ghiNorm, color: '#f59e0b' },
      { label: 'Stabilité climatique', weight: '20 %', value: stab, color: '#10b981' },
      { label: 'Indice de clarté (KT)', weight: '20 %', value: kt, color: '#3b82f6' },
      { label: 'Risque inverse', weight: '20 %', value: riskInv, color: '#ef4444' },
    ];
    return rows.map(r => `<div style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:8px">
        <div style="font-size:13px;color:var(--text-primary);font-weight:600">${this._safe(r.label)}</div>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="background:var(--bg-elevated);color:var(--text-secondary);font-size:11px;padding:2px 7px;border-radius:10px;font-weight:600">${r.weight}</span>
          <span style="font-size:12px;font-weight:700;color:${r.color}">${Number(r.value).toFixed(1)}/100</span>
        </div>
      </div>
      <div style="width:100%;height:7px;background:var(--bg-elevated);border-radius:4px;overflow:hidden">
        <div style="width:${Math.max(0, Math.min(100, Number(r.value) || 0))}%;height:100%;background:${r.color};transition:width .4s ease"></div>
      </div>
    </div>`).join('');
  },
  _normalizeGhi(g) { const lo = 4.0, hi = 8.0; return Math.max(0, Math.min(100, ((g - lo) / (hi - lo)) * 100)); },
  _scoreColor(s) { s = Number(s) || 0; if (s >= 75) return '#10b981'; if (s >= 55) return '#3b82f6'; if (s >= 35) return '#f59e0b'; return '#ef4444'; },
  _riskLevelFromScore(inv) { const s = Number(inv); if (!Number.isFinite(s)) return 'unavailable'; const r = 100 - s; if (r < 33) return 'low'; if (r <= 66) return 'medium'; return 'high'; },

  /* ─────────────────────── INDICATEURS DE RISQUE ─────────────────────── */
  computeRisks() {
    const a = this.analysis || {}, w = this.wilayaStats || {};
    const stab = Number(a.stabilite_pct ?? NaN);
    const climateLevel = Number.isFinite(stab) ? this._riskLevelFromScore(stab) : 'unavailable';
    const scoreLocal = Number(a.score_commune ?? NaN);
    const compositeLevel = Number.isFinite(scoreLocal) ? this._riskLevelFromScore(scoreLocal) : 'unavailable';
    const lat = Number(a.latitude ?? w.latitude ?? NaN);
    const gridDist = Number.isFinite(lat) ? Math.max(0, (36.5 - lat) * 40) : NaN;
    const gridLevel = Number.isFinite(gridDist) ? (gridDist < 100 ? 'low' : gridDist <= 250 ? 'medium' : 'high') : 'unavailable';
    return {
      climatique: {
        label: 'Stabilité climatique', level: climateLevel,
        value: Number.isFinite(stab) ? `${stab.toFixed(1)}/100` : '—',
        detail: Number.isFinite(stab) ? `Score stabilité (CV journalier GHI) : ${stab.toFixed(1)}/100` : 'Indisponible'
      },
      composite: {
        label: 'Risque composite (inversé)', level: compositeLevel,
        value: Number.isFinite(scoreLocal) ? `${(100 - scoreLocal).toFixed(1)} % risque` : '—',
        detail: Number.isFinite(scoreLocal) ? `Score local : ${scoreLocal.toFixed(1)}/100` : 'Score indispo'
      },
      reseau: {
        label: 'Risque réseau', level: gridLevel,
        value: Number.isFinite(gridDist) ? `~${gridDist.toFixed(0)} km` : '—',
        detail: Number.isFinite(gridDist) ? `Distance proxy réseau (latitude-based) : ~${gridDist.toFixed(0)} km du nord algérien.` : 'Distance non calculable'
      },
      stabilityScore: stab, scoreLocal, gridDistance: gridDist,
    };
  },

  renderRiskBlock(risks) {
    const cards = [risks.climatique, risks.composite, risks.reseau];
    return `<div style="display:flex;flex-direction:column;gap:10px">${cards.map(c => `<div style="padding:12px;border-radius:6px;background:var(--bg-elevated);border:1px solid var(--border-color)">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px">
        <div style="font-size:13px;font-weight:600;color:var(--text-primary)">${this._safe(c.label)}</div>
        ${this.renderRiskBadge(c.level)}
      </div>
      <div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px">${this._safe(c.detail)}</div>
      <div style="font-size:12px;color:var(--text-primary);font-weight:600">${this._safe(c.value)}</div>
    </div>`).join('')}</div>`;
  },
  renderRiskBadge(lvl) {
    const map = {
      low: ['rgba(16,185,129,0.15)', '#10b981', 'Faible'],
      medium: ['rgba(245,158,11,0.15)', '#f59e0b', 'Moyen'],
      high: ['rgba(239,68,68,0.15)', '#ef4444', 'Élevé'],
      unavailable: ['rgba(156,163,175,0.15)', '#9ca3af', 'N/A']
    };
    const [bg, fg, l] = map[lvl] || map.unavailable;
    return `<span style="background:${bg};color:${fg};font-size:11px;padding:3px 9px;border-radius:10px;font-weight:600">${l}</span>`;
  },

  renderWhyZone(risks) {
    const a = this.analysis || {};
    const ghi = Number(a.ghi_annuel_kwh_m2 || 0), score = Number(a.score_commune || 0), wind = Number(a.vent_moyen_m_s || 0);
    const r = [];
    if (ghi > 6.5) r.push(`Rayonnement solaire exceptionnel (${ghi.toFixed(2)} kWh/m²/an).`);
    else if (ghi > 5.5) r.push(`Très bon GHI annuel (${ghi.toFixed(2)} kWh/m²/an).`);
    else if (ghi > 4.5) r.push(`Niveau d'irradiation correct (${ghi.toFixed(2)} kWh/m²/an).`);
    if (wind > 0 && wind < 4.5) r.push(`Faible vitesse du vent (${wind.toFixed(2)} m/s), favorable aux installations.`);
    else if (wind >= 4.5) r.push(`Vent moyen ${wind.toFixed(2)} m/s : ancrages renforcés recommandés.`);
    if (score > 75) r.push(`Excellent score composite local (${score.toFixed(2)}/100).`);
    else if (score > 55) r.push(`Potentiel solide (score ${score.toFixed(2)}/100).`);
    else r.push(`Potentiel modéré (score ${score.toFixed(2)}/100), analyse terrain conseillée.`);
    if (risks.climatique.level === 'low') r.push('Variabilité climatique maîtrisée.');
    else if (risks.climatique.level === 'medium') r.push('Variabilité climatique modérée à intégrer dans le dimensionnement.');
    else if (risks.climatique.level === 'high') r.push('Forte variabilité climatique : prévoir surdimensionnement.');
    if (risks.reseau.level === 'low') r.push('Proximité relative du réseau électrique : risque de raccordement faible.');
    else if (risks.reseau.level === 'medium') r.push('Distance réseau modérée : étude de raccordement recommandée.');
    else if (risks.reseau.level === 'high') r.push('Éloignement marqué du réseau, peut impacter le coût total.');
    if (!r.length) r.push('Données dataset à confirmer par étude terrain.');
    return r;
  },

  /* ─────────────────────── PARAMÈTRES TECHNIQUES ─────────────────────── */
  computeTechnicalParameters() {
    const a = this.analysis || {}, w = this.wilayaStats || {};
    const ghi = Number(a.ghi_annuel_kwh_m2 || 0), natRef = 5.8;
    const ratio = natRef > 0 ? ghi / natRef : 1;
    const surface_m2 = Math.max(7000, Math.min(15000, Math.round(10000 * ratio)));
    const power_kwc = Math.round(surface_m2 / 7);
    const PR = 0.80;
    const annual_mwh = Number(((ghi * power_kwc * PR) / 1000).toFixed(1));
    const monthlyGhi = (this.monthly && Array.isArray(this.monthly.ghi_commune)) ? this.monthly.ghi_commune : Array(12).fill(ghi / 12);
    const monthly_mwh = monthlyGhi.map(g => Number(((Number(g || 0) * power_kwc * PR) / 1000).toFixed(2)));
    const potentialMw = Number(w.potentiel_mw || 0);
    const map_potential_mwh = Number((ghi * potentialMw * PR).toFixed(0));
    return { surface_m2, power_kwc, annual_mwh, monthly_mwh, map_potential_mwh };
  },

  /* ─────────────────────── INDICATEURS COMPLÉMENTAIRES ─────────────────────── */
  computeExtraIndicators() {
    const a = this.analysis || {};
    const ghi = Number(a.ghi_annuel_kwh_m2 || 0);
    // Peak Sun Hours : GHI annuel / 365 (heures utiles par jour)
    const psh = ghi > 0 ? ghi / 365 : 0;

    // Analyse saisonnière : identifie les mois extrêmes et les mois stables
    const rawMonthly = (this.monthly && Array.isArray(this.monthly.ghi_commune))
      ? this.monthly.ghi_commune
      : Array(12).fill(ghi / 12);
    const monthlyGhi = rawMonthly.map(v => Number(v || 0));
    const maxGhi = Math.max(...monthlyGhi);
    const minGhi = Math.min(...monthlyGhi);
    const bestMonthIdx = monthlyGhi.indexOf(maxGhi);
    const worstMonthIdx = monthlyGhi.indexOf(minGhi);
    const threshold = maxGhi * 0.80;
    const stableMonths = monthlyGhi.filter(v => v >= threshold).length;

    return {
      psh,
      seasonal: { bestMonthIdx, worstMonthIdx, monthlyGhi, stableMonths, maxGhi }
    };
  },

  /* ─────────────────────── CARTE & GRAPHIQUES ─────────────────────── */
  async initVisuals() { await new Promise(r => setTimeout(r, 50)); this.initMap(); this.initCharts(); },
  destroyVisuals() {
    Object.values(this.charts || {}).forEach(c => { try { c.destroy(); } catch (_) { } });
    this.charts = {};
    if (this.leafletMap) { try { this.leafletMap.remove(); } catch (_) { } this.leafletMap = null; }
  },

  initMap() {
    const el = document.getElementById('zone-map');
    if (!el || typeof L === 'undefined' || !this.analysis) return;
    const a = this.analysis, w = this.wilayaStats || {}, tech = this.computeTechnicalParameters();
    const lat = Number(a.latitude ?? w.latitude ?? 28);
    const lon = Number(a.longitude ?? w.longitude ?? 2.6);
    this.leafletMap = L.map('zone-map', { center: [lat, lon], zoom: 9, scrollWheelZoom: false });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap', maxZoom: 18 }).addTo(this.leafletMap);
    const score = Number(a.score_commune || 0), color = this._scoreColor(score);

    if (Number.isFinite(Number(w.latitude)) && Number.isFinite(Number(w.longitude))) {
      const wM = L.circleMarker([Number(w.latitude), Number(w.longitude)], { radius: 14, fillColor: '#3b82f6', color: '#fff', weight: 3, fillOpacity: 0.6 }).addTo(this.leafletMap);
      wM.bindPopup(`<div style="min-width:220px;color:var(--text-primary)">
        <div style="font-weight:700;margin-bottom:6px">${this._safe(w.wilaya_name)} (wilaya)</div>
        <div style="font-size:12px;line-height:1.7">
          <div>GHI annuel : <strong>${Number(w.ghi_annuel_kwh_m2 || 0).toFixed(2)}</strong> kWh/m²/an</div>
          <div>Potentiel wilaya : <strong>${Number(w.potentiel_mw || 0).toFixed(1)}</strong> MW</div>
          <div>Score : <strong>${Number(w.score_composite || 0).toFixed(2)}</strong>/100</div>
        </div></div>`);
    }

    const cM = L.circleMarker([lat, lon], { radius: 10, fillColor: color, color: '#fff', weight: 3, fillOpacity: 0.95 }).addTo(this.leafletMap);
    cM.bindPopup(`<div style="min-width:260px;color:var(--text-primary)">
      <div style="font-weight:700;margin-bottom:6px;font-size:14px">${this._safe(a.commune_name)}</div>
      <div style="font-size:12px;line-height:1.7">
        <div>Wilaya : <strong>${this._safe(a.wilaya_name)}</strong></div>
        <div>Climat : <strong>${this._safe(a.climate || '—')}</strong></div>
        <div>GHI annuel : <strong>${Number(a.ghi_annuel_kwh_m2 || 0).toFixed(2)}</strong> kWh/m²/an</div>
        <div>Score local : <strong>${Number(a.score_commune || 0).toFixed(2)}</strong>/100</div>
        <div>Surface conseillée : <strong>${tech.surface_m2.toLocaleString('fr-FR')}</strong> m²</div>
        <div>Production estimée : <strong>${tech.annual_mwh.toFixed(1)}</strong> MWh/an</div>
        <div style="margin-top:6px;padding-top:6px;border-top:1px solid #e2e8f0">
          <span style="color:#666">Latitude :</span> <strong>${Number(a.latitude).toFixed(5)}°N</strong><br>
          <span style="color:#666">Longitude :</span> <strong>${Number(a.longitude).toFixed(5)}°E</strong>
        </div>
      </div></div>`).openPopup();
    setTimeout(() => { try { this.leafletMap.invalidateSize(); } catch (_) { } }, 200);
  },

  initCharts() {
    if (typeof Chart === 'undefined' || !this.monthly) return;
    Object.values(this.charts || {}).forEach(c => { try { c.destroy(); } catch (_) { } });
    this.charts = {};
    const labels = this.monthly.labels || ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'];
    const tech = this.computeTechnicalParameters();
    const gridCol = 'rgba(255,255,255,0.06)';
    const tickCol = '#9ca3af';

    const pCtx = document.getElementById('za-chart-prod');
    if (pCtx && tech.monthly_mwh.length === 12) {
      this.charts.prod = new Chart(pCtx, {
        type: 'bar',
        data: { labels, datasets: [{ label: 'MWh/mois', data: tech.monthly_mwh, backgroundColor: 'rgba(16,185,129,0.75)', borderColor: '#10b981', borderWidth: 1 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.parsed.y.toFixed(2)} MWh` } } },
          scales: {
            y: { beginAtZero: true, title: { display: true, text: 'MWh', color: tickCol }, ticks: { color: tickCol }, grid: { color: gridCol } },
            x: { ticks: { color: tickCol }, grid: { color: gridCol } }
          }
        }
      });
    }
    const cCtx = document.getElementById('za-chart-cmp');
    if (cCtx && this.monthly.ghi_commune && this.monthly.ghi_national) {
      this.charts.cmp = new Chart(cCtx, {
        type: 'line',
        data: {
          labels, datasets: [
            { label: `Commune (${this.analysis?.commune_name || ''})`, data: this.monthly.ghi_commune, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,.2)', tension: .3, fill: true, pointRadius: 3 },
            { label: 'Moyenne nationale', data: this.monthly.ghi_national, borderColor: '#3b82f6', backgroundColor: 'transparent', borderDash: [6, 4], tension: .3, fill: false, pointRadius: 2 },
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom', labels: { color: tickCol } } },
          scales: {
            y: { beginAtZero: true, title: { display: true, text: 'kWh/m²/mois', color: tickCol }, ticks: { color: tickCol }, grid: { color: gridCol } },
            x: { ticks: { color: tickCol }, grid: { color: gridCol } }
          }
        }
      });
    }
  },

  /* ─────────────────────── ACTIONS ─────────────────────── */
  attachActions() {
    const s = document.getElementById('za-save-btn');
    if (s && !this.isFree()) s.onclick = () => this.saveAnalysis();
    const r = document.getElementById('za-report-btn');
    if (r && !this.isFree()) r.onclick = () => this.goToReport();
  },

  goToROI() {
    if (!this.analysis) return;
    const a = this.analysis;
    const tech = this.computeTechnicalParameters();
    // Sauvegarde les données dans sessionStorage pour que la page ROI les récupère au chargement
    const roiPrefill = {
      wilaya: a.wilaya_name,
      commune: a.commune_name,
      puissance_kwc: tech.power_kwc,
      surface_m2: tech.surface_m2,
      ghi: Number(a.ghi_annuel_kwh_m2 || 0).toFixed(2),
      annual_mwh: tech.annual_mwh,
      score: Number(a.score_commune || 0).toFixed(2),
      latitude: a.latitude,
      longitude: a.longitude,
      source: 'zone-analysis',
    };
    try { sessionStorage.setItem('roi_prefill', JSON.stringify(roiPrefill)); } catch (_) {}
    App.navigate('roi', roiPrefill);
  },

  goToReport() {
    if (!this.analysis) return;
    const tech = this.computeTechnicalParameters();
    App.navigate('reports', {
      wilaya: this.analysis.wilaya_name,
      commune: this.analysis.commune_name,
      power_kwc: tech.power_kwc,
      ghi: Number(this.analysis.ghi_annuel_kwh_m2 || 0).toFixed(2),
      score: Number(this.analysis.score_commune || 0).toFixed(2),
      source: 'zone',
    });
  },

  async saveAnalysis() {
    if (window.PlanGate && PlanGate.require) { const ok = await PlanGate.require('action.save_analysis', 'pro'); if (!ok) return; }
    else if (this.isFree()) { App.navigate('pricing'); return; }
    if (!this.analysis) return;
    try {
      const res = await DataService.saveAnalysis({ wilaya: this.analysis.wilaya_name, commune: this.analysis.commune_name, score: this.analysis.score_commune, ghi: this.analysis.ghi_annuel_kwh_m2 });
      if ((res.status === 201 || res.status === 200) && res.data) { if (window.Components?.toast) Components.toast(this._t('zone.saved_ok', 'Analyse sauvegardée'), 'success'); }
      else if (res.status === 401) App.navigate('login');
      else if (res.status === 402) App.navigate('pricing');
      else { if (window.Components?.toast) Components.toast(this._t('zone.save_failed', 'Échec'), 'error'); }
    } catch (e) { console.error(e); if (window.Components?.toast) Components.toast(this._t('zone.save_failed', 'Échec'), 'error'); }
  },

  /* ─────────────────────── HELPERS D'AFFICHAGE ─────────────────────── */
  _tp(label, value, color = 'var(--text-primary)') {
    return `<div style="margin-bottom:10px">
      <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em">${this._safe(label)}</div>
      <div style="font-size:16px;font-weight:700;color:${color}">${this._safe(value)}</div>
    </div>`;
  },
  _dr(label, value, unit = '') {
    return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px dashed var(--border-color)">
      <span style="font-size:13px;color:var(--text-secondary)">${this._safe(label)}</span>
      <strong style="color:var(--text-primary)">${this._safe(value)}${unit ? ' ' + unit : ''}</strong>
    </div>`;
  },
  _sc(label, value, sub, color) {
    return `<div style="padding:12px;border-radius:6px;background:var(--bg-elevated);border:1px solid var(--border-color)">
      <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em">${this._safe(label)}</div>
      <div style="font-size:18px;font-weight:700;color:${color}">${this._safe(value)}</div>
      ${sub ? `<div style="font-size:11px;color:var(--text-secondary)">${this._safe(sub)}</div>` : ''}
    </div>`;
  },
  _kpi(label, value, color) {
    return `<div style="padding:10px 12px;border-radius:6px;background:var(--bg-elevated);border:1px solid var(--border-color)">
      <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px">${this._safe(label)}</div>
      <div style="font-size:15px;font-weight:700;color:${color}">${this._safe(value)}</div>
    </div>`;
  },
};
window.ZoneAnalysisPage = ZoneAnalysisPage;
window.ZoneAnalysis = ZoneAnalysisPage;