// Global application state — selected wilaya + per-page snapshots for navigation restore.
const AppState = {
  // Currently selected wilaya, shared across pages
  selectedWilaya: {
    code: '',
    name: '',
    ghiAnnuel: null,
    potentielMW: null,
    scoreComposite: null,
  },

  // Per-page snapshots (params, scroll position, etc.) for navigation restore
  pages: {},

  // Set the selected wilaya and persist it to sessionStorage
  setSelectedWilaya({ code = '', name = '', ghiAnnuel = null, potentielMW = null, scoreComposite = null } = {}) {
    this.selectedWilaya = {
      code: String(code || '').padStart(2, '0'),
      name: name || '',
      ghiAnnuel: ghiAnnuel != null ? Number(ghiAnnuel) : null,
      potentielMW: potentielMW != null ? Number(potentielMW) : null,
      scoreComposite: scoreComposite != null ? Number(scoreComposite) : null,
    };
    try {
      sessionStorage.setItem('sdz_selected_wilaya', JSON.stringify(this.selectedWilaya));
    } catch (e) {
      // sessionStorage unavailable (private mode, quota, etc.) — fail silently
    }
  },

  // Restore the selected wilaya from sessionStorage on page load
  loadFromSession() {
    try {
      const raw = sessionStorage.getItem('sdz_selected_wilaya');
      if (raw) Object.assign(this.selectedWilaya, JSON.parse(raw));
    } catch (e) {
      // No saved state or corrupted JSON — keep defaults
    }
  },

  // Save a snapshot of a page's state, timestamped
  savePage(page, snapshot = {}) {
    if (!page) return;
    this.pages[page] = {
      ...snapshot,
      savedAt: Date.now(),
    };
  },

  // Retrieve the saved snapshot for a page, if any
  getPage(page) {
    return this.pages[page] || null;
  },

  // Merge navigation params with stored page params (explicit params win)
  mergeNavParams(page, params = {}) {
    const saved = this.getPage(page);
    const savedParams = saved?.params || {};
    const merged = { ...savedParams, ...params };
    // Fall back to the globally selected wilaya if no wilaya was specified
    if (!merged.name && !merged.wilaya && !merged.code && this.selectedWilaya.name) {
      merged.name = this.selectedWilaya.name;
      if (this.selectedWilaya.code) merged.code = this.selectedWilaya.code;
    }
    return merged;
  },
};

// Restore previous selection on load and expose globally
AppState.loadFromSession();
window.AppState = AppState;