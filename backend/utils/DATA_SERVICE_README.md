# 🛰 SolarDecide DZ — Central Data Service

Single source of truth for every page that needs wilaya / commune / national
statistics. Loads the parquet **once** at process boot and serves every
aggregation from an LRU-cached in-memory layer.

---

## 1. File layout

```
backend/backend/
├─ data/
│   └─ algeria_solar_communes_REAL.parquet   ← REQUIRED (96 MB, 58×291×5y)
├─ utils/
│   └─ data_service.py                        ← Python implementation
├─ routes/
│   └─ data_service_api.py                    ← Flask REST wrapper
└─ app.py                                     ← already registers the bp

frontend/frontend/
├─ index.html                                 ← loads data-service.js
└─ js/
    └─ data-service.js                        ← HTTP mirror used by pages
```

Path resolution order for the parquet:

1. `$PARQUET_PATH` env var
2. `backend/backend/data/algeria_solar_communes_REAL.parquet` (canonical)
3. `backend/backend/algeria_solar_communes_REAL.parquet`
4. Project-root copy (CI fallback)

---

## 2. Python API (`from utils.data_service import …`)

| Function | Signature | Returns |
|---|---|---|
| `get_wilaya_stats(name_or_code)` | `(str\|int) → dict\|None` | All key figures for one wilaya |
| `get_commune_stats(wilaya, commune)` | `(str, str) → dict\|None` | Same fields filtered to one commune |
| `get_national_stats()` | `() → dict` | TWh total, n_wilayas, n_communes, date span |
| `get_top_wilayas(metric, n)` | `(str, int) → list[dict]` | Top N by `ghi`/`potentiel`/`score` |
| `get_monthly_ghi(name)` | `(str) → dict\|None` | 12 monthly GHI values + labels |
| `list_wilayas()` | `() → list[dict]` | (code, name, climate) for selectors |
| `list_communes(name)` | `(str) → list[str]\|None` | Communes inside a wilaya |
| `is_ready()` | `() → dict` | Health / schema check |

### Mandatory formulas (as specified)

| Quantity | Formula |
|---|---|
| GHI annuel (kWh/m²/an) | `mean(GHI) × 8760 / 1000` |
| Stabilité climatique | `1 − std(GHI)/mean(GHI)` |
| Potentiel MW | `ghi_annuel × area_km² × 1000 × 0.20 / 1000` |
| `area_km²` | 10 km² × n_communes (default — column absent from dataset) |
| Score composite | `100 × (0.40·GHI_n + 0.20·DNI_n + 0.20·KT_n + 0.10·stabT_n + 0.10·WS10M_n)` |

Each `*_n` is min-max normalised on `[0, 1]` across the **58** wilayas (national basis).

### Unit caveat (important)

The dataset's `GHI` column is clipped to `[0, 1.5]` (likely unit ≠ canonical
`W/m²`). Applying the spec formula `× 8760 / 1000` therefore gives values
around 6 kWh/m²/year instead of the 1800-2400 typical for Algeria.
This is a **dataset-upstream issue**, not a service bug — re-ingest NASA POWER
with standard units to fix the magnitude. The formula is implemented exactly
as specified in the brief.

---

## 3. REST API (`/api/data-service/*`)

Every route returns `{ data: …, status: 200, source: "data_service" }` on success,
or `{ error: "...", status: 404 }` on a missing entity.

```
GET /api/data-service/health
GET /api/data-service/wilayas
GET /api/data-service/wilaya/<nom_ou_code>
GET /api/data-service/commune/<nom_wilaya>/<commune>
GET /api/data-service/national
GET /api/data-service/top?metric=ghi|potentiel_mw|score_composite&n=10
GET /api/data-service/monthly-ghi/<nom>
GET /api/data-service/communes/<nom_wilaya>
```

Smoke test (Python):

```bash
cd backend/backend
python3 -c "
from app import create_app
client = create_app().test_client()
r = client.get('/api/data-service/national')
print(r.get_json()['data'])
"
```

Expected:
```
{'n_wilayas': 58, 'n_communes': 291, 'annees_de_donnees': 5,
 'date_debut': '2019-01-01', 'date_fin': '2023-12-31', ...}
```

---

## 4. Frontend usage (`window.DataService`)

`frontend/js/data-service.js` is loaded BEFORE `i18n.js` in `index.html`,
so every page module sees `DataService` as a global. **No `import` needed**.

```js
// Inside any page render()
const stats = await DataService.getWilayaStats('Tamanrasset');
//    stats.ghi_annuel_kwh_m2, stats.score_composite, stats.potentiel_mw, ...

const top10 = await DataService.getTopWilayas('score_composite', 10);
const nat   = await DataService.getNationalStats();
const ghi12 = await DataService.getMonthlyGhi('Adrar');
const comm  = await DataService.getCommuneStats('Adrar', 'Adrar Centre');
```

Cache: each method memoises its result for the page lifetime.
Call `DataService.clearCache()` to force a refresh (e.g. after a deep settings change).

---

## 5. Migration guide for existing pages

The legacy endpoints (`/api/wilayas`, `/api/classement`, `/api/wilaya/<nom>`,
`/api/top10`, `/api/score-composite/<nom>` …) **still work** — Phase 2 was not
touched. But every NEW code path and every page rewrite must call
`DataService.*` only. Concretely:

| Legacy call (in a page) | New call |
|---|---|
| `fetch('/api/wilayas')` | `DataService.listWilayas()` |
| `fetch('/api/wilaya/Tamanrasset')` | `DataService.getWilayaStats('Tamanrasset')` |
| `fetch('/api/classement')` | `DataService.getTopWilayas('score_composite', 58)` |
| `fetch('/api/top10?critere=ghi')` | `DataService.getTopWilayas('ghi', 10)` |
| `fetch('/api/score-composite/Annaba')` | `DataService.getWilayaStats('Annaba').score_composite` |

Recommended order to migrate pages:
1. `landing.js` ✅ already done (hero counters)
2. `ranking.js` — biggest payoff (single source of ranking truth)
3. `wilaya-dashboard.js` — replaces `API.getWilaya` + `API.getCompositeScore`
4. `zone-analysis.js`
5. `roi.js` — only needs `getWilayaStats(name).ghi_annuel_kwh_m2`
6. `reports.js`
7. `forecast.js` — keep `/api/forecast-simple/*` for the IA model, switch to
   `DataService.listWilayas()` for the selector
8. `comparison.js` — keep `/api/compare` (ML model), use `DataService.listWilayas()` for the selector

---

## 6. Hard-coded counters fixed in `landing.js`

| Before | After |
|---|---|
| `1541` communes | `291` (live from `getNationalStats().n_communes`) |
| `25` ans de données | `5` (live from `getNationalStats().annees_de_donnees`) |
| `5.2M` TWh hard-coded | live `getNationalStats().twh_potentiel_total` |
| `58` wilayas hard-coded | live `getNationalStats().n_wilayas` (no change in value, but now confirmed) |

The values still display the right defaults (291 / 5 / 58) **even when the
backend is offline**, because they are seeded directly in `LandingPage._stats`
and the live refresh is non-blocking.

---

## 7. Dataset audit (run once at boot)

`is_ready()` returns `missing_cols: []` if the parquet contains the expected
20 columns. Current dataset (`algeria_solar_communes_REAL.parquet`) passes
the audit:

```
columns_required = datetime, wilaya_code, wilaya_name, commune_name,
                   latitude, longitude, climate,
                   GHI, DNI, DHI, T2M, T2M_MAX, T2M_MIN,
                   WS10M, RH2M, CLEARNESS_KT, PRECIP_MM
columns_missing  = []        ✓
n_wilayas        = 58        ✓
n_communes       = 291       ✓
time_range       = 2019-01-01 → 2023-12-31  (5 years)  ✓
total_rows       = 12 752 784
```
