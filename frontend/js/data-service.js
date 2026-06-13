// SolarDecide DZ — Service de données central (miroir frontend)
//
// Wrapper HTTP léger autour des routes /api/data-service/* (utils/data_service.py).
//
// USAGE OBLIGATOIRE :
// Toutes les pages (classement, wilaya, analyse de zone, comparaison,
// prévisions, ROI, rapports...) doivent passer par ce module pour obtenir
// les statistiques wilaya / commune / nationales. Ne plus appeler directement
// /api/wilayas, /api/classement, etc. — ces routes legacy restent actives
// mais sont unifiées via ce service central.
//
// Méthodes publiques :
//   DataService.getWilayaStats(name)             -> Promise<object|null>
//   DataService.getCommuneStats(wilaya, commune) -> Promise<object|null>
//   DataService.getNationalStats()               -> Promise<object>
//   DataService.getTopWilayas(metric='score_composite', n=10) -> Promise<object[]>
//   DataService.getMonthlyGhi(name)              -> Promise<object|null>
//   DataService.listWilayas()                    -> Promise<object[]>
//   DataService.listCommunes(name)               -> Promise<string[]|null>
//   DataService.health()                         -> Promise<object>
//
// Cache : chaque méthode met son résultat en cache pour la durée de vie de la
// page. Appeler DataService.clearCache() pour forcer un rafraîchissement.
(function (global) {
  'use strict';

  const BASE = () =>
    (global.API && global.API.BASE_URL) ||
    (global.BACKEND_URL) ||
    'http://localhost:5000/api';

  const _cache = new Map();

  // Construit les en-têtes d'authentification (Bearer token) pour les requêtes
  function _authHeaders(extra = {}) {
    const headers = { 'Content-Type': 'application/json', ...extra };
    const tok = (typeof sessionStorage !== 'undefined') ? sessionStorage.getItem('auth_token') : null;
    if (tok) headers['Authorization'] = `Bearer ${tok}`;
    return headers;
  }

  // Requête GET générique avec cache en mémoire et timeout de 15s
  async function _get(endpoint, opts = {}) {
    const noCache = !!opts.noCache || endpoint.startsWith('/admin/');
    if (!noCache && _cache.has(endpoint)) return _cache.get(endpoint);
    try {
      const headers = { 'Content-Type': 'application/json' };
      const tok = (typeof sessionStorage !== 'undefined') ? sessionStorage.getItem('auth_token') : null;
      if (tok) headers['Authorization'] = `Bearer ${tok}`;

      const res = await fetch(`${BASE()}${endpoint}`, {
        credentials: 'include',
        headers,
        signal: AbortSignal.timeout(15000),
      });
      if (!res.ok) {
        console.warn(`[DataService] ${endpoint} → HTTP ${res.status}`);
        return null;
      }
      const json = await res.json();
      if (!noCache) _cache.set(endpoint, json);
      return json;
    } catch (err) {
      console.error(`[DataService] fetch failed ${endpoint}:`, err.message);
      return null;
    }
  }

  const DataService = {
    BASE,

    clearCache() { _cache.clear(); },

    async health() {
      const r = await _get('/data-service/health');
      return r || { ready: false, error: 'unreachable' };
    },

    // Alias — certaines pages appellent DataService.getWilayas()
    async getWilayas() { return this.listWilayas(); },

    async listWilayas() {
      const r = await _get('/data-service/wilayas');
      return r?.data || [];
    },

    async listCommunes(wilayaName) {
      if (!wilayaName) return null;
      const r = await _get(`/data-service/communes/${encodeURIComponent(wilayaName)}`);
      return r?.data || null;
    },

    async getWilayaStats(wilayaName) {
      if (!wilayaName) return null;
      const r = await _get(`/data-service/wilaya/${encodeURIComponent(wilayaName)}`);
      return r?.data || null;
    },

    async getCommuneStats(wilayaName, communeName) {
      if (!wilayaName || !communeName) return null;
      const r = await _get(
        `/data-service/commune/${encodeURIComponent(wilayaName)}/${encodeURIComponent(communeName)}`
      );
      return r?.data || null;
    },

    async getNationalStats() {
      const r = await _get('/data-service/national');
      return r?.data || null;
    },

    async getTopWilayas(metric = 'score_composite', n = 10) {
      const m = encodeURIComponent(metric);
      const nn = Math.max(1, Math.min(58, Number(n) || 10));
      const r = await _get(`/data-service/top?metric=${m}&n=${nn}`);
      return r?.data || [];
    },

    async getMonthlyGhi(wilayaName) {
      if (!wilayaName) return null;
      const r = await _get(`/data-service/monthly-ghi/${encodeURIComponent(wilayaName)}`);
      return r?.data || null;
    },

    // ── Phase 3 — divers ─────────────────────────────────────────────
    async getClimateZones() {
      const r = await _get('/data-service/climate-zones');
      return r?.data || [];
    },

    async getWilayaOfTheWeek() {
      const r = await _get('/wilaya-du-jour');
      if (r?.data) return r.data;
      const r2 = await _get('/data-service/wilaya-of-the-week');
      return r2?.data || null;
    },

    async getAnalysesCount() {
      const r = await _get('/analyses-count');
      return r?.data || { total_analyses: 0, by_type: {} };
    },

    // Phase 3 — helpers pour la page Classement
    async getRanking({ metric = 'score', limit = 58, region = '', climate = '', search = '' } = {}) {
      const qs = new URLSearchParams();
      qs.set('metric', metric);
      qs.set('limit',  String(limit));
      if (region)  qs.set('region',  region);
      if (climate) qs.set('climate', climate);
      if (search)  qs.set('search',  search);
      const r = await _get(`/classement?${qs.toString()}`);
      return r?.data || [];
    },

    async getRegionsList() {
      const r = await _get('/regions');
      return r?.data || [];
    },

    async getRegionsBreakdown() {
      const r = await _get('/repartition-regions');
      return r?.data || [];
    },

    // Construit l'URL de téléchargement CSV (le cookie d'auth est suivi par le navigateur)
    csvExportUrl() {
      return `${BASE()}/export-csv-classement`;
    },

    // ── Phase 3 — Dashboard Wilaya ───────────────────────────────────
    async getWilayaMonthly(wilayaName) {
      if (!wilayaName) return null;
      const r = await _get(`/wilaya-monthly/${encodeURIComponent(wilayaName)}`);
      return r?.data || null;
    },

    async getWilayaRadar(wilayaName) {
      if (!wilayaName) return null;
      const r = await _get(`/wilaya-radar/${encodeURIComponent(wilayaName)}`);
      return r?.data || null;
    },

    async getWilayaExtras(wilayaName) {
      if (!wilayaName) return null;
      const r = await _get(`/wilaya-extras/${encodeURIComponent(wilayaName)}`);
      return r?.data || null;
    },

    // Construit l'URL de téléchargement du PDF wilaya (restriction de plan côté serveur)
    wilayaPdfUrl(wilayaName) {
      return `${BASE()}/wilaya-pdf/${encodeURIComponent(wilayaName)}`;
    },

    // ── Phase 3 — Analyse de Zone ─────────────────────────────────────
    async getCommuneAnalysis(wilayaName, communeName) {
      if (!wilayaName || !communeName) return null;
      const r = await _get(`/commune-stats/${encodeURIComponent(wilayaName)}/${encodeURIComponent(communeName)}`);
      return r?.data || null;
    },
    async getCommuneMonthly(wilayaName, communeName) {
      if (!wilayaName || !communeName) return null;
      const r = await _get(`/commune-monthly/${encodeURIComponent(wilayaName)}/${encodeURIComponent(communeName)}`);
      return r?.data || null;
    },
    async getCommunes(wilayaName) {
      if (!wilayaName) return [];
      const r = await _get(`/data-service/communes/${encodeURIComponent(wilayaName)}`);
      return r?.data || [];
    },

    // ── Phase 3 — Comparaison ─────────────────────────────────────────
    // POST /api/comparaison — réservé aux plans Pro et supérieurs
    async runComparaison(wilayas) {
      const resp = await fetch(`${BASE()}/comparaison`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wilayas }),
      });
      const out = await resp.json().catch(() => ({}));
      return { status: resp.status, ...out };
    },
    // Déclenche le téléchargement du PDF — restriction Pro+ côté serveur
    async downloadComparaisonPdf(wilayas) {
      const resp = await fetch(`${BASE()}/comparaison/pdf`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wilayas }),
      });
      if (!resp.ok) {
        let err = {};
        try { err = await resp.json(); } catch(_) {}
        return { status: resp.status, error: err.error || 'pdf_failed' };
      }
      const blob = await resp.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url;
      a.download = `comparaison_${(wilayas||[]).join('_')}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      return { status: 200 };
    },

    // ── Phase 3 — Admin ────────────────────────────────────────────────
    async adminDashboardStats() {
      const r = await _get('/admin/dashboard-stats');
      return r?.data || null;
    },
    async adminListUsers({ plan = 'all', search = '' } = {}) {
      const qs = new URLSearchParams();
      if (plan)   qs.set('plan', plan);
      if (search) qs.set('search', search);
      const r = await _get(`/admin/users?${qs.toString()}`);
      return r?.data || [];
    },
    async adminUpdateUserPlan(userId, plan) {
      const resp = await fetch(`${BASE()}/admin/users/${userId}/plan`, {
        method: 'PUT', credentials: 'include',
        headers: _authHeaders(),
        body: JSON.stringify({ plan }),
      });
      const out = await resp.json().catch(() => ({}));
      return { status: resp.status, ...out };
    },
    async adminResetUserQuota(userId) {
      const resp = await fetch(`${BASE()}/admin/users/${userId}/reset-quota`, {
        method: 'POST', credentials: 'include',
        headers: _authHeaders(),
      });
      const out = await resp.json().catch(() => ({}));
      return { status: resp.status, ...out };
    },
    async adminToggleUserActive(userId) {
      const resp = await fetch(`${BASE()}/admin/users/${userId}/toggle-active`, {
        method: 'PUT', credentials: 'include',
        headers: _authHeaders(),
      });
      const out = await resp.json().catch(() => ({}));
      return { status: resp.status, ...out };
    },
    async adminDeleteUser(userId) {
      const resp = await fetch(`${BASE()}/admin/users/${userId}`, {
        method: 'DELETE', credentials: 'include',
        headers: _authHeaders(),
      });
      const out = await resp.json().catch(() => ({}));
      return { status: resp.status, ...out };
    },
    async adminAnalytics() {
      const r = await _get('/admin/analytics');
      return r?.data || null;
    },
    async adminLogs({ type = 'all', date = '' } = {}) {
      const qs = new URLSearchParams();
      if (type) qs.set('type', type);
      if (date) qs.set('date', date);
      const r = await _get(`/admin/logs?${qs.toString()}`);
      return r?.data || { activities: [], errors: [] };
    },
    async adminReports() {
      const r = await _get('/admin/reports');
      return r?.data || { reports: [], stats: {} };
    },

    // ── Phase 3 — Profil ──────────────────────────────────────────────
    async getProfile() {
      const r = await _get('/profile', { noCache: true });
      return r?.data || null;
    },
    async getProfileAnalyses(limit) {
      const url = limit ? `/profile/analyses?limit=${limit}` : '/profile/analyses';
      const r = await _get(url, { noCache: true });
      return r || { data: [], count: 0 };
    },
    async getProfileRoi(limit) {
      const url = limit ? `/profile/roi-history?limit=${limit}` : '/profile/roi-history';
      const r = await _get(url, { noCache: true });
      return r || { data: [], count: 0 };
    },
    async getProfileReports() {
      const r = await _get('/profile/reports', { noCache: true });
      return r || { data: [], count: 0 };
    },
    profileReportDownloadUrl(id) {
      return `${BASE()}/profile/reports/${id}/download`;
    },

    // Sauvegarde l'analyse de zone courante dans l'historique SQLite (Pro+)
    async saveAnalysis({ wilaya, commune, score, ghi }) {
      const resp = await fetch(`${BASE()}/save-analysis`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wilaya, commune, score, ghi }),
      });
      const out = await resp.json().catch(() => ({}));
      return { status: resp.status, ...out };
    },
  };

  global.DataService = DataService;
})(typeof window !== 'undefined' ? window : globalThis);