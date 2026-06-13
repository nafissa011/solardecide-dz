const AdminUsersPage = {
  // Cached user list, total count, and active filter state
  _users: [],
  _total: 0,
  _filter: { plan: 'all', search: '' },

  // Resolves a translation key with an optional fallback string
  _t(k, f = '') {
    return (typeof I18N !== 'undefined' && I18N.t) ? (I18N.t(k) || f) : f;
  },

  // Renders the loading skeleton then triggers the initial data fetch
  async render() {
    document.getElementById('page-content').innerHTML =
      `<div class="page-wrapper">${Components.loading('', 'Chargement des utilisateurs…')}</div>`;
    await this._load();
  },

  // Fetches the filtered user list, rebuilds the page, and re-binds all interactions
  async _load() {
    this._users = await DataService.adminListUsers(this._filter) || [];
    this._total = this._users.length;
    document.getElementById('page-content').innerHTML = this._template();
    if (typeof I18N !== 'undefined' && I18N.applyDom) I18N.applyDom();
    this._bindFilters();
    this._bindRowActions();
  },

  // Builds the full page HTML: header, filter bar, users table, action legend, and styles
  _template() {

    // Returns a colour-coded pill badge for the user's subscription plan
    const planBadge = u => {
      const map = {
        free:       { bg: 'rgba(107,114,128,.15)', color: 'var(--text-muted)',  label: 'Free' },
        pro:        { bg: 'rgba(20,184,166,.15)',  color: 'var(--teal-400)',    label: 'Pro' },
        enterprise: { bg: 'rgba(245,158,11,.15)',  color: 'var(--amber-400)',   label: 'Enterprise' },
      };
      const s = map[u.plan] || map.free;
      return `<span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;background:${s.bg};color:${s.color}">${s.label}</span>`;
    };

    // Returns a green "Actif" or red "Inactif" pill based on the account status
    const statusBadge = u => u.is_active
      ? `<span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;background:rgba(34,197,94,.12);color:var(--green-400);border:1px solid rgba(34,197,94,.25)">Actif</span>`
      : `<span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;background:rgba(239,68,68,.12);color:var(--red-400);border:1px solid rgba(239,68,68,.25)">Inactif</span>`;

    // Returns a purple "admin" badge; empty string for regular users
    const roleBadge = u => u.role === 'admin'
      ? `<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;background:rgba(139,92,246,.15);color:var(--purple-500);margin-left:4px">admin</span>`
      : '';

    // Date helpers: date-only and date+time, both localised to French
    const fmtDate = iso => iso ? new Date(iso).toLocaleDateString('fr') : '—';
    const fmtDT   = iso => iso ? new Date(iso).toLocaleString('fr', { dateStyle: 'short', timeStyle: 'short' }) : '—';

    // One table row per user; admin accounts have no delete button to prevent accidental removal
    const rows = this._users.map(u => `
      <tr data-uid="${u.id}" class="adm-user-row${u.is_active ? '' : ' row-inactive'}">
        <td style="font-family:monospace;font-size:12px;color:var(--text-muted)">#${u.id}</td>
        <td>
          <span style="color:var(--text-primary);font-weight:600">${this._esc(u.name)}</span>
          ${roleBadge(u)}
        </td>
        <td style="font-family:monospace;font-size:12px;color:var(--text-secondary)">${this._esc(u.email)}</td>
        <td>
          <div style="display:flex;align-items:center;gap:6px">
            ${planBadge(u)}
            <select class="adm-plan-sel" data-action="select-plan"
                    style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:6px;color:var(--text-primary);font-size:12px;padding:3px 6px">
              <option value="free"       ${u.plan === 'free'       ? 'selected' : ''}>Free</option>
              <option value="pro"        ${u.plan === 'pro'        ? 'selected' : ''}>Pro</option>
              <option value="enterprise" ${u.plan === 'enterprise' ? 'selected' : ''}>Enterprise</option>
            </select>
          </div>
        </td>
        <td style="text-align:center;color:var(--text-primary);font-weight:600">${u.analyses_month}</td>
        <td style="text-align:center;color:var(--text-primary);font-weight:600">${u.reports_month}</td>
        <td style="color:var(--text-secondary);font-size:12px">${fmtDate(u.created_at)}</td>
        <td style="color:var(--text-secondary);font-size:12px">${fmtDT(u.last_login)}</td>
        <td>${statusBadge(u)}</td>
        <td style="white-space:nowrap">
          <div style="display:flex;gap:4px;align-items:center">
            <button class="adm-act-btn adm-act-apply" data-action="apply-plan"
                    title="Appliquer le plan sélectionné">
              <i class="fas fa-check"></i>
            </button>
            <button class="adm-act-btn ${u.is_active ? 'adm-act-deactivate' : 'adm-act-activate'}"
                    data-action="toggle"
                    title="${u.is_active ? 'Désactiver le compte' : 'Activer le compte'}">
              <i class="fas fa-power-off"></i>
            </button>
            ${u.role !== 'admin' ? `
            <button class="adm-act-btn adm-act-delete" data-action="delete"
                    title="Supprimer l'utilisateur">
              <i class="fas fa-trash"></i>
            </button>` : `<span style="width:28px"></span>`}
          </div>
        </td>
      </tr>`).join('') ||
      `<tr><td colspan="10" style="padding:28px;text-align:center;color:var(--text-muted)">
        <i class="fas fa-users" style="font-size:24px;display:block;margin-bottom:8px"></i>
        Aucun utilisateur trouvé
      </td></tr>`;

    return `
<div class="page-wrapper">

  <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin-bottom:22px">
    <div>
      <h1 style="margin:0;color:var(--text-primary)">
        <i class="fas fa-users" style="color:var(--amber-400)"></i>
        Gérer les utilisateurs
      </h1>
      <p style="margin:4px 0 0;color:var(--text-muted);font-size:13px">
        ${this._total} utilisateur${this._total > 1 ? 's' : ''} trouvé${this._total > 1 ? 's' : ''}
      </p>
    </div>
  </div>

  <!-- Filter bar: plan dropdown and name/email search -->
  <div class="card" style="margin-bottom:16px">
    <div class="card-body" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;padding:16px">
      <div>
        <label class="form-label">Filtrer par plan</label>
        <select id="adm-flt-plan" class="form-control">
          <option value="all"        ${this._filter.plan === 'all'        ? 'selected' : ''}>Tous les plans</option>
          <option value="free"       ${this._filter.plan === 'free'       ? 'selected' : ''}>Free</option>
          <option value="pro"        ${this._filter.plan === 'pro'        ? 'selected' : ''}>Pro</option>
          <option value="enterprise" ${this._filter.plan === 'enterprise' ? 'selected' : ''}>Enterprise</option>
        </select>
      </div>
      <div>
        <label class="form-label">Rechercher (nom ou email)</label>
        <input id="adm-flt-search" class="form-control"
               value="${this._esc(this._filter.search)}"
               placeholder="ex: nafissa, user@mail.dz">
      </div>
    </div>
  </div>

  <!-- Users table: plan selector and per-row action buttons -->
  <div class="card">
    <div class="card-body" style="padding:0;overflow-x:auto">
      <table class="adm-users-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Nom</th>
            <th>Email</th>
            <th>Plan</th>
            <th style="text-align:center">Analyses<br><small style="font-weight:400;font-size:10px">(mois)</small></th>
            <th style="text-align:center">Rapports<br><small style="font-weight:400;font-size:10px">(mois)</small></th>
            <th>Inscription</th>
            <th>Dernière connexion</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Action legend: visual reference for the three row-level buttons -->
  <div style="margin-top:12px;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--text-muted)">
    <span><span class="adm-act-btn adm-act-apply"      style="display:inline-flex;pointer-events:none"><i class="fas fa-check"></i></span> Appliquer plan</span>
    <span><span class="adm-act-btn adm-act-deactivate" style="display:inline-flex;pointer-events:none"><i class="fas fa-power-off"></i></span> Activer / Désactiver</span>
    <span><span class="adm-act-btn adm-act-delete"     style="display:inline-flex;pointer-events:none"><i class="fas fa-trash"></i></span> Supprimer</span>
  </div>

</div>

<style>
/* Users table: column headers are uppercased and compact */
.adm-users-table { width:100%;border-collapse:collapse;font-size:13px }
.adm-users-table th {
  padding:11px 14px;
  background:var(--bg-elevated);
  color:var(--text-secondary);
  font-weight:600;font-size:11px;
  text-transform:uppercase;letter-spacing:.04em;
  text-align:left;white-space:nowrap;
  border-bottom:1px solid var(--border-color);
}
.adm-users-table td {
  padding:11px 14px;
  border-bottom:1px solid var(--border-color);
  color:var(--text-primary);
  vertical-align:middle;
}
.adm-users-table tbody tr:hover { background:rgba(255,255,255,.025) }
.adm-users-table tbody tr:last-child td { border-bottom:none }

/* Inactive rows are dimmed to signal disabled accounts at a glance */
.row-inactive td { opacity:.65 }

/* Inline plan selector inside the table cell */
.adm-plan-sel { cursor:pointer; outline:none }
.adm-plan-sel:focus { border-color:var(--amber-400) }

/* Shared action button shell; colour modifiers applied per action type */
.adm-act-btn {
  width:28px;height:28px;
  display:inline-flex;align-items:center;justify-content:center;
  border-radius:6px;border:1px solid transparent;
  font-size:12px;cursor:pointer;
  transition:transform .12s ease, opacity .12s ease;
}
.adm-act-btn:hover       { transform:translateY(-1px);opacity:.85 }
.adm-act-apply           { background:rgba(20,184,166,.15); color:var(--teal-400);  border-color:rgba(20,184,166,.3) }
.adm-act-deactivate      { background:rgba(245,158,11,.15); color:var(--amber-400); border-color:rgba(245,158,11,.3) }
.adm-act-activate        { background:rgba(34,197,94,.15);  color:var(--green-400); border-color:rgba(34,197,94,.3) }
.adm-act-delete          { background:rgba(239,68,68,.15);  color:var(--red-400);   border-color:rgba(239,68,68,.3) }

/* Spinner animation shown on the button icon while an async action is in flight */
.adm-act-btn.loading i { animation:spin .7s linear infinite }
@keyframes spin { to { transform:rotate(360deg) } }
</style>`;
  },

  // Binds the plan dropdown and search input; search is debounced to avoid excessive API calls
  _bindFilters() {
    const debounce = (fn, ms = 300) => {
      let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
    };

    const pSel = document.getElementById('adm-flt-plan');
    if (pSel) pSel.onchange = () => { this._filter.plan = pSel.value; this._load(); };

    const sIn = document.getElementById('adm-flt-search');
    if (sIn) sIn.oninput = debounce(() => { this._filter.search = sIn.value.trim(); this._load(); }, 300);
  },

  // Attaches click handlers to every action button in every user row;
  // shows a spinner on the button during the async operation, then reloads the table
  _bindRowActions() {
    document.querySelectorAll('tr[data-uid]').forEach(tr => {
      const uid = Number(tr.dataset.uid);

      tr.querySelectorAll('[data-action]').forEach(el => {
        el.onclick = async () => {
          const action = el.dataset.action;

          // The plan <select> itself is not an action trigger
          if (!action || action === 'select-plan') return;

          // Show a spinner while the request is in flight
          const origHTML = el.innerHTML;
          el.innerHTML = '<i class="fas fa-spinner"></i>';
          el.classList.add('loading');
          el.disabled = true;

          try {
            if (action === 'apply-plan') {
              const sel     = tr.querySelector('[data-action="select-plan"]');
              const newPlan = sel?.value || 'free';
              const r       = await DataService.adminUpdateUserPlan(uid, newPlan);
              this._toast(r?.status === 200, 'Plan mis à jour', 'Erreur mise à jour plan');

            } else if (action === 'toggle') {
              const r = await DataService.adminToggleUserActive(uid);
              this._toast(r?.status === 200, 'Statut modifié', 'Erreur modification statut');

            } else if (action === 'delete') {
              // Restore the button before showing the confirmation dialog
              el.innerHTML = origHTML;
              el.classList.remove('loading');
              el.disabled = false;
              if (!confirm('Supprimer définitivement cet utilisateur ?')) return;

              // Re-apply spinner after the user confirms
              el.innerHTML = '<i class="fas fa-spinner"></i>';
              el.classList.add('loading');
              el.disabled = true;
              const r = await DataService.adminDeleteUser(uid);
              this._toast(r?.status === 200, 'Utilisateur supprimé', 'Erreur suppression');
            }
          } catch (err) {
            console.error('[AdminUsers] action error:', err);
            this._toast(false, '', 'Une erreur est survenue');
          }

          // Reload the table to reflect the updated state
          await this._load();
        };
      });
    });
  },

  // Delegates to the global toast component when available; falls back silently
  _toast(ok, msgOk = '', msgErr = 'Erreur') {
    const msg  = ok ? msgOk : msgErr;
    const kind = ok ? 'success' : 'error';
    if (window.Components?.toast) Components.toast(msg, kind);
  },

  // Escapes both angle brackets to prevent XSS when injecting user-supplied data into HTML
  _esc(v) {
    return (v == null) ? '' : String(v).replace(/</g, '&lt;').replace(/>/g, '&gt;');
  },
};

window.AdminUsersPage = AdminUsersPage;