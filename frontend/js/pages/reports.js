const ReportsPage = {
  wilayas: [],
  regions: [],
  selectedReport: null,
  generating: false,
  pendingParams: {},

  reportTypes: [
    {
      id: 'investor',
      icon: 'fa-briefcase',
      title: 'Rapport Investisseur',
      shortDesc: "Analyse complète d'une wilaya pour décider d'un investissement solaire.",
      sections: [
        '1. Résumé de la zone (wilaya, climat, GHI, potentiel, score, classement)',
        '2. Potentiel solaire réel (GHI mensuel vs moyenne nationale)',
        '3. Calcul ROI détaillé (investissement, économies, payback, bénéfice 25 ans)',
        '4. Analyse des risques (climat, accès, réseau, environnement)',
        '5. Prévision de production sur 12 mois + tendance 5 ans',
        '6. Recommandation finale automatique',
      ],
      requires: ['wilaya', 'power_kwc'],
      accent: 'var(--amber-400)',
    },
    {
      id: 'government',
      icon: 'fa-university',
      title: 'Rapport Gouvernement / Institutionnel',
      shortDesc: 'Vue régionale et nationale pour les décideurs publics et institutionnels.',
      sections: [
        '1. Analyse régionale (toutes les wilayas de la région + classement intra)',
        '2. Potentiel national (Top 10 + carte régionale en tableau)',
        '3. État de l’infrastructure (distances réseau par région)',
        '4. Zones prioritaires recommandées (Top 5 justifié)',
        '5. Prévisions et tendances climatiques',
        '6. Plan d’action suggéré',
      ],
      requires: ['region'],
      accent: 'var(--blue-400)',
    },
    {
      id: 'technical',
      icon: 'fa-hard-hat',
      title: 'Perspectives Techniques',
      shortDesc: 'Spécifications équipement, dimensionnement et étude de faisabilité.',
      sections: [
        '1. Spécifications équipement recommandé (panneaux, onduleur, configuration)',
        '2. Dimensionnement (surface 6-8 m²/kWc, production estimée)',
        '3. Étude de faisabilité (score, risques, conditions)',
        '4. Contraintes identifiées et solutions techniques proposées',
      ],
      requires: ['wilaya', 'power_kwc'],
      accent: 'var(--teal-400)',
    },
  ],

  apiBase() {
    return (window.API && API.BASE_URL) ? API.BASE_URL : 'http://localhost:5000/api';
  },

  async fetchJson(endpoint) {
    try {
      const res = await fetch(`${this.apiBase()}${endpoint}`, { credentials: 'include' });
      if (!res.ok) return null;
      return await res.json();
    } catch (error) {
      console.error('ReportsPage fetch error', endpoint, error);
      return null;
    }
  },

  async render(params = {}) {
    const content = document.getElementById('page-content');
    content.innerHTML = `
      <div class="page-wrapper">
        ${Components.loading('', 'Chargement de l’espace rapports...')}
      </div>
    `;

    try {
      await this.ensureWilayasList();
      this.pendingParams = this.extractIncomingParams(params);

      // Pré-sélectionner le rapport investisseur si on arrive depuis la page ROI
      if (params.source === 'roi' || params.wilaya || params.puissance_kwc) {
        this.selectedReport = 'investor';
      }

      content.innerHTML = this.renderShell();
    } catch (error) {
      console.error('ReportsPage render error:', error);
      content.innerHTML = `
        <div class="page-wrapper">
          <div class="card" style="max-width:680px;margin:40px auto">
            <div class="card-body text-center">
              ${Components.emptyState(
                'fa-exclamation-triangle',
                'Espace rapports indisponible',
                error?.message || 'Une erreur est survenue lors du chargement.',
                `<button class="btn btn-primary" onclick="App.navigate('landing')"><i class="fas fa-home"></i> Retour à l’accueil</button>`
              )}
            </div>
          </div>
        </div>
      `;
    }
  },

  async ensureWilayasList() {
    if (this.wilayas.length) return this.wilayas;
    const res = await this.fetchJson('/wilayas');
    const data = Array.isArray(res?.data) ? res.data : [];
    if (!data.length) {
      throw new Error('Impossible de charger la liste des wilayas depuis le backend.');
    }
    this.wilayas = data
      .map(item => ({
        code: String(item.code ?? item.id ?? '').padStart(2, '0'),
        name: item.nom || item.name,
        region: item.region || '—',
      }))
      .filter(item => item.name)
      .sort((a, b) => a.name.localeCompare(b.name, 'fr'));
    this.regions = Array.from(new Set(this.wilayas.map(w => w.region))).sort();
    return this.wilayas;
  },

  extractIncomingParams(params = {}) {
    const out = { wilaya: '', region: '', power_kwc: '', roi_data: null };

    if (params.wilaya && this.wilayas.some(w => w.name === params.wilaya)) {
      out.wilaya = params.wilaya;
      const found = this.wilayas.find(w => w.name === params.wilaya);
      if (found) out.region = found.region;
    }

    if (params.region && this.regions.includes(params.region)) {
      out.region = params.region;
    }

    const power = Number(params.puissance_kwc ?? params.power_kwc);
    if (Number.isFinite(power) && power > 0) {
      out.power_kwc = power;
    }

    // Récupère les éventuelles données ROI transmises par la page Analyse ROI
    const roiCandidates = {
      investment_da: params.investissement_da,
      production_year1_kwh: params.production_an1_kwh,
      savings_year1_da: params.economie_an1_da,
      payback_years: params.payback_annees,
      net_benefit_25y_da: params.benefice_25_da,
      co2_tons_per_year: params.co2_tonnes_an,
    };
    const hasRoi = Object.values(roiCandidates).some(v => v !== undefined && v !== '');
    if (hasRoi) {
      out.roi_data = {};
      Object.entries(roiCandidates).forEach(([k, v]) => {
        const num = Number(v);
        if (Number.isFinite(num)) out.roi_data[k] = num;
      });
    }

    return out;
  },

  renderShell() {
    return `
      <div class="page-wrapper">
        ${Components.pageHeader(
          'fa-file-pdf',
          'Rapports',
          'Générez un rapport PDF basé exclusivement sur les vraies données du dataset',
          '<span class="badge badge-measured">✅ Données dataset .parquet</span>'
        )}

        ${this.renderIncomingBanner()}

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px;margin-bottom:24px">
          ${this.reportTypes.map(report => this.renderReportCard(report)).join('')}
        </div>

        <div id="report-form-container">
          ${this.selectedReport ? this.renderForm(this.selectedReport) : this.renderHint()}
        </div>
      </div>
    `;
  },

  renderIncomingBanner() {
    const p = this.pendingParams || {};
    if (!p.wilaya && !p.power_kwc && !p.roi_data) return '';
    return `
      <div class="info-panel mb-5">
        <div class="info-panel-title"><i class="fas fa-link"></i> Paramètres reçus de la page Analyse ROI</div>
        <div class="info-panel-text">
          ${p.wilaya ? `Wilaya : <strong>${this.esc(p.wilaya)}</strong>` : ''}
          ${p.power_kwc ? ` · Puissance : <strong>${Utils.formatNumber(p.power_kwc, 0)} kWc</strong>` : ''}
          ${p.roi_data ? ` · Résultats ROI réutilisés dans le rapport investisseur` : ''}
        </div>
      </div>
    `;
  },

  renderReportCard(report) {
    const isActive = this.selectedReport === report.id;
    return `
      <div class="card" style="cursor:pointer;border-top:4px solid ${report.accent};${isActive ? `box-shadow:0 0 0 2px ${report.accent}` : ''}"
           onclick="ReportsPage.selectReport('${report.id}')">
        <div class="card-body">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
            <i class="fas ${report.icon}" style="font-size:24px;color:${report.accent}"></i>
            <div style="font-size:16px;font-weight:700;color:var(--text-primary)">${this.esc(report.title)}</div>
          </div>
          <div style="font-size:13px;color:var(--text-secondary);line-height:1.6;margin-bottom:12px">
            ${this.esc(report.shortDesc)}
          </div>
          <ul style="margin:0;padding-left:18px;font-size:12px;color:var(--text-secondary);line-height:1.7">
            ${report.sections.map(line => `<li>${this.esc(line)}</li>`).join('')}
          </ul>
          <div style="margin-top:14px">
            <button class="btn ${isActive ? 'btn-primary' : 'btn-secondary'} btn-sm" onclick="event.stopPropagation();ReportsPage.selectReport('${report.id}')">
              <i class="fas fa-arrow-right"></i> ${isActive ? 'Sélectionné' : 'Choisir ce rapport'}
            </button>
          </div>
        </div>
      </div>
    `;
  },

  renderHint() {
    return `
      <div class="card">
        <div class="card-body text-center" style="padding:36px">
          <i class="fas fa-mouse-pointer" style="font-size:32px;color:var(--text-muted);margin-bottom:12px"></i>
          <div style="font-size:15px;font-weight:600;color:var(--text-primary);margin-bottom:6px">Choisissez un rapport ci-dessus</div>
          <div style="font-size:13px;color:var(--text-secondary)">Le formulaire de génération s’affiche après sélection.</div>
        </div>
      </div>
    `;
  },

  selectReport(id) {
    this.selectedReport = id;
    const container = document.getElementById('report-form-container');
    if (container) container.innerHTML = this.renderForm(id);

    // Re-render les cartes pour mettre à jour leur état visuel (sélectionné/non sélectionné)
    document.querySelectorAll('[onclick^="ReportsPage.selectReport"]').forEach(() => {});
    const cardsContainer = document.querySelector('.page-wrapper > div[style*="repeat(auto-fit"]');
    if (cardsContainer) {
      cardsContainer.innerHTML = this.reportTypes.map(report => this.renderReportCard(report)).join('');
    }
  },

  renderForm(reportId) {
    const report = this.reportTypes.find(r => r.id === reportId);
    if (!report) return '';

    const wilayaOptions = this.wilayas
      .map(item => `<option value="${this.esc(item.name)}" ${this.pendingParams.wilaya === item.name ? 'selected' : ''}>${this.esc(item.name)}</option>`)
      .join('');

    const regionOptions = this.regions
      .map(name => `<option value="${this.esc(name)}" ${this.pendingParams.region === name ? 'selected' : ''}>${this.esc(name)}</option>`)
      .join('');

    const blocks = [];

    if (report.requires.includes('wilaya')) {
      blocks.push(`
        <div>
          <label class="form-label" for="report-wilaya">Wilaya</label>
          <select id="report-wilaya" class="form-select">
            <option value="">Sélectionnez une wilaya...</option>
            ${wilayaOptions}
          </select>
        </div>
      `);
    }

    if (report.requires.includes('region')) {
      blocks.push(`
        <div>
          <label class="form-label" for="report-region">Région (ou wilaya pour déduire la région)</label>
          <select id="report-region" class="form-select">
            <option value="">Sélectionnez une région...</option>
            ${regionOptions}
          </select>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
            Vous pouvez aussi sélectionner une wilaya ci-dessous : la région sera déduite automatiquement.
          </div>
        </div>
        <div>
          <label class="form-label" for="report-region-wilaya">Wilaya (facultatif)</label>
          <select id="report-region-wilaya" class="form-select">
            <option value="">— Non précisé —</option>
            ${wilayaOptions}
          </select>
        </div>
      `);
    }

    if (report.requires.includes('power_kwc')) {
      const defaultPower = this.pendingParams.power_kwc || (reportId === 'technical' ? 250 : 100);
      blocks.push(`
        <div>
          <label class="form-label" for="report-power">Puissance projet</label>
          <div style="position:relative">
            <input id="report-power" type="number" min="1" step="1" value="${defaultPower}"
                   class="form-input" />
            <span style="position:absolute;right:12px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:12px">kWc</span>
          </div>
        </div>
      `);
    }

    return `
      <div class="card mb-5">
        <div class="card-header">
          <div class="card-title"><i class="fas fa-cogs"></i> Paramètres : ${this.esc(report.title)}</div>
          <span class="badge" style="background:${report.accent}20;color:${report.accent};border:1px solid ${report.accent}55">
            ${this.esc(report.id)}
          </span>
        </div>
        <div class="card-body">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px">
            ${blocks.join('')}
          </div>
          <div style="margin-top:20px;display:flex;gap:10px;flex-wrap:wrap">
            <button class="btn btn-primary" onclick="ReportsPage.generate('${report.id}')" id="btn-generate-${report.id}">
              <i class="fas fa-file-pdf"></i> Générer le rapport
            </button>
            <button class="btn btn-secondary" onclick="ReportsPage.cancel()">
              <i class="fas fa-times"></i> Annuler
            </button>
          </div>
          <div style="margin-top:14px;font-size:12px;color:var(--text-secondary);line-height:1.6">
            Le PDF contient strictement les sections listées sur la carte, calculées à partir
            du dataset .parquet (aucun contenu inventé).
          </div>
        </div>
      </div>
    `;
  },

  cancel() {
    this.selectedReport = null;
    const container = document.getElementById('report-form-container');
    if (container) container.innerHTML = this.renderHint();
    const cardsContainer = document.querySelector('.page-wrapper > div[style*="repeat(auto-fit"]');
    if (cardsContainer) {
      cardsContainer.innerHTML = this.reportTypes.map(report => this.renderReportCard(report)).join('');
    }
  },

  async generate(reportId) {
    if (this.generating) return;
    const report = this.reportTypes.find(r => r.id === reportId);
    if (!report) return;

    const body = { report_type: report.id };

    if (report.requires.includes('wilaya')) {
      const wilayaEl = document.getElementById('report-wilaya');
      const wilayaName = wilayaEl?.value || '';
      if (!wilayaName) {
        Utils.toast('warning', 'Wilaya requise', 'Veuillez sélectionner une wilaya.');
        return;
      }
      body.wilaya = wilayaName;
    }

    if (report.requires.includes('region')) {
      const regionEl = document.getElementById('report-region');
      const wilayaEl = document.getElementById('report-region-wilaya');
      const region = regionEl?.value || '';
      const wilayaName = wilayaEl?.value || '';
      if (!region && !wilayaName) {
        Utils.toast('warning', 'Périmètre requis', 'Veuillez choisir une région ou une wilaya.');
        return;
      }
      if (region) body.region = region;
      if (wilayaName) body.wilaya = wilayaName;
    }

    if (report.requires.includes('power_kwc')) {
      const powerEl = document.getElementById('report-power');
      const power = Number(powerEl?.value);
      if (!(Number.isFinite(power) && power > 0)) {
        Utils.toast('warning', 'Puissance invalide', 'Veuillez saisir une puissance projet en kWc.');
        return;
      }
      body.power_kwc = power;
    }

    if (this.pendingParams.roi_data && report.id === 'investor') {
      body.roi_data = this.pendingParams.roi_data;
    }

    body.title = `${report.title} — ${body.wilaya || body.region || 'Algérie'}`;

    const btn = document.getElementById(`btn-generate-${report.id}`);
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Génération en cours...`;
    }
    this.generating = true;

    try {
      const url = `${this.apiBase()}/reports/generate`;
      const token = sessionStorage.getItem('auth_token');
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch(url, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody?.error || `Erreur backend (${response.status})`);
      }

      const blob = await response.blob();
      const filename = this.buildFilename(report.id, body);
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);

      Utils.toast('success', 'Rapport prêt', `${filename} téléchargé.`);
    } catch (error) {
      console.error('ReportsPage generate error:', error);
      Utils.toast('error', 'Génération impossible', error?.message || 'Erreur inconnue.');
    } finally {
      this.generating = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<i class="fas fa-file-pdf"></i> Générer le rapport`;
      }
    }
  },

  buildFilename(reportId, body) {
    const slug = (s) => String(s || '')
      .toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'algeria';
    const today = new Date().toISOString().slice(0, 10);
    const scope = body.wilaya || body.region || 'algerie';
    return `solardecide_${reportId}_${slug(scope)}_${today}.pdf`;
  },

  esc(value) {
    const el = document.createElement('div');
    el.textContent = value ?? '';
    return el.innerHTML;
  },
};

window.ReportsPage = ReportsPage;