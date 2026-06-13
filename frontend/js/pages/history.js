const HistoryPage = {
  items: [],
  currentType: 'all',
  currentItem: null,

  async render(params = {}) {
    // Guard: redirect unauthenticated users before rendering
    const verified = await API.verify();
    if (!verified?.authenticated) {
      return;
    }

    const content = document.getElementById('page-content');
    content.innerHTML = `
      <div class="page-wrapper">
        ${Components.pageHeader(
          'fa-history',
          'Historique des Analyses',
          'Consultez et exportez toutes vos analyses, prévisions et calculs ROI',
          `<button class="btn btn-secondary btn-sm" onclick="HistoryPage.exportAll()">
            <i class="fas fa-download"></i> Exporter tout (JSON)
          </button>`
        )}

        <div class="card mb-5">
          <div class="card-body" style="padding:12px 20px">
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
              ${[
                { key: 'all',           label: 'Tout',                    icon: 'fa-list'       },
                { key: 'zone_analysis', label: 'Recommandations Zones',   icon: 'fa-map-pin'    },
                { key: 'forecast',      label: 'Prévisions',              icon: 'fa-chart-line' },
                { key: 'roi',           label: 'Calculs ROI',             icon: 'fa-dollar-sign'},
                { key: 'report',        label: 'Rapports',                icon: 'fa-file-pdf'   },
              ].map(t => `
                <button class="btn ${t.key === this.currentType ? 'btn-primary' : 'btn-secondary'} btn-sm"
                  id="tab-${t.key}" onclick="HistoryPage.filterType('${t.key}')">
                  <i class="fas ${t.icon}"></i> ${t.label}
                </button>
              `).join('')}
              <span style="margin-left:auto;font-size:12px;color:var(--text-muted)" id="history-count"></span>
            </div>
          </div>
        </div>

        <div id="history-list">
          <div style="text-align:center;padding:48px">
            <div style="width:28px;height:28px;border:3px solid var(--bg-elevated);border-top-color:var(--amber-400);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px"></div>
            <p style="color:var(--text-muted)">Chargement de l'historique...</p>
          </div>
        </div>

        <div id="history-detail-panel" style="display:none"></div>
      </div>
      <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
    `;

    await this.loadHistory();
  },

  async loadHistory() {
    const res = await API.getHistory(this.currentType);
    this.items = res?.data || [];
    this.renderList();
  },

  filterType(type) {
    this.currentType = type;

    // Sync active state across all filter tabs
    ['all', 'zone_analysis', 'forecast', 'roi', 'report'].forEach(t => {
      const btn = document.getElementById(`tab-${t}`);
      if (btn) {
        btn.className = `btn ${t === type ? 'btn-primary' : 'btn-secondary'} btn-sm`;
      }
    });

    this.loadHistory();
  },

  renderList() {
    const container = document.getElementById('history-list');
    const countEl   = document.getElementById('history-count');
    if (!container) return;

    if (countEl) countEl.textContent = `${this.items.length} entrée(s)`;

    // Empty state — prompt the user to create their first entry
    if (!this.items.length) {
      container.innerHTML = `
        <div class="card">
          <div class="card-body" style="text-align:center;padding:48px">
            <i class="fas fa-inbox" style="font-size:48px;color:var(--text-muted);opacity:0.4;margin-bottom:16px;display:block"></i>
            <div style="font-size:15px;font-weight:600;color:var(--text-secondary)">Aucune entrée dans l'historique</div>
            <div style="font-size:13px;color:var(--text-muted);margin-top:8px">
              Lancez une analyse de zones, une prévision ou un calcul ROI pour commencer.
            </div>
          </div>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div class="card">
        <div class="scroll-x">
          <table class="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Wilaya</th>
                <th>Détails</th>
                <th>Métriques</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${this.items.map(item => this._renderRow(item)).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  _renderRow(item) {
    // Map each history type to its visual config (icon, color, badge class)
    const typeConfig = {
      zone_analysis: { icon: 'fa-map-pin',    color: 'var(--amber-400)', label: 'Recommandation Zones', badge: 'badge-amber' },
      forecast:      { icon: 'fa-chart-line', color: 'var(--teal-400)',  label: 'Prévision IA',         badge: 'badge-teal'  },
      roi:           { icon: 'fa-dollar-sign',color: 'var(--green-400)', label: 'Calcul ROI',           badge: 'badge-green' },
      report:        { icon: 'fa-file-pdf',   color: 'var(--red-400)',   label: 'Rapport',              badge: 'badge-blue'  },
    };
    const cfg = typeConfig[item.type] || { icon: 'fa-circle', color: 'var(--text-muted)', label: item.type, badge: 'badge-gray' };

    const details = this._getDetails(item);
    const metrics = this._getMetrics(item);
    const date    = new Date(item.created_at || item.generated_at || '').toLocaleString('fr-FR');

    // Escape item JSON for safe inline onclick attribute injection
    return `
      <tr>
        <td>
          <span class="badge ${cfg.badge}">
            <i class="fas ${cfg.icon}"></i> ${cfg.label}
          </span>
        </td>
        <td style="font-weight:600">${item.wilaya_name || item.wilaya_code || '—'}</td>
        <td style="font-size:12px;color:var(--text-secondary)">${details}</td>
        <td style="font-size:12px">${metrics}</td>
        <td style="font-size:12px;color:var(--text-muted)">${date}</td>
        <td>
          <div style="display:flex;gap:6px">
            <button class="btn btn-secondary btn-sm" title="Voir détails"
              onclick="HistoryPage.showDetail(${JSON.stringify(item).replace(/"/g, '&quot;')})">
              <i class="fas fa-eye"></i>
            </button>
            <button class="btn btn-secondary btn-sm" title="Exporter JSON"
              onclick="HistoryPage.exportItem(${JSON.stringify(item).replace(/"/g, '&quot;')})">
              <i class="fas fa-download"></i>
            </button>
            <button class="btn btn-danger btn-sm" title="Supprimer"
              onclick="HistoryPage.deleteItem(${item.id}, '${item.type}')">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  },

  // Returns a human-readable summary line per history type
  _getDetails(item) {
    if (item.type === 'zone_analysis') {
      const zones = item.result?.recommended_zones?.length || 0;
      return `Capacité: <strong>${item.target_capacity_mw} MW</strong> • ${zones} zones recommandées`;
    }
    if (item.type === 'forecast') {
      return `Modèle: <strong>${item.model_id}</strong> • Variable: <strong>${item.variable}</strong> • Horizon: <strong>${item.horizon}</strong>`;
    }
    if (item.type === 'roi') {
      return `Capacité: <strong>${item.capacity_mw} MW</strong> • Scénario: <strong>${item.scenario}</strong>`;
    }
    if (item.type === 'report') {
      return `Type: <strong>${item.report_type || '—'}</strong> • Capacité: <strong>${item.capacity_mw || '—'} MW</strong>`;
    }
    return '—';
  },

  // Returns key performance metrics relevant to each history type
  _getMetrics(item) {
    if (item.type === 'forecast' && item.metrics) {
      const m = item.metrics;
      return `MAE: <strong>${m.mae?.toFixed ? m.mae.toFixed(3) : m.mae || '—'}</strong> • R²: <strong>${m.r2?.toFixed ? m.r2.toFixed(3) : m.r2 || '—'}</strong>`;
    }
    if (item.type === 'roi') {
      return `IRR: <strong>${item.irr?.toFixed ? item.irr.toFixed(1) : item.irr || '—'}%</strong> • Payback: <strong>${item.payback_years?.toFixed ? item.payback_years.toFixed(1) : item.payback_years || '—'} ans</strong>`;
    }
    if (item.type === 'zone_analysis') {
      const best = item.result?.recommended_zones?.[0];
      return best
        ? `Meilleure zone: <strong>${best.commune_name}</strong> (score: ${best.score?.toFixed ? best.score.toFixed(1) : best.score})`
        : '—';
    }
    return '—';
  },

  showDetail(item) {
    this.currentItem = item;

    // Pretty-print the full result payload for inspection
    const content = JSON.stringify(item.result || item, null, 2);

    Components.showModal(
      `Détails — ${item.type} (${item.wilaya_name || item.wilaya_code || ''})`,
      `
        <div style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap">
          ${this._getDetailBadges(item)}
        </div>
        <div style="background:var(--bg-base);border-radius:var(--radius-md);padding:16px;max-height:400px;overflow-y:auto">
          <pre style="font-size:11px;color:var(--text-secondary);white-space:pre-wrap;word-break:break-all;margin:0">${content}</pre>
        </div>
        <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end">
          <button class="btn btn-secondary btn-sm" onclick="HistoryPage.exportItem(HistoryPage.currentItem)">
            <i class="fas fa-download"></i> Exporter JSON
          </button>
          <button class="btn btn-primary btn-sm" onclick="HistoryPage.replayItem(HistoryPage.currentItem)">
            <i class="fas fa-redo"></i> Rejouer
          </button>
        </div>
      `
    );
  },

  // Builds contextual badge chips for the detail modal header
  _getDetailBadges(item) {
    const badges = [];

    if (item.wilaya_name) {
      badges.push(`<span class="badge badge-amber"><i class="fas fa-map-marker-alt"></i> ${item.wilaya_name}</span>`);
    }
    if (item.type === 'forecast') {
      badges.push(`<span class="badge badge-teal">${item.variable}</span>`);
      badges.push(`<span class="badge badge-blue">${item.horizon}</span>`);
      badges.push(`<span class="badge badge-gray">${item.model_id}</span>`);
    }
    if (item.type === 'roi') {
      badges.push(`<span class="badge badge-green">${item.capacity_mw} MW</span>`);
      badges.push(`<span class="badge badge-gray">Scénario: ${item.scenario}</span>`);
    }
    if (item.type === 'zone_analysis') {
      badges.push(`<span class="badge badge-amber">${item.target_capacity_mw} MW cible</span>`);
    }
    if (item.processing_time_ms) {
      badges.push(`<span class="badge badge-gray">${item.processing_time_ms.toFixed(0)}ms</span>`);
    }

    return badges.join('');
  },

  // Re-navigates to the originating page pre-filled with the item's parameters
  replayItem(item) {
    if (!item) return;

    if (item.type === 'forecast') {
      App.navigate('forecast', {
        wilaya:   item.wilaya_code,
        variable: item.variable,
        horizon:  item.horizon,
        model:    item.model_id,
      });
    } else if (item.type === 'roi') {
      App.navigate('roi', { wilaya: item.wilaya_name, capacity: item.capacity_mw });
    } else if (item.type === 'zone_analysis') {
      App.navigate('wilaya', { code: String(item.wilaya_code).padStart(2, '0') });
    }
  },

  exportItem(item) {
    const blob = new Blob([JSON.stringify(item, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');

    a.href     = url;
    a.download = `solardz_${item.type}_${item.id}_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();

    // Release the object URL to free memory
    URL.revokeObjectURL(url);
    Utils.toast('success', 'Export', `${item.type}_${item.id}.json téléchargé`);
  },

  async exportAll() {
    const res = await API.exportHistory('all');

    if (!res?.data) {
      Utils.toast('error', 'Erreur', 'Impossible d\'exporter l\'historique');
      return;
    }

    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');

    a.href     = url;
    a.download = `solardz_history_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();

    URL.revokeObjectURL(url);
    Utils.toast('success', 'Export complet', `${res.data.length} entrées exportées`);
  },

  async deleteItem(id, type) {
    if (!confirm('Supprimer cette entrée de l\'historique ?')) return;

    const res = await API.deleteHistoryItem(id, type);

    if (res?.status === 200 || res?.message) {
      Utils.toast('success', 'Supprimé', 'Entrée supprimée de l\'historique');
      await this.loadHistory();
    } else {
      Utils.toast('error', 'Erreur', 'Impossible de supprimer cette entrée');
    }
  },
};

window.HistoryPage = HistoryPage;