const OfflinePage = {
  packs: [],

  async render() {
    const content = document.getElementById('page-content');
    content.innerHTML = Components.loading(null, 'Chargement du centre hors-ligne...');

    const res            = await API.getOfflinePacks();
    this.packs           = res?.data || [];
    const pendingCount   = await OfflineSync.getPendingCount();
    const pendingActions = await OfflineSync.getPending();
    const downloaded     = this.packs.filter(p => p.status === 'downloaded');
    const totalSizeMB    = downloaded.reduce((s, p) => s + (p.size_mb || 0), 0);

    content.innerHTML = `
      <div class="page-wrapper">
        ${Components.pageHeader(
          'fa-wifi',
          'Centre Hors-Ligne',
          'Téléchargez les packs de données pour une utilisation en zone isolée (Sahara, terrain)',
          `<div class="connection-badge ${navigator.onLine ? 'online' : 'offline'}" id="conn-badge">
             ${navigator.onLine ? '🟢 En ligne' : '🔴 Hors ligne'}
           </div>
           <button class="btn btn-primary btn-sm" onclick="OfflinePage.syncAll()">
             <i class="fas fa-sync"></i> Synchroniser (<span id="offline-pending-count">${pendingCount}</span>)
           </button>`
        )}

        <div class="kpi-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:24px">
          ${Components.kpiCard({ icon:'fa-download', iconClass:'green',  label:'Packs téléchargés',  value: downloaded.length,  sub:`/${this.packs.length} disponibles` })}
          ${Components.kpiCard({ icon:'fa-hdd',      iconClass:'blue',   label:'Stockage utilisé',   value:`${totalSizeMB} MB`, sub:'IndexedDB local' })}
          ${Components.kpiCard({ icon:'fa-clock',    iconClass:'amber',  label:'Actions en attente', value: pendingCount,       sub:'Seront rejouées en ligne', colorClass: pendingCount > 0 ? 'amber' : '' })}
          ${Components.kpiCard({ icon:'fa-satellite-dish', iconClass:'teal', label:'Connexion',      value: navigator.onLine ? 'En ligne' : 'Hors ligne', sub: navigator.onLine ? 'Sync disponible' : 'Mode déconnecté', colorClass:'teal' })}
        </div>

        <div class="card mb-5">
          <div class="card-header">
            <div class="card-title"><i class="fas fa-satellite-dish"></i> État de Synchronisation</div>
          </div>
          <div class="card-body">
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px">
              <div style="background:var(--bg-elevated);border-radius:var(--radius-md);padding:16px">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted);margin-bottom:8px">Connexion réseau</div>
                <div style="font-size:20px;font-weight:700;color:${navigator.onLine ? 'var(--green-400)' : 'var(--red-400)'}">
                  <i class="fas ${navigator.onLine ? 'fa-wifi' : 'fa-wifi-slash'}"></i>
                  ${navigator.onLine ? 'En ligne' : 'Hors ligne'}
                </div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
                  ${navigator.onLine ? 'Synchronisation automatique active' : 'Sync au retour de connexion'}
                </div>
              </div>
              <div style="background:var(--bg-elevated);border-radius:var(--radius-md);padding:16px">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted);margin-bottom:8px">Actions en file</div>
                <div style="font-size:28px;font-weight:700;color:${pendingCount > 0 ? 'var(--amber-400)' : 'var(--green-400)'};font-family:'Space Grotesk'" id="offline-pending-count-big">${pendingCount}</div>
                <div style="font-size:11px;color:var(--text-muted)">analyses / prévisions / ROI</div>
              </div>
              <div style="background:var(--bg-elevated);border-radius:var(--radius-md);padding:16px">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted);margin-bottom:8px">Stockage IndexedDB</div>
                <div style="font-size:20px;font-weight:700;color:var(--teal-400);font-family:'Space Grotesk'">${totalSizeMB} MB</div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:4px">Packs téléchargés</div>
              </div>
            </div>
          </div>
        </div>

        ${pendingActions.length > 0 ? `
        <div class="card mb-5">
          <div class="card-header">
            <div class="card-title"><i class="fas fa-list-ul"></i> File d'Actions en Attente</div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-primary btn-sm" onclick="OfflinePage.syncAll()">
                <i class="fas fa-play"></i> Rejouer tout
              </button>
              <button class="btn btn-danger btn-sm" onclick="OfflinePage.clearQueue()">
                <i class="fas fa-trash"></i> Vider
              </button>
            </div>
          </div>
          <div class="scroll-x">
            <table class="data-table">
              <thead><tr><th>#</th><th>Endpoint</th><th>Méthode</th><th>Date</th><th>Tentatives</th></tr></thead>
              <tbody>
                ${pendingActions.map(a => `
                  <tr>
                    <td>${a.id}</td>
                    <td style="font-size:12px;font-family:monospace">${a.endpoint}</td>
                    <td><span class="badge badge-teal">${a.method}</span></td>
                    <td style="font-size:12px">${new Date(a.timestamp).toLocaleString('fr-FR')}</td>
                    <td>${a.retries || 0}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
        ` : ''}

        <div class="card mb-5">
          <div class="card-header">
            <div class="card-title"><i class="fas fa-archive"></i> Packs de Données Disponibles</div>
          </div>
          <div class="card-body">
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">
              ${this.packs.map(p => this._renderPack(p)).join('')}
            </div>
          </div>
        </div>

        <div class="card mb-5">
          <div class="card-header">
            <div class="card-title"><i class="fas fa-mobile-alt"></i> Fonctionnalités Hors-Ligne</div>
          </div>
          <div class="card-body">
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px">
              ${[
                { icon:'fa-map',              label:'Cartes topographiques',  desc:'Tuiles OpenStreetMap cachées localement'    },
                { icon:'fa-chart-line',        label:'Prévisions hors-ligne',  desc:'Modèles ML chargés depuis checkpoints'      },
                { icon:'fa-database',          label:'Données historiques',    desc:'IndexedDB — données Parquet locales'        },
                { icon:'fa-cloud-upload-alt',  label:'Sync différée',          desc:'Actions rejouées au retour en ligne'        },
                { icon:'fa-history',           label:'Historique local',       desc:'Analyses sauvegardées en base SQLite'       },
              ].map(f => `
                <div style="display:flex;align-items:center;gap:10px;padding:12px;background:var(--bg-elevated);border-radius:var(--radius-md)">
                  <div class="kpi-icon green" style="width:32px;height:32px;font-size:14px">
                    <i class="fas ${f.icon}"></i>
                  </div>
                  <div style="flex:1">
                    <div style="font-size:13px;font-weight:600">${f.label}</div>
                    <div style="font-size:11px;color:var(--text-muted)">${f.desc}</div>
                  </div>
                  <span class="badge badge-green">✅</span>
                </div>
              `).join('')}
            </div>
          </div>
        </div>

        <div class="info-panel">
          <div class="info-panel-title"><i class="fas fa-info-circle"></i> Comment fonctionne le mode hors-ligne</div>
          <div class="info-panel-text">
            1. Téléchargez les packs des wilayas que vous allez visiter (Wi-Fi recommandé)<br>
            2. Toutes les analyses, prévisions et calculs ROI effectués hors-ligne sont mis en file d'attente<br>
            3. À votre retour en zone connectée, la synchronisation se déclenche automatiquement<br>
            4. L'historique complet reste accessible même sans connexion
          </div>
        </div>
      </div>
    `;

    // Keep the connection badge in sync with real-time network events
    window.addEventListener('online',  () => this._updateConnBadge(true));
    window.addEventListener('offline', () => this._updateConnBadge(false));
  },

  _renderPack(p) {
    const isDownloaded = p.status === 'downloaded';
    return `
      <div style="background:var(--bg-elevated);border-radius:var(--radius-md);padding:16px;border:1px solid ${isDownloaded ? 'rgba(34,197,94,0.3)' : 'var(--border-color)'}">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
          <div class="kpi-icon ${isDownloaded ? 'green' : 'amber'}" style="width:36px;height:36px;font-size:16px">
            <i class="fas ${isDownloaded ? 'fa-check-circle' : 'fa-archive'}"></i>
          </div>
          <div>
            <div style="font-size:14px;font-weight:700">${p.name}</div>
            <div style="font-size:11px;color:var(--text-muted)">${p.size_mb} MB • ${p.wilayas || 0} wilayas</div>
          </div>
          <span class="badge ${isDownloaded ? 'badge-green' : 'badge-amber'}" style="margin-left:auto">
            ${isDownloaded ? '✅ Téléchargé' : '⬇️ Disponible'}
          </span>
        </div>
        <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;line-height:1.5">${p.description}</p>
        ${p.downloaded_at ? `<div style="font-size:10px;color:var(--text-muted);margin-bottom:8px">Téléchargé le ${p.downloaded_at}</div>` : ''}
        <button class="btn ${isDownloaded ? 'btn-secondary' : 'btn-primary'} btn-sm w-full"
          onclick="OfflinePage.downloadPack('${p.id}', '${p.name}')">
          <i class="fas ${isDownloaded ? 'fa-sync' : 'fa-download'}"></i>
          ${isDownloaded ? 'Mettre à jour' : 'Télécharger'}
        </button>
      </div>
    `;
  },

  async downloadPack(packId, name) {
    Utils.toast('info', `Téléchargement: ${name}`, 'En cours...');
    const res = await API.downloadPack(packId);
    if (res?.data) {
      Utils.toast('success', 'Pack téléchargé!', `${name} disponible hors-ligne`);
      await this.render();
    } else {
      Utils.toast('error', 'Erreur', 'Téléchargement échoué');
    }
  },

  async syncAll() {
    Utils.toast('info', 'Synchronisation', 'Envoi des actions en attente...');
    const result = await API.syncPendingActions();

    if (result.synced > 0) {
      Utils.toast('success', 'Synchronisation réussie', `${result.synced} action(s) synchronisée(s)`);
    } else if (result.failed > 0) {
      Utils.toast('warning', 'Sync partielle', `${result.failed} action(s) échouée(s)`);
    } else {
      Utils.toast('info', 'Rien à synchroniser', 'File d\'attente vide');
    }

    await this.render();
  },

  async clearQueue() {
    if (!confirm('Vider la file d\'attente ? Les actions non synchronisées seront perdues.')) return;
    await OfflineSync.clearAll();
    Utils.toast('success', 'File vidée', 'Toutes les actions en attente ont été supprimées');
    await this.render();
  },

  // Reflects live network status changes in the header badge without a full re-render
  _updateConnBadge(online) {
    const badge = document.getElementById('conn-badge');
    if (badge) {
      badge.className  = `connection-badge ${online ? 'online' : 'offline'}`;
      badge.textContent = online ? '🟢 En ligne' : '🔴 Hors ligne';
    }
  },
};

window.OfflinePage = OfflinePage;