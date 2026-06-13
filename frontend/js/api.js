/*
  En production  : appelle le backend Flask (window.BACKEND_URL)
  En mode offline: tombe sur MOCK_DATA de mock-data.js
 */

const API = {
  BASE_URL: (typeof window !== 'undefined' && window.BACKEND_URL)
    ? window.BACKEND_URL
    : 'http://localhost:5000/api',

  USE_MOCK: false,

  _backendOnline: false,
  _checkDone: false,

  _padCode(value) {
    return String(value ?? '').padStart(2, '0');
  },

  _wilayaCode(value) {
    const raw = String(value ?? '').trim();
    if (/^\d+$/.test(raw)) return parseInt(raw, 10);

    if (typeof MOCK_DATA !== 'undefined') {
      const match = MOCK_DATA.wilayas.find(w => w.name === raw || w.wilaya_name === raw);
      if (match?.code) return parseInt(match.code, 10);
    }

    return NaN;
  },

  _num(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  },

  _clamp(value, min = 0, max = 100) {
    return Math.max(min, Math.min(max, value));
  },

  _annualize(value) {
    return Math.round(this._num(value, 0) * 8760);
  },

  _statusFromScore(score) {
    const s = this._num(score, 0);
    if (s >= 85) return 'optimal';
    if (s >= 70) return 'high_potential';
    if (s >= 55) return 'moderate';
    return 'limited';
  },

  _findMockWilaya({ code = '', name = '' } = {}) {
    return MOCK_DATA.wilayas.find(w => w.code === code || w.name === name) || null;
  },

  _findMockZone({ id = '', name = '', wilaya = '' } = {}) {
    return MOCK_DATA.zones.find(z => z.id === id || (z.name === name && z.wilaya === wilaya)) || null;
  },

   _normalizeModel(model = {}) {
     const available = model.available !== undefined ? Boolean(model.available) : true;
     const { status, ...rest } = model;
     return {
       ...rest,
       status,
       available,
       type: model.type || model.family || 'Forecasting',
       training_time: model.training_time || (available ? 'Local checkpoint' : 'Checkpoint unavailable'),
       params: model.params || 'N/A',
       description: model.description || 'Forecasting model metadata',
     };
   },

  _normalizeWilaya(w) {
    if (!w) return null;
    const code = this._padCode(w.code ?? w.wilaya_code);
    const name = w.name || w.wilaya_name || `Wilaya ${code}`;
    const mock = this._findMockWilaya({ code, name }) || {};

    const meanGhi = this._num(w.mean_ghi, mock.ghi ? mock.ghi / 8760 : 0);
    const meanDni = this._num(w.mean_dni, mock.dni ? mock.dni / 8760 : meanGhi * 1.08);
    const meanDhi = this._num(w.mean_dhi, mock.dhi ? mock.dhi / 8760 : meanGhi * 0.18);
    const score = this._num(w.score, mock.score || 0);
    const gridDistance = this._num(
      w.grid_distance_km,
      mock.grid_distance_km ?? Math.max(0, Math.round((90 - score) * 10))
    );
    const demand = this._num(w.mean_demand, mock.demand_mw || 0);
    const clearness = this._num(w.mean_clearness, mock.clearness_kt || 0.6);
    const variability = this._num(w.variability, 0.05);

    return {
      ...mock,
      ...w,
      code,
      wilaya_code: this._num(w.wilaya_code, this._num(code, 0)),
      name,
      wilaya_name: name,
      region: w.region || mock.region || 'Algérie',
      climate: w.climate || mock.climate || 'BWh',
      lat: this._num(w.latitude, mock.lat || 0),
      lon: this._num(w.longitude, mock.lon || 0),
      latitude: this._num(w.latitude, mock.lat || 0),
      longitude: this._num(w.longitude, mock.lon || 0),
      ghi: this._annualize(meanGhi) || mock.ghi || 0,
      dni: this._annualize(meanDni) || mock.dni || 0,
      dhi: this._annualize(meanDhi) || mock.dhi || 0,
      mean_ghi: meanGhi,
      mean_dni: meanDni,
      mean_dhi: meanDhi,
      t2m: Number(this._num(w.mean_t2m, mock.t2m || 0).toFixed(1)),
      t2m_max: this._num(w.t2m_max, mock.t2m_max || this._num(w.mean_t2m, mock.t2m || 0) + 12),
      t2m_min: this._num(w.t2m_min, mock.t2m_min || this._num(w.mean_t2m, mock.t2m || 0) - 10),
      ws10m: Number(this._num(w.mean_ws10m, mock.ws10m || 3.5).toFixed(1)),
      rh2m: Number(this._num(w.mean_rh2m, mock.rh2m || 35).toFixed(1)),
      clearness_kt: Number(clearness.toFixed(2)),
      score: Number(score.toFixed(1)),
      solar_score: Math.round(this._clamp(this._annualize(meanGhi) / 26, 0, 99)),
      stability_score: Math.round(this._clamp(100 - variability * 900, 35, 98)),
      terrain_score: this._num(w.terrain_score, mock.terrain_score || Math.round(this._clamp(score - 6, 35, 95))),
      grid_score: Math.round(this._clamp(100 - gridDistance / 12, 10, 98)),
      demand_score: Math.round(this._clamp(demand / 8, 10, 98)),
      installed_mw: this._num(w.installed_mw, mock.installed_mw || 0),
      potential_mw: this._num(w.potential_mw, mock.potential_mw || Math.round(this._annualize(meanGhi) * 18)),
      grid_distance_km: Math.round(gridDistance),
      population: this._num(w.population, mock.population || 0),
      demand_mw: Number(demand.toFixed(1)),
      peak_demand: Math.round(this._num(w.peak_demand, mock.peak_demand || demand * 1.28)),
      status: w.status || mock.status || this._statusFromScore(score),
      data_source: w.data_source || mock.data_source || 'DuckDB/Parquet',
      communes: this._num(w.n_communes, mock.communes || 0),
      best_zones: mock.best_zones || [],
    };
  },

  _normalizeZone(z) {
    if (!z) return null;
    const id = z.id || '';
    const inferredCode = this._wilayaCode(z.wilaya_code || z.code || String(id).split('_')[0]);
    const wilaya = z.wilaya || z.wilaya_name || '';
    const name = z.name || z.commune_name || id;
    const mock = this._findMockZone({ id, name, wilaya }) || {};

    const meanGhi = this._num(z.mean_ghi, mock.ghi ? mock.ghi / 8760 : 0);
    const meanDni = this._num(z.mean_dni, mock.dni ? mock.dni / 8760 : meanGhi * 1.1);
    const score = this._num(z.score, mock.score || 0);
    const gridDist = this._num(z.grid_dist_km, mock.grid_dist_km || 120);
    const area = this._num(z.area_km2, mock.area_km2 || Math.max(40, Math.round(this._num(z.mean_demand, 80) / 2)));
    const clearness = this._num(z.mean_clearness, mock.clearness_kt || 0.65);
    const recommendation = z.recommendation || mock.recommendation || (score >= 80 ? 'build' : score >= 60 ? 'study' : 'wait');

    const rationale = Array.isArray(z.rationale) && z.rationale.length ? z.rationale : [
      `Composite score ${score.toFixed(1)}/100 based on irradiance and stability`,
      `Average GHI ${this._annualize(meanGhi)} kWh/m²/year`,
      `Grid distance ${Math.round(gridDist)} km`,
      clearness >= 0.65 ? 'High clearness index supports PV yield' : 'Moderate clearness suggests additional diligence',
    ];

    return {
      ...mock,
      ...z,
      id,
      code: Number.isFinite(inferredCode) ? this._padCode(inferredCode) : '',
      wilaya_code: Number.isFinite(inferredCode) ? inferredCode : this._num(z.wilaya_code, 0),
      wilaya,
      wilaya_name: wilaya,
      name,
      commune_name: name,
      lat: this._num(z.latitude, mock.lat || 0),
      lon: this._num(z.longitude, mock.lon || 0),
      latitude: this._num(z.latitude, mock.lat || 0),
      longitude: this._num(z.longitude, mock.lon || 0),
      area_km2: area,
      ghi: this._annualize(meanGhi) || mock.ghi || 0,
      dni: this._annualize(meanDni) || mock.dni || 0,
      mean_ghi: meanGhi,
      mean_dni: meanDni,
      clearness_kt: Number(clearness.toFixed(2)),
      score: Number(score.toFixed(1)),
      solar_score: this._num(z.solar_score, mock.solar_score || Math.round(this._clamp(this._annualize(meanGhi) / 26, 0, 99))),
      stability_score: this._num(z.stability_score, mock.stability_score || Math.round(this._clamp(94 - this._num(z.variability, 0.05) * 900, 30, 98))),
      terrain_score: this._num(z.terrain_score, mock.terrain_score || Math.round(this._clamp(score - 4, 30, 98))),
      grid_score: this._num(z.grid_score, mock.grid_score || Math.round(this._clamp(100 - gridDist / 10, 5, 98))),
      demand_score: this._num(z.demand_score, mock.demand_score || Math.round(this._clamp(this._num(z.mean_demand, 80) / 3, 10, 98))),
      elevation: this._num(z.elevation, mock.elevation || 250),
      terrain_type: z.terrain_type || mock.terrain_type || 'flat',
      grid_dist_km: Math.round(gridDist),
      road_dist_km: Math.round(this._num(z.road_dist_km, mock.road_dist_km || Math.max(8, gridDist * 0.22))),
      risk_seismic: z.risk_seismic || mock.risk_seismic || 'low',
      risk_flood: z.risk_flood || mock.risk_flood || 'low',
      risk_sand: z.risk_sand || mock.risk_sand || 'medium',
      risk_political: z.risk_political || mock.risk_political || 'low',
      land_status: z.land_status || mock.land_status || 'public',
      data_source: z.data_source || mock.data_source || 'DuckDB/Parquet',
      recommendation,
      potential_mw: this._num(z.potential_mw, mock.potential_mw || Math.round(area * 9)),
      rationale,
    };
  },

  _normalizeDecision(data) {
    if (!data) return null;
    const zone = this._normalizeZone(data.zone);
    return {
      ...data,
      zone,
      verdict: data.verdict || zone?.recommendation || 'study',
      confidence: this._num(data.confidence, 0.75),
      strengths: Array.isArray(data.strengths) ? data.strengths : (zone?.rationale || []),
      risks: Array.isArray(data.risks) ? data.risks : [],
      actions: Array.isArray(data.actions) ? data.actions : [],
    };
  },

  async checkBackend() {
    try {
      const res = await fetch(`${this.BASE_URL}/health`, { signal: AbortSignal.timeout(3000) });
      this._backendOnline = res.ok;
    } catch {
      this._backendOnline = false;
    }
    this._checkDone = true;
    return this._backendOnline;
  },

  async _get(endpoint, params = {}) {
    const url = new URL(`${this.BASE_URL}${endpoint}`);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
    });
    try {
      const headers = { 'Content-Type': 'application/json' };
      const token = sessionStorage.getItem('auth_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(url.toString(), {
        credentials: 'include',
        headers,
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) {
        this._backendOnline = true;
        
        // Log error details for debugging
        const errorBody = await res.text().catch(() => '');
        console.warn(`API Error ${res.status} on ${endpoint}:`, errorBody);
        
        // Handle 401 Unauthorized - likely session expired
        if (res.status === 401) {
          console.warn('Authentication failed - session may have expired');
          sessionStorage.removeItem('user');
          if (window.App) {
            window.App.navigate('login');
          }
        }
        
        return null;
      }
      const json = await res.json();
      this._backendOnline = true;
      return json;
    } catch (err) {
      this._backendOnline = false;
      console.error(`Fetch error on ${endpoint}:`, err.message);
      return null;
    }
  },

  async _post(endpoint, body = {}) {
    try {
      const headers = { 'Content-Type': 'application/json' };
      const token = sessionStorage.getItem('auth_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${this.BASE_URL}${endpoint}`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(10000),
      });
      if (!res.ok) {
        const errorBody = await res.text().catch(() => '');
        console.warn(`API Error ${res.status} on POST ${endpoint}:`, errorBody);
        if (res.status === 401) {
          sessionStorage.removeItem('user');
          if (window.App) window.App.navigate('login');
        }
        return null;
      }
      const json = await res.json();
      this._backendOnline = true;
      return json;
    } catch (err) {
      this._backendOnline = false;
      console.error(`Fetch error on POST ${endpoint}:`, err.message);
      return null;
    }
  },

  async verify() {
    const res = await this._get('/auth/verify');
    if (!res?.authenticated) {
      sessionStorage.removeItem('user');
      return null;
    }
    return res;
  },

  // Phase 1 — fetch current user (name, email, joined date) from SQLite
  async getCurrentUser() {
    try {
      const res = await this._get('/auth/user');
      return res?.data || null;
    } catch (e) {
      return null;
    }
  },

  async enqueue(endpoint, method = 'POST', body = {}, type = null) {
    if (!window.OfflineSync?.enqueue) return null;
    return OfflineSync.enqueue(endpoint, method, body, type);
  },

  async syncPendingActions() {
    if (!window.OfflineSync?.syncNow) return { synced: 0, failed: 0 };
    return OfflineSync.syncNow();
  },

  async _queueWrite(endpoint, method, body, type = null) {
    const actionId = await this.enqueue(endpoint, method, body, type);
    if (!actionId) return null;
    return {
      data: { queued: true, action_id: actionId, endpoint, method },
      status: 202,
      offline: true,
    };
  },

  async post(endpoint, body = {}, options = {}) {
    const live = await this._post(endpoint, body);
    if (live) return live;
    if (options.queueOffline === false) return null;
    if (navigator.onLine && this._backendOnline) return null;
    return this._queueWrite(endpoint, 'POST', body, options.type);
  },

  _delay: (ms = 300) => new Promise(r => setTimeout(r, ms + Math.random() * 100)),

  // ── Authentication ─────────────────────────────────────────────────────────

  async login(email, password) {
         try {
             const res = await fetch(`${this.BASE_URL}/auth/login`, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ email, password }),
                 signal: AbortSignal.timeout(10000),
                 credentials: 'include',  // Required for httpOnly cookies
             });

             if (res.ok) {
                        const json = await res.json();
                        // Token is stored in httpOnly cookie; backend returns it in
                        // JSON for development so we can send Authorization header
                        const access_token = json.access_token || (json.data && json.data.access_token) || null;
                        const userInfo = json.data || {};
                        if (access_token) sessionStorage.setItem('auth_token', access_token);
                        // Store user info (without token)
                        sessionStorage.setItem('user', JSON.stringify(userInfo));
                 
                 // Debug: check Set-Cookie headers
                 console.log('Login successful. Response headers:', {
                     'set-cookie': res.headers.get('set-cookie'),
                     'content-type': res.headers.get('content-type')
                 });
                 console.log('Document cookies after login:', document.cookie);
                 
                 if (window.Components) Components.renderAppShell();
                 return json;
             } else {
                 let errorJson;
                 try {
                     errorJson = await res.json();
                 } catch (e) {
                     errorJson = { error: 'Unknown error' };
                 }
                 return { error: errorJson.error || 'Unknown error', status: res.status };
             }
         } catch (err) {
             // Network error or timeout -> fallback to mock if allowed
             await this._delay(500);
             if (email && password) {
                 sessionStorage.setItem('user', JSON.stringify({ email: email, role: 'user', plan: 'free' }));  // fallback mock — role defaults to 'user'
                 if (window.Components) Components.renderAppShell();
                 return { data: { access_token: 'mock_token_123' }, status: 200 };
             }
             return { error: 'Network error', status: 500 };
         }
     },

  async register(name, email, password) {
         try {
             const res = await fetch(`${this.BASE_URL}/auth/register`, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ name, email, password }),
                 signal: AbortSignal.timeout(10000),
                 credentials: 'include',
             });

             if (res.ok) {
                 const json = await res.json();
                 return json;
             } else {
                 let errorJson;
                 try {
                     errorJson = await res.json();
                 } catch (e) {
                     errorJson = { error: 'Unknown error' };
                 }
                 return { error: errorJson.error || 'Unknown error', status: res.status };
             }
         } catch (err) {
             // Network error or timeout -> fallback to mock
             await this._delay(500);
             return { data: { message: "Mock user registered" }, status: 201 };
         }
     },

logout() {
         // Logout on server side first
         fetch(`${this.BASE_URL}/auth/logout`, {
             method: 'POST',
             credentials: 'include',
         }).catch(() => {});

         // Clear session
    sessionStorage.removeItem('user');
    sessionStorage.removeItem('auth_token');
         if (window.Components) Components.renderAppShell();
         App.navigate('login');
     },

   isAuthenticated() {
     return !!sessionStorage.getItem('user');
   },

  // ── Wilayas ──────────────────────────────────────────────────────────────

  async getWilayas(filters = {}) {
    const live = await this._get('/wilayas', {
      region: filters.region,
      climate: filters.climate,
      minScore: filters.minScore,
      search: filters.search,
      sort: filters.sort,
    });
    if (live?.data) {
      const data = live.data.map(w => this._normalizeWilaya(w)).filter(Boolean);
      return { ...live, data, total: data.length };
    }

    await this._delay(300);
    let data = [...MOCK_DATA.wilayas];
    if (filters.region) data = data.filter(w => w.region === filters.region);
    if (filters.minScore) data = data.filter(w => w.score >= filters.minScore);
    if (filters.climate) data = data.filter(w => w.climate === filters.climate);
    if (filters.sort === 'score') data.sort((a, b) => b.score - a.score);
    if (filters.sort === 'ghi') data.sort((a, b) => b.ghi - a.ghi);
    if (filters.sort === 'potential') data.sort((a, b) => b.potential_mw - a.potential_mw);
    if (filters.search) {
      const q = filters.search.toLowerCase();
      data = data.filter(w => w.name.toLowerCase().includes(q));
    }
    return { data: data.map(w => this._normalizeWilaya(w)), total: data.length, status: 200 };
  },

  async getWilaya(codeOrName) {
    const raw = String(codeOrName ?? '').trim();
    const identifier = encodeURIComponent(raw || '16');
    const live = await this._get(`/wilaya/${identifier}`);
    if (live?.data) {
      const d = live.data;
      const normalized = this._normalizeWilaya({
        code: d.code ?? d.id,
        wilaya_code: d.code ?? d.id,
        name: d.nom || d.name || raw,
        wilaya_name: d.nom || d.name || raw,
        region: d.region,
        climate: d.climat || d.climate,
        latitude: d.latitude,
        longitude: d.longitude,
        n_communes: d.nombre_communes ?? d.communes_count,
        score: d.score_composite,
        mean_ghi: this._num(d.ghi_annuel_kwh_m2 ?? d.ghi_annual_kwh_m2, 0) / 8760,
        t2m_min: d.temperature_min ?? d.t_min,
        t2m_max: d.temperature_max ?? d.t_max,
        mean_t2m: d.temperature_mean,
        mean_ws10m: d.vitesse_vent_m_s ?? d.wind_speed,
        mean_clearness: d.clearness_kt,
        demand_mw_avg: d.demand_mw_avg,
        grid_distance_km: d.distance_reseau_km ?? d.grid_distance_km,
      });
      return { ...live, data: { ...normalized, ...d } };
    }

    const normalizedCode = this._padCode(raw || '16');
    const legacy = await this._get(`/wilayas/${parseInt(normalizedCode, 10)}`);
    if (legacy?.data) return { ...legacy, data: this._normalizeWilaya(legacy.data) };

    await this._delay(200);
    const wilaya = MOCK_DATA.wilayas.find(w => w.code === normalizedCode || w.name === raw);
    if (!wilaya) return { error: 'Not found', status: 404 };
    return { data: this._normalizeWilaya(wilaya), status: 200 };
  },

  async getCompositeScore(wilayaName) {
    const live = await this._get(`/score-composite/${encodeURIComponent(String(wilayaName ?? '').trim())}`);
    if (live?.data) return live;
    return { data: null, status: 404 };
  },

  // ── Zones ────────────────────────────────────────────────────────────────

  async getZones(wilayaName = null) {
    const live = await this._get('/zones', wilayaName ? { wilaya: wilayaName } : {});
    if (live?.data) {
      const data = live.data.map(z => this._normalizeZone(z)).filter(Boolean);
      return { ...live, data, total: data.length };
    }

    await this._delay(350);
    let zones = [...MOCK_DATA.zones];
    if (wilayaName) zones = zones.filter(z => z.wilaya === wilayaName);
    return { data: zones.map(z => this._normalizeZone(z)), total: zones.length, status: 200 };
  },

  async getZone(id) {
    const live = await this._get(`/zones/${id}`);
    if (live?.data) return { ...live, data: this._normalizeZone(live.data) };

    await this._delay(200);
    const zone = MOCK_DATA.zones.find(z => z.id === id);
    if (!zone) return { error: 'Not found', status: 404 };
    return { data: this._normalizeZone(zone), status: 200 };
  },

  // ── Séries temporelles ───────────────────────────────────────────────────

  async getTimeSeries(wilayaCode, variable = 'GHI', period = 'monthly', options = {}) {
    const { allowMock = true } = options;
    const code = this._wilayaCode(wilayaCode);
    if (Number.isFinite(code)) {
      const live = await this._get(`/wilayas/${code}/timeseries`, { variable, period });
      if (live) return live;
    }

    if (!allowMock) {
      return {
        data: { labels: [], values: [], variable, wilaya: wilayaCode, period, data_source: 'unavailable' },
        status: 503,
        error: 'Live time series unavailable',
      };
    }

    await this._delay(400);
    const ts = MOCK_DATA.monthlyTimeSeries;
    const wMap = { '09': 'tamanrasset', '30': 'ouargla', '16': 'alger' };
    const key = wMap[this._padCode(Number.isFinite(code) ? code : wilayaCode)] || 'tamanrasset';
    const varData = ts[key][variable.toLowerCase()] || ts.tamanrasset.ghi;
    return {
      data: {
        labels: ts.labels,
        values: varData,
        variable,
        wilaya: wilayaCode,
        period,
        data_source: 'NASA_POWER',
        unit: variable === 'GHI' || variable === 'DNI' ? 'kWh/m²/mois' : variable === 'T2M' ? '°C' : variable === 'demand_mw' ? 'MW' : 'diverses',
      },
      status: 200,
    };
  },

  async getHourlyProfile(wilayaCode, season = 'summer', options = {}) {
    const { allowMock = true } = options;
    const code = this._wilayaCode(wilayaCode);
    if (Number.isFinite(code)) {
      const live = await this._get(`/wilayas/${code}/hourly`, { season });
      if (live) return live;
    }

    if (!allowMock) {
      return {
        data: { labels: [], values: [], season, wilaya: wilayaCode, data_source: 'unavailable' },
        status: 503,
        error: 'Live hourly profile unavailable',
      };
    }

    await this._delay(300);
    const profiles = MOCK_DATA.hourlyProfile;
    const isSahara = ['09', '30', '01', '37', '47'].includes(String(this._padCode(Number.isFinite(code) ? code : wilayaCode)));
    const key = `${isSahara ? 'sahara' : 'north'}_${season}`;
    return {
      data: { labels: profiles.labels, values: profiles[key] || profiles.sahara_summer, season, wilaya: wilayaCode },
      status: 200,
    };
  },

  // ── Prévisions ───────────────────────────────────────────────────────────

  async getForecast(modelId, variable = 'GHI', wilayaCode = '09', horizon = '30j') {
    const live = await this._get('/forecast', {
      model: modelId,
      variable,
      wilaya: this._padCode(wilayaCode),
      horizon: horizon,
    });
    if (live?.data) {
      const raw = live.data;
      const forecasts = raw.forecasts || [];
      // Format timestamps: use DD/MM HH:00 for clarity
      const formatLabel = (ts) => {
        const d = new Date(ts);
        const day = d.getDate();
        const month = d.getMonth() + 1;
        const hour = d.getHours();
        return `${day}/${month} ${hour}:00`;
      };
      const labels = forecasts.map(f => formatLabel(f.timestamp));
      const predicted = forecasts.map(f => f.value);
      const lower_ci = forecasts.map(f => f.confidence_lower);
      const upper_ci = forecasts.map(f => f.confidence_upper);
      // Use actual if available; otherwise fallback to predicted
      const actual = forecasts.map(f => (f.actual !== undefined && f.actual !== null) ? f.actual : f.value);
      const model = {
        ...this._normalizeModel(raw.model || {}),
        mae: raw.metrics?.mae,
        rmse: raw.metrics?.rmse,
        mape: raw.metrics?.mape,
        r2: raw.metrics?.r2,
      };
      return {
        ...live,
        data: {
          labels,
          actual,
          predicted,
          lower_ci,
          upper_ci,
          model,
          variable: variable,
          wilaya: this._padCode(wilayaCode),
          horizon: horizon,
          source: raw.source,
          processing_time_ms: raw.processing_time_ms,
        }
      };
    }

    // Fallback to mock if backend fails
    await this._delay(600);
    let rawModel = MOCK_DATA.forecastData.models.find(m => m.id === modelId);
    if (!rawModel) {
      rawModel = MOCK_DATA.forecastData.models[0];
    }
    const model = this._normalizeModel({
      ...rawModel,
      id: modelId,
      name: rawModel.id === modelId ? rawModel.name : modelId,
      available: false,
      training_time: 'Offline mock',
      description: rawModel.description || 'Mock forecast model',
    });
    const fd = MOCK_DATA.forecastData.forecast30d;
    const variance = { dlinear: 1.08, informer: 0.99, autoformer: 0.98, patchtst: 0.99, nhits: 0.985 };
    const factor = variance[modelId] || 1.0;
    return {
      data: {
        model,
        labels: fd.labels,
        actual: fd.actual,
        predicted: fd.predicted.map(v => Math.round(v * factor + (Math.random() - 0.5) * 4)),
        lower_ci: fd.lower_ci,
        upper_ci: fd.upper_ci,
        variable,
        wilaya: wilayaCode,
        horizon,
        source: 'mock',
      },
      status: 200,
    };
  },

  async getModels() {
    try {
      const live = await this._get('/models');
      if (live?.data) {
        let payload = live.data;
        if (payload?.data && typeof payload.data === 'object') {
          payload = payload.data;
        }

        // Some older backends or wrappers may return the payload directly as an array.
        if (payload?.forecasting_models === undefined && Array.isArray(live.data)) {
          payload = { forecasting_models: live.data };
        }

        if (!payload || typeof payload !== 'object') {
          payload = {};
        }

        // Handle new API response format with all model types
        let forecastingModels = payload.forecasting_models || [];
        let zoneRecNew = payload.zone_recommendation_new_approach || [];
        let zoneRecOld = payload.zone_recommendation_old_approach || [];

        // Ensure we have arrays
        if (!Array.isArray(forecastingModels)) {
          forecastingModels = [];
        }
        if (!Array.isArray(zoneRecNew)) {
          zoneRecNew = [];
        }
        if (!Array.isArray(zoneRecOld)) {
          zoneRecOld = [];
        }

        const normForecast = forecastingModels.map(m => this._normalizeModel(m));
        const normZoneNew = zoneRecNew.map(m => this._normalizeModel(m));
        const normZoneOld = zoneRecOld.map(m => this._normalizeModel(m));

        return {
          data: {
            forecasting_models: normForecast,
            zone_recommendation: payload.zone_recommendation || null,
            zone_recommendation_new_approach: normZoneNew,
            zone_recommendation_old_approach: normZoneOld,
            summary: payload.summary || {
              total_systems: normForecast.length + normZoneNew.length + normZoneOld.length,
              forecasting_count: normForecast.length,
              zone_recommendation_new_count: normZoneNew.length,
              zone_recommendation_old_count: normZoneOld.length,
              rule_based_count: payload.zone_recommendation ? 1 : 0
            }
          },
          status: 200
        };
      }

      return {
        data: {
          forecasting_models: (MOCK_DATA.forecastData?.models || []).map(m => this._normalizeModel(m)),
          zone_recommendation: null,
          zone_recommendation_new_approach: [],
          zone_recommendation_old_approach: [],
          summary: {}
        },
        status: 200
      };
    } catch (err) {
      console.warn('API getModels failed:', err);
      // Fallback to mock models so pages stay functional offline
      const mockModels = (MOCK_DATA.forecastData?.models || []).map(m => this._normalizeModel(m));
      const mockZoneNew = [];
      const mockZoneOld = [];
      return {
        data: {
          forecasting_models: mockModels,
          zone_recommendation: null,
          zone_recommendation_new_approach: mockZoneNew,
          zone_recommendation_old_approach: mockZoneOld,
          summary: {
            total_systems: mockModels.length,
            forecasting_count: mockModels.length,
            zone_recommendation_new_count: 0,
            zone_recommendation_old_count: 0,
            rule_based_count: 0
          }
        },
        status: 200
      };
    }
  },

  // ── Équipements ──────────────────────────────────────────────────────────

  async getEquipment(type = 'all', siteCapacity = 10) {
    await this._delay(300);
    const eq = MOCK_DATA.equipment;
    return {
      data: {
        panels: eq.panels,
        inverters: eq.inverters,
        storage: eq.storage,
        trackers: eq.trackers,
        site_capacity_mw: siteCapacity,
        recommendation: { panel: 'pv001', inverter: 'inv002', tracker: 'tr001', storage: 'bat001' },
      },
      status: 200,
    };
  },

  // ── ROI ──────────────────────────────────────────────────────────────────

  async getROIAnalysis(params = {}) {
    const wilayaCode = params.wilaya_code
      || this._findMockWilaya({ code: this._padCode(params.wilaya), name: params.wilaya })?.code
      || params.wilaya;

    const requestBody = {
      capacity_mw: params.capacity_mw,
      wilaya_code: wilayaCode,
      scenario: params.scenario,
    };

    const live = await this._post('/roi', requestBody);
    if (live) return live;

    const queuedActionId = (!navigator.onLine || !this._backendOnline)
      ? await this.enqueue('/roi', 'POST', requestBody, 'roi')
      : null;

    await this._delay(500);
    const { capacity_mw = 50, wilaya = 'Tamanrasset', scenario = 'base' } = params;
    const s = MOCK_DATA.roiScenarios[scenario] || MOCK_DATA.roiScenarios.base;
    const wilayaData = MOCK_DATA.wilayas.find(w => w.name === wilaya || w.code === this._padCode(wilayaCode)) || MOCK_DATA.wilayas[0];
    const capex = capacity_mw * s.capex_per_mw;
    const annual_gen_mwh = capacity_mw * wilayaData.ghi * 0.00085 * 1000;
    const cashflows = [];
    let cumulative = -capex;
    for (let yr = 1; yr <= 25; yr++) {
      const gen = annual_gen_mwh * Math.pow(1 - s.degradation_pct / 100, yr - 1);
      const revenue = gen * s.tariff_usd_kwh * 1000;
      const ncf = revenue - capacity_mw * s.opex_per_mw_yr;
      cumulative += ncf;
      cashflows.push({ year: yr, revenue: Math.round(revenue), opex: capacity_mw * s.opex_per_mw_yr, ncf: Math.round(ncf), cumulative: Math.round(cumulative) });
    }
    return {
      data: {
        params: { capacity_mw, wilaya: wilayaData.name, scenario },
        scenario: s,
        capex: Math.round(capex),
        npv: Math.round(s.npv * (capacity_mw / 50)),
        irr: s.irr,
        payback_years: s.payback,
        lcoe_usd_kwh: s.lcoe,
        annual_generation_mwh: Math.round(annual_gen_mwh),
        annual_revenue_usd: Math.round(annual_gen_mwh * s.tariff_usd_kwh * 1000),
        cashflows,
        offline_queued_action_id: queuedActionId,
      },
      status: 200,
      offline: Boolean(queuedActionId),
    };
  },

  // ── Décision ─────────────────────────────────────────────────────────────

  async getDecision(zoneId) {
    const live = await this._get(`/decision/${zoneId}`);
    if (live?.data) return { ...live, data: this._normalizeDecision(live.data) };

    await this._delay(400);
    const zone = MOCK_DATA.zones.find(z => z.id === zoneId) || MOCK_DATA.zones[0];
    const verdict = zone.recommendation;
    const actionMap = {
      build: [
        { title: "Lancer étude de faisabilité détaillée", desc: "Mandater un bureau d'études pour PVsyst et analyse géotechnique", priority: 'haute', timeline: '2-3 mois', cost: '80-120K USD' },
        { title: "Déposer demande d'autorisation foncière", desc: "Auprès de la Direction des Domaines et du Ministère de l'Énergie", priority: 'haute', timeline: '3-6 mois', cost: '15-25K USD' },
      ],
      study: [
        { title: "Étude d'impact sécheresse et ensablement", desc: "Analyse historique vents + mesures terrain sur 12 mois min.", priority: 'haute', timeline: '6-12 mois', cost: '50-80K USD' },
      ],
      wait: [
        { title: "Surveiller développement infrastructure réseau", desc: "Suivre programme HTB Sonelgaz pour cette région", priority: 'basse', timeline: 'Continu', cost: 'Minimal' },
      ],
    };
    return {
      data: {
        zone,
        verdict,
        confidence: verdict === 'build' ? 0.87 : verdict === 'study' ? 0.74 : 0.68,
        strengths: zone.rationale,
        risks: [
          { type: 'Technique', level: zone.risk_sand === 'high' ? 'high' : 'medium', detail: 'Ensablement potentiel' },
          { type: 'Réseau', level: zone.grid_dist_km > 100 ? 'high' : 'medium', detail: `Distance réseau: ${zone.grid_dist_km} km` },
          { type: 'Financement', level: 'medium', detail: 'Accès crédit projet' },
          { type: 'Réglementaire', level: 'low', detail: 'Contexte DZ favorable' },
        ],
        actions: actionMap[verdict] || actionMap.study,
      },
      status: 200,
    };
  },

  // ── Stats nationales ─────────────────────────────────────────────────────

  async getNationalStats() {
    const live = await this._get('/national-stats');
    if (live) return live;

    await this._delay(200);
    return { data: MOCK_DATA.nationalStats, status: 200 };
  },

  // ── Comparaison multi-sites ───────────────────────────────────────────────

  async compareSites(wilayas = []) {
    const live = await this._post('/compare', { wilayas });
    if (live) return live;

    await this._delay(400);
    const sites = wilayas.map(c => MOCK_DATA.wilayas.find(w => w.code === String(c))).filter(Boolean);
    const winner = sites.length ? sites.reduce((a, b) => a.score > b.score ? a : b) : null;
    return { data: { sites, winner: winner?.name, recommendation: winner ? `${winner.name} présente le meilleur potentiel.` : '' }, status: 200 };
  },

  // ── Packs hors-ligne ─────────────────────────────────────────────────────

  async getOfflinePacks() {
    const live = await this._get('/offline/packs');
    if (live) return live;

    await this._delay(300);
    return { data: MOCK_DATA.offlinePacks, status: 200 };
  },

  async downloadPack(packId) {
    const live = await this._post(`/offline/packs/${packId}/download`, {});
    if (live) return live;

    const pack = MOCK_DATA.offlinePacks.find(p => p.id === packId);
    if (!pack) return { error: 'Pack not found', status: 404 };
    await this._delay(2000);
    pack.status = 'downloaded';
    pack.downloaded_at = new Date().toISOString().split('T')[0];
    return { data: pack, status: 200 };
  },

  // ── Ranking ──────────────────────────────────────────────────────────────

  async getRanking() {
    const live = await this._get('/ranking');
    if (live?.data) {
      const data = live.data.map(w => this._normalizeWilaya(w)).filter(Boolean);
      return { ...live, data, total: data.length };
    }

    // Fallback to wilayas endpoint
    return this.getWilayas({ sort: 'score' });
  },

  async getRankingDetail(wilayaCode) {
    const live = await this._get(`/ranking/${wilayaCode}`);
    if (live?.data) return live;

    // Fallback
    await this._delay(200);
    return { data: null, status: 404 };
  },

  async getModelDetail(modelName) {
    const live = await this._get(`/models/${modelName}`);
    if (live?.data) return live;

    // Fallback
    await this._delay(200);
    return { data: null, status: 404 };
  },

  // ── Sources de données ────────────────────────────────────────────────────

  async getDataSources() {
    const live = await this._get('/data-sources');
    if (live) return live;

    await this._delay(200);
    return { data: MOCK_DATA.dataSources, status: 200 };
  },

  // ── Rapports ─────────────────────────────────────────────────────────────

  async generateReport(type, zoneId, format = 'investor') {
    const live = await this._post('/reports/generate', { type, zone_id: zoneId, format });
    if (live) return live;

    await this._delay(1500);
    return {
      data: {
        id: 'rpt_' + Date.now(),
        type,
        zone_id: zoneId,
        format,
        generated_at: new Date().toISOString(),
        pages: format === 'investor' ? 18 : 24,
        size_kb: 2840,
        status: 'ready',
      },
      status: 200,
    };
  },

  // ── Historique ────────────────────────────────────────────────────────────

  async getHistory(type = 'all', limit = 50, offset = 0) {
    const live = await this._get('/history', { type, limit, offset });
    if (live?.data) return live;
    // Fallback: empty list if not authenticated or backend offline
    return { data: [], total: 0, status: 200 };
  },

  async getHistoryItem(id, type) {
    const live = await this._get(`/history/${id}`, { type });
    if (live?.data) return live;
    return { error: 'Not found', status: 404 };
  },

  async deleteHistoryItem(id, type) {
    try {
      const res = await fetch(`${this.BASE_URL}/history/${id}?type=${type}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  },

  async exportHistory(type = 'all') {
    const live = await this._get('/history/export', { type });
    if (live?.data) return live;
    return { data: [], status: 200 };
  },

  // ── Recherche globale ────────────────────────────────────────────────────

  async search(query) {
    const live = await this._get('/search', { q: query });
    if (live) return live;

    await this._delay(250);
    const q = query.toLowerCase();
    const wilayas = MOCK_DATA.wilayas
      .filter(w => w.name.toLowerCase().includes(q) || w.region.toLowerCase().includes(q))
      .map(w => ({ type: 'wilaya', id: w.code, name: w.name, subtitle: `${w.region} • Score: ${w.score}` }));
    const zones = MOCK_DATA.zones
      .filter(z => z.name.toLowerCase().includes(q) || z.wilaya.toLowerCase().includes(q))
       .map(z => ({ type: 'zone', id: z.id, name: z.name, subtitle: `${z.wilaya} • GHI: ${z.ghi}` }));
     return { data: [...wilayas, ...zones], status: 200 };
   },

   // ── AI Model Comparison for Zone Recommendations ────────
 
   async runDeterministicRecommendation(params = {}) {
     const live = await this._post('/recommendation/deterministic', {
       wilaya_code: params.wilaya_code,
       target_capacity_mw: params.target_capacity_mw
     });
     if (live) return live;

     await this._delay(200);
     return { data: null, status: 404 };
   },
 
   async runMLRecommendation(params = {}) {
     const live = await this._post('/recommendation/ml', {
       wilaya_code: params.wilaya_code,
       target_capacity_mw: params.target_capacity_mw,
       approach: params.approach,
       model_name: params.model_name
     });
     if (live) return live;

     await this._delay(200);
     return { data: null, status: 404 };
   },
 
   // ── Rapports (Reports) ──────────────────────────────────────────────────

   async generateReport(params = {}) {
    const requestBody = {
      title: params.title || 'Solar Project Report',
      capacity_mw: params.capacity_mw || 50,
      wilaya: params.wilaya || 'Algeria',
      report_type: params.report_type || 'investor',
      roi_data: params.roi_data || {},
      forecast_data: params.forecast_data || {},
    };

    try {
      const token = sessionStorage.getItem('auth_token');
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${this.BASE_URL}/reports/generate`, {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify(requestBody),
        signal: AbortSignal.timeout(30000),
      });

      if (!res.ok) {
        console.warn(`Report generation failed with status ${res.status}`);
        return { error: 'Report generation failed', status: res.status };
      }

      // Get the blob and create download link
      const blob = await res.blob();
      const reportId = res.headers.get('X-Report-Id');
      return {
        data: {
          blob,
          report_id: reportId,
          filename: `solar_report_${new Date().toISOString().split('T')[0]}.pdf`,
        },
        status: 200,
      };
    } catch (err) {
      console.error('Report generation error:', err);
      return { error: err.message, status: 500 };
    }
  },

  async listReports() {
    const live = await this._get('/reports');
    if (live?.data) return live;

    await this._delay(300);
    return { data: [], total: 0, status: 200 };
  },

  async downloadReport(reportId) {
    try {
      const token = sessionStorage.getItem('auth_token');
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${this.BASE_URL}/reports/${reportId}/download`, {
        method: 'GET',
        credentials: 'include',
        headers,
        signal: AbortSignal.timeout(30000),
      });

      if (!res.ok) {
        const errorText = await res.text().catch(() => 'Download failed');
        console.warn(`Report download failed: ${res.status}`, errorText);
        return { error: errorText || 'Download failed', status: res.status };
      }

      const blob = await res.blob();
      const disposition = res.headers.get('content-disposition') || '';
      const filenameMatch = disposition.match(/filename\*?=([^;]+)/i);
      const filename = filenameMatch ? filenameMatch[1].trim().replace(/^UTF-8''/, '').replace(/"/g, '') : `solar_report_${reportId}.pdf`;
      return { data: { blob, filename }, status: 200 };
    } catch (err) {
      console.error('Report download error:', err);
      return { error: err.message || 'Download failed', status: 500 };
    }
  },

  async deleteReport(reportId) {
    const live = await this._delete(`/reports/${reportId}`);
    if (live) return live;

    await this._delay(100);
    return { status: 200, message: 'Deleted' };
  },

  async _delete(endpoint) {
    try {
      const headers = { 'Content-Type': 'application/json' };
      const token = sessionStorage.getItem('auth_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${this.BASE_URL}${endpoint}`, {
        method: 'DELETE',
        credentials: 'include',
        headers,
        signal: AbortSignal.timeout(10000),
      });
      if (!res.ok) {
        console.warn(`API Error ${res.status} on DELETE ${endpoint}`);
        return null;
      }
      const json = await res.json();
      this._backendOnline = true;
      return json;
    } catch (err) {
      this._backendOnline = false;
      console.error(`Fetch error on DELETE ${endpoint}:`, err.message);
      return null;
    }
  },
};

window.API = API;