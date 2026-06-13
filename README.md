<div align="center">

# 🌞 SolarDecide DZ

### AI-Powered Solar Energy Planning & Forecasting Platform for Algeria

*Plateforme d'aide à la décision solaire basée sur l'IA — pensée pour les investisseurs, les pouvoirs publics, les opérateurs réseau, les bureaux d'études EPC et les équipes terrain.*

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-black?logo=flask)
![DuckDB](https://img.shields.io/badge/DuckDB-1.5-yellow?logo=duckdb)
![PyTorch](https://img.shields.io/badge/PyTorch-2.0%2B-red?logo=pytorch)
![scikit--learn](https://img.shields.io/badge/scikit--learn-1.6-orange?logo=scikit-learn)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-green?logo=leaflet)
![Chart.js](https://img.shields.io/badge/Chart.js-4.4-pink?logo=chartdotjs)
![PWA](https://img.shields.io/badge/PWA-ready-purple)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

</div>

---

## 📖 Table des matières

1. [Présentation](#-présentation)
2. [Fonctionnalités principales](#-fonctionnalités-principales)
3. [Dataset](#-dataset--algeria_solar_communes_realparquet)
4. [Modèles d'IA](#-modèles-dia)
5. [Fichiers lourds (Dataset & Modèles)](#-fichiers-lourds-dataset--modèles)
6. [Architecture technique](#-architecture-technique)
7. [Stack technologique](#-stack-technologique)
8. [Installation & démarrage](#-installation--démarrage)
9. [API REST](#-api-rest)
10. [Plans d'abonnement](#-plans-dabonnement--quotas)
11. [Structure du projet](#-structure-du-projet)
12. [Captures écran](#-aperçu)
13. [Roadmap](#-roadmap)
14. [Licence & contributeurs](#-licence)

---

## 🌍 Présentation

**SolarDecide DZ** est une web application **full-stack** d'aide à la décision pour le déploiement de centrales photovoltaïques en Algérie. Elle combine :

- 🛰️ Un **dataset NASA POWER** réel de **12,7 millions** de mesures horaires couvrant **58 wilayas** et **287 communes** algériennes sur **5 années** (2019-2023),
- 🤖 Plusieurs **modèles d'IA entraînés** (Random Forest, Hybrid Ridge + MLP, et family Transformer : PatchTST / TFT / N-HiTS) pour la **prévision GHI** et le **classement multicritère** des zones,
- 💰 Un moteur de **calcul ROI financier** (CAPEX, OPEX, NPV, IRR, LCOE, payback) avec **3 scénarios** (conservateur / base / optimiste),
- 📄 La **génération automatique de rapports PDF** (Investisseur / Gouvernement / EPC),
- 🌐 Une **interface SPA multilingue** (FR/EN) avec mode hors ligne (**PWA**), 13 pages métier, et une **administration complète**.

> **Public cible** : investisseurs solaires, ministères de l'énergie, bureaux EPC, gestionnaires de réseau (Sonelgaz / OS), chercheurs.

---

## ✨ Fonctionnalités principales

### 🏠 Front-office (13 pages)

| # | Page | Description |
|---|---|---|
| 1 | **Landing** | Hero animé, particules, recherche rapide, carte Leaflet interactive des wilayas |
| 2 | **Classement national** | Tableau triable des 58 wilayas, filtres climat/région, top‑10 GHI, export CSV |
| 3 | **Dashboard Wilaya** | 6 KPI (GHI, DNI, Kt, T°, MW, demande), score composite radar, profils horaires été/hiver |
| 4 | **Analyse de Zone** ⭐ | Verdict *Build / Study / Wait*, panel explicabilité « Pourquoi cette zone ? », 6 risques (sismique, crue, sable, logistique, réseau, foncier) |
| 5 | **Comparaison de sites** | Jusqu'à 3 wilayas côte à côte, radar 5D, recommandation IA |
| 6 | **Prévision** | Sélecteur de 9 modèles, 7 variables (GHI/DNI/DHI/T2M/WS10M/demande/Kt), horizons 24h → 30j |
| 7 | **Comparaison modèles** | Leaderboard MAE/RMSE/MAPE/R², radar des top‑3 modèles |
| 8 | **Conseiller équipement** | Recommandation panneaux/onduleurs/trackers/stockage, BOM exportable |
| 9 | **Analyse ROI** | 5 KPI financiers, 3 scénarios, cashflow 25 ans, sensibilité au tarif |
| 10 | **Aide à la décision** | Verdict pleine page, plan d'action priorisé, navigation contextuelle |
| 11 | **Centre offline** ⭐ | Packs wilaya téléchargeables, notes terrain géolocalisées, PWA |
| 12 | **Rapports** | Investisseur / Gouvernement / EPC / Thèse — génération PDF |
| 13 | **Provenance données** | Registre des sources NASA, légende mesuré/estimé/synthétique |

### 🔐 Authentification & administration

- **JWT + cookies httpOnly** (PyJWT, HS256, expiration 24h)
- **Rôles** : `user` / `admin`
- **Plans** : `free` / `pro` (4 000 DZD/mois) / `enterprise` (7 000 DZD/mois)
- **Quotas mensuels** sur les recommandations (reset auto)
- **Dashboard Admin** : utilisateurs, analytics, logs d'activité, logs d'erreurs, rapports
- **Rate limiting** : 50 req/h, 200 req/j par IP (Flask-Limiter)

### 🌐 Internationalisation & PWA

- **Multilingue** : Français (par défaut) + English (JSON `locales/`)
- **Thème sombre** designé pour la lecture solaire
- **PWA** : manifest, service worker, packs wilaya hors-ligne
- **Responsive** : mobile / tablette / desktop / impression

---

## 📊 Dataset : `algeria_solar_communes_REAL.parquet`

> Le fichier doit être placé dans `backend/data/algeria_solar_communes_REAL.parquet` (chemin défini par `PARQUET_PATH` dans `config.py`).

| Caractéristique | Valeur |
|---|---|
| **Source** | NASA POWER (`data_source = NASA_real`) |
| **Format** | Apache Parquet (compression Snappy) |
| **Taille** | ~96 MB |
| **Granularité temporelle** | Horaire (1 mesure / heure) |
| **Période couverte** | 2019-01-01 00:00 → 2023-12-31 23:00 (5 ans, 1826 jours) |
| **Lignes** | **12 752 784** |
| **Colonnes** | 20 |
| **Couverture spatiale** | **58 wilayas**, **291 (wilaya, commune)** distinctes |

### Répartition climatique

| Zone climatique | Lignes | Région |
|---|---|---|
| 🏖️ Coastal | 3 330 624 | Littoral |
| 🏜️ Saharan | 2 629 440 | Grand Sud |
| 🌵 Semi-Arid | 2 410 320 | Steppe |
| ☀️ Arid | 2 278 848 | Hauts Plateaux |
| ⛰️ Highland | 2 103 552 | Atlas |

### Schéma complet

| Colonne | Type | Unité | Description |
|---|---|---|---|
| `datetime` | timestamp[ns] | — | Horodatage horaire |
| `wilaya_code` | int16 | — | Code wilaya (1-58) |
| `wilaya_name` | string | — | Nom officiel de la wilaya |
| `commune_name` | string | — | Nom de la commune |
| `latitude` | float32 | ° | Latitude WGS84 |
| `longitude` | float32 | ° | Longitude WGS84 |
| `climate` | string | — | Coastal / Saharan / Arid / Semi-Arid / Highland |
| `data_source` | string | — | `NASA_real` |
| `GHI` | float32 | kWh/m²/h | **Global Horizontal Irradiance** |
| `DNI` | float32 | kWh/m²/h | Direct Normal Irradiance |
| `DHI` | float32 | kWh/m²/h | Diffuse Horizontal Irradiance |
| `T2M` | float32 | °C | Température à 2 m |
| `T2M_MAX` | float32 | °C | Température max journalière |
| `T2M_MIN` | float32 | °C | Température min journalière |
| `WS10M` | float32 | m/s | Vitesse du vent à 10 m |
| `RH2M` | float32 | % | Humidité relative à 2 m |
| `CLRSKY_GHI` | float32 | kWh/m²/h | GHI ciel clair (référence théorique) |
| `CLEARNESS_KT` | float32 | 0-1 | Indice de clarté (GHI / extraterrestre) |
| `PRECIP_MM` | float32 | mm | Précipitations horaires |
| `demand_mw` | float32 | MW | Demande électrique estimée |

### Top 5 wilayas par GHI moyen (potentiel solaire)

| Rang | Wilaya | GHI moyen (kWh/m²/h) |
|---|---|---|
| 🥇 1 | Bordj Badji Mokhtar | 0.740 |
| 🥈 2 | In Guezzam | 0.740 |
| 🥉 3 | Tamanrasset | 0.739 |
| 4 | Illizi | 0.735 |
| 5 | Djanet | 0.735 |

> ⚡ Le dataset est interrogé via **DuckDB en mode `read_parquet`** — toutes les agrégations s'exécutent en **< 200 ms** sans charger le fichier complet en mémoire.

---

## 🤖 Modèles d'IA

### 1. Prévision GHI — `ml/prevision/`

| Modèle | Famille | Fichier | Métriques | Usage |
|---|---|---|---|---|
| **Random Forest** ✅ | Ensemble | `best_model_RandomForest.pkl` | MAPE **18.2 %** · Accuracy **81.8 %** | Production — `/api/forecast-simple/<wilaya>` |
| PatchTST | Transformer | `patchtst.pt` (1.2M params) | — | À la demande |
| TFT | Transformer | `tft.pt` (2.1M params) | — | À la demande |
| N-HiTS | MLP hiérarchique | `nhits.pt` (0.8M params) | — | Fallback rapide |
| VMD-PatchTST | Hybrid (3 branches) | — | — | Désactivé par défaut |
| Persistence / Derived | Naive | — | — | Variables secondaires (DHI/DNI/T2M/WS10M) |

**Pipeline** : agrégation mensuelle → fenêtre glissante `LOOK_BACK = 6` → prédiction GHI normalisé → dénormalisation → conversion kWh (100 kWc, PR = 0.80) → autorégression sur N pas.

### 2. Classement wilayas — `ml/comparaison_wilaya/`

| Modèle | Fichier | Métriques (test 2023) |
|---|---|---|
| **Hybrid Ridge + MLP** ✅ | `model_Hybrid_Ridge_MLP.pkl` | RMSE = **18.79** · MAE = **11.09** · R² = **0.636** · MAPE = **43.16 %** |

Scores pré-calculés dans `wilaya_ranking_final.csv` (split temporel strict 2019-2022 entraînement / 2023 test).

### 3. Score composite zones (déterministe)

---

## 📊 Fichiers lourds (Dataset & Modèles)

Les fichiers volumineux sont **hébergés sur Google Drive** :

### 1. Dataset Principal
| Fichier | Taille | Lien de téléchargement |
|---------|--------|------------------------|
| `algeria_solar_communes_REAL.parquet` | ~101 MB | **[⬇️ Télécharger le Dataset](https://drive.google.com/drive/u/0/folders/1W5ak6G5Ve7w7db9DMmDlkw6NpAtJIEMR)** |

> Placez-le dans : `backend/data/algeria_solar_communes_REAL.parquet`

### 2. Modèles d'IA (.pkl)
| Fichier | Taille | Dossier | Usage | Lien |
|---------|--------|---------|-------|------|
| `best_models_demand.pkl` | ~309 MB | `prevision/` | Prévision demande | **[⬇️ Télécharger](https://drive.google.com/drive/u/0/folders/1W5ak6G5Ve7w7db9DMmDlkw6NpAtJIEMR)** |
| `best_model_RandomForest.pkl` | ~XX MB | `prevision/` | Prévision GHI (production) | **[⬇️ Télécharger](https://drive.google.com/drive/u/0/folders/1W5ak6G5Ve7w7db9DMmDlkw6NpAtJIEMR)** |
| `model_Hybrid_Ridge_MLP.pkl` | ~XX MB | `comparaison_wilaya/` | Classement wilayas | **[⬇️ Télécharger](https://drive.google.com/drive/u/0/folders/1W5ak6G5Ve7w7db9DMmDlkw6NpAtJIEMR)** |

> **Instructions** :
> - Créez les dossiers `backend/ml/prevision/` et `backend/ml/comparaison_wilaya/`
> - Placez les fichiers aux emplacements correspondants

---

```
score = 0.35·mean_GHI + 0.20·sunshine_hours + 0.15·peak_GHI 
      + 0.15·clearness + 0.15·low_variability
```

Seuil heure ensoleillée : `GHI > 0.15 kWh/m²`.


---

## 🏗️ Architecture technique

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (SPA – Vanilla JS)                 │
│  index.html  +  13 pages  +  Leaflet  +  Chart.js  +  i18n  +  PWA  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  fetch + JWT cookie
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BACKEND  (Flask 3.1 — app.py)                 │
│                                                                     │
│  ┌──────────────┐  ┌─────────────┐  ┌─────────────────────────────┐ │
│  │  Routes /api │→ │  Services   │→ │  DataEngine (DuckDB)        │ │
│  │  20+ BPs     │  │  · auth     │  │   read_parquet → SQL <200ms │ │
│  └──────┬───────┘  │  · plan     │  └─────────────┬───────────────┘ │
│         │          │  · recommend│                │                 │
│         │          │  · forecast│                ▼                 │
│         │          │  · admin    │  ┌─────────────────────────────┐ │
│         │          └──────┬──────┘  │ algeria_solar_communes_REAL │ │
│         │                 │         │      .parquet  (96 MB)      │ │
│         │          ┌──────▼──────┐  └─────────────────────────────┘ │
│         │          │  ML Models  │                                  │
│         │          │ · RF .pkl   │                                  │
│         │          │ · Ridge+MLP │                                  │
│         │          │ · PatchTST  │                                  │
│         │          └─────────────┘                                  │
│         ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  SQLite (database.db) — users, plans, history, logs, reports │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Flask-Limiter (50/h, 200/d)  ·  CORS allowlist  ·  JWT cookies     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Stack technologique

### Backend

| Catégorie | Technologie |
|---|---|
| **Framework web** | Flask 3.1, Flask-CORS, Flask-Limiter, Flask-SQLAlchemy |
| **Base de données** | SQLite (dev) — DuckDB **1.5** pour le moteur analytique sur Parquet |
| **Données** | pandas 2.2, numpy 2.3, pyarrow, numpy-financial |
| **ML (core)** | scikit-learn 1.6, joblib |
| **ML (optionnel)** | PyTorch ≥ 2.0 (PatchTST / TFT / N-HiTS) |
| **Auth** | PyJWT 2.13 (HS256) + Werkzeug password hashing |
| **Validation** | Pydantic 2.13 |
| **PDF** | ReportLab 4.4 |

### Frontend

| Catégorie | Technologie |
|---|---|
| **Base** | Vanilla JavaScript ES6+ (zéro build) |
| **Cartographie** | Leaflet 1.9 |
| **Graphiques** | Chart.js 4.4 |
| **Style** | CSS3 (dark theme + responsive + print) |
| **Polices** | Inter, Space Grotesk, Font Awesome 6 |
| **PWA** | Web App Manifest + Service Worker |
| **i18n** | JSON par locale (fr, en) |

---

## 🚀 Installation & démarrage

### Pré-requis

- Python **3.9+** (testé sur 3.13)
- 4 GB RAM minimum (pour les requêtes DuckDB sur le parquet complet)
- Le fichier `algeria_solar_communes_REAL.parquet` (~96 MB)

### 1. Cloner le dépôt

```bash
git clone https://github.com/<your-user>/SolarDecide-DZ.git
cd SolarDecide-DZ
```

### 2. Installer le backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .\.venv\Scripts\activate         # Windows PowerShell

pip install -r requirements.txt           # core (obligatoire)
pip install -r requirements_ml.txt        # PyTorch (optionnel — pour PatchTST/TFT/N-HiTS)
```

> 💡 Sans `requirements_ml.txt`, le backend démarre en **mode dégradé** : le blueprint forecast deep-learning est ignoré silencieusement, mais **tous les autres endpoints** (dataset, ROI, comparaison Hybrid Ridge+MLP, rapports) restent **100 % fonctionnels**.

### 3. Placer le dataset

```bash
mkdir -p backend/data
cp <chemin>/algeria_solar_communes_REAL.parquet backend/data/
```

### 4. Variables d'environnement (optionnel)

```bash
export JWT_SECRET="change-me-in-production"
export FLASK_ENV="production"                      # active la CORS allowlist
export ALLOWED_ORIGINS="https://solardz.dz"
export PARQUET_PATH="backend/data/algeria_solar_communes_REAL.parquet"
```

### 5. Lancer l'application

```bash
cd backend
python app.py --host 0.0.0.0 --port 5000
```

Le serveur Flask sert **également le frontend statique** (`frontend/`) à la racine `/`. Ouvrir :

👉 **http://localhost:5000**

### 6. (Optionnel) Déploiement sur Google Colab

```python
!python app.py --port 5000
# Puis exposer via cloudflared :
# !cloudflared tunnel --url http://localhost:5000
# Mettre à jour window.BACKEND_URL dans frontend/index.html
```

---

## 🔌 API REST

L'API expose **70+ endpoints** organisés en blueprints. Voici les plus importants :

### 🔐 Authentification — `/api/auth/*`

| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Création de compte |
| `POST` | `/auth/login` | Connexion → cookie JWT httpOnly |
| `POST` | `/auth/logout` | Déconnexion |
| `GET` | `/auth/verify` | Vérifier la session |
| `GET` | `/auth/user` | Profil utilisateur courant |

### 📊 Données — `/api/data-service/*` & `/api/*`

| Endpoint | Description |
|---|---|
| `GET /api/wilayas` | Liste des 58 wilayas |
| `GET /api/wilaya/<nom>` | Détails d'une wilaya |
| `GET /api/classement` | Classement national |
| `GET /api/top10` | Top 10 GHI |
| `GET /api/repartition-regions` | Stats par région climatique |
| `GET /api/score-composite/<wilaya>` | Score composite détaillé |
| `GET /api/wilaya-monthly/<nom>` | Profil mensuel GHI/DNI |
| `GET /api/wilaya-du-jour` | Wilaya mise en avant |

### 🤖 Prévision — `/api/forecast*`

| Endpoint | Description |
|---|---|
| `GET /api/forecast-simple/<wilaya>` | Prévision Random Forest (production) |
| `GET /api/long-term-trend/<wilaya>` | Tendance long terme |
| `GET /api/forecast` | Prévision multimodèle (PyTorch) |
| `GET /api/forecast/compare` | Comparaison de modèles |

### 🎯 Recommandation & comparaison

| Endpoint | Description |
|---|---|
| `POST /api/recommendation/deterministic` | Score composite zones |
| `POST /api/recommendation/ml` | Modèle ML |
| `POST /api/comparaison` | Comparer N wilayas |
| `POST /api/comparaison/pdf` | Export PDF comparaison |

### 💰 ROI — `/api/roi*`

| Endpoint | Description |
|---|---|
| `POST /api/roi` | Calcul CAPEX/NPV/IRR/Payback/LCOE |
| `GET /api/roi/history` | Historique des calculs |
| `GET /api/roi/export-pdf/<id>` | Export PDF rapport ROI |

### 📄 Rapports — `/api/reports*`

| Endpoint | Description |
|---|---|
| `POST /api/reports/generate` | Générer un rapport (Investor/Gov/EPC) |
| `GET /api/reports` | Lister mes rapports |
| `GET /api/reports/<id>/download` | Télécharger PDF |

### 👤 Profil & historique

| Endpoint | Description |
|---|---|
| `GET /api/profile` | Mon profil |
| `GET /api/profile/analyses` | Mes analyses |
| `GET /api/history` | Historique global |
| `GET /api/history/export` | Export CSV |

### 🛡️ Administration — `/api/admin/*` (rôle admin requis)

| Endpoint | Description |
|---|---|
| `GET /admin/dashboard-stats` | KPI globaux |
| `GET /admin/users` | Lister utilisateurs |
| `PUT /admin/users/<id>/plan` | Changer le plan |
| `PUT /admin/users/<id>/toggle-active` | Activer / désactiver |
| `DELETE /admin/users/<id>` | Supprimer |
| `GET /admin/analytics` | Statistiques d'usage |
| `GET /admin/logs` | Logs d'activité & d'erreurs |
| `GET /admin/reports` | Tous les rapports générés |

### 💳 Plans & quotas — `/api/plan/*`

| Endpoint | Description |
|---|---|
| `GET /plan/info` | Mon plan + compteurs + tarifs |
| `GET /plan/quotas` | Table des quotas |
| `POST /upgrade-plan` | Upgrade (paiement simulé) |
| `POST /plan/downgrade` | Repasser en free |

### 🩺 Santé

```http
GET /api/health
→ { "status": "ok", "parquet": true, "version": "1.0.0",
    "services": { "recommendation": true, "forecasting": true } }
```

---

## 💳 Plans d'abonnement & quotas

| Fonctionnalité | 🆓 Free | 🟠 Pro (4 000 DZD/mois) | 🟣 Enterprise (7 000 DZD/mois) |
|---|:---:|:---:|:---:|
| Consultation classements & dashboards | ✅ | ✅ | ✅ |
| Export CSV classement | ❌ | ✅ | ✅ |
| Export CSV brut | ❌ | ❌ | ✅ |
| Analyse de zone | ❌ | ✅ | ✅ |
| Comparaison de sites | ❌ | ✅ | ✅ |
| Prévision 24 h / 7 j | ❌ | ✅ | ✅ |
| Prévision 30 j / 1 an / long terme | ❌ | ❌ | ✅ |
| Calcul ROI | ❌ | ✅ | ✅ |
| Rapport Investisseur | ❌ | ✅ | ✅ |
| Rapport Gouvernement / EPC | ❌ | ❌ | ✅ |
| Recommandations / mois | 0 | **5** | ♾️ |
| Accès API | ❌ | ❌ | ✅ |

> 💡 La logique des quotas est centralisée dans `services/plan_service.py` (`QUOTAS`, `FEATURE_REQUIREMENTS`). Le reset mensuel est paresseux (au prochain hit).

---

## 📂 Structure du projet

```
SolarDecide-DZ/
├── backend/
│   ├── app.py                          # Application factory Flask
│   ├── config.py                       # PARQUET_PATH, MODEL_REGISTRY, scénarios ROI, JWT…
│   ├── data_engine.py                  # DuckDB + Parquet (couche analytique)
│   ├── db_models.py                    # SQLAlchemy : User, Plans, History, Logs, Reports
│   ├── schemas.py                      # Pydantic
│   ├── preprocessing.py                # Pipeline features
│   ├── ai_forecasting.py               # Wrapper modèles forecasting
│   ├── ai_zone_recommendation.py       # Score composite + risques
│   ├── migrate_admin.py                # Migration rôle admin
│   ├── migrate_plan.py                 # Migration colonnes plan
│   ├── requirements.txt                # core deps
│   ├── requirements_ml.txt             # PyTorch (optionnel)
│   ├── database.db                     # SQLite (dev)
│   │
│   ├── data/
│   │   └── algeria_solar_communes_REAL.parquet   ⚠️ à placer ici
│   │
│   ├── models/
│   │   └── loader.py                   # Lazy-loading des checkpoints PyTorch
│   │
│   ├── ml/
│   │   ├── prevision/
│   │   │   ├── best_model_RandomForest.pkl
│   │   │   ├── forecast_service.py     # MAPE 18.2 %
│   │   │   ├── Code modeles.py         # Script d'entraînement
│   │   │   └── wilaya_ghi_ranking.csv
│   │   └── comparaison_wilaya/
│   │       ├── model_Hybrid_Ridge_MLP.pkl
│   │       ├── compare.py              # Blueprint /api/compare
│   │       └── wilaya_ranking_final.csv
│   │
│   ├── services/
│   │   ├── admin_service.py
│   │   ├── forecasting_service.py
│   │   ├── plan_service.py             # PLAN_ORDER, QUOTAS, décorateurs
│   │   ├── recommendation_service.py
│   │   └── zone_model_service.py
│   │
│   ├── routes/                         # 20 blueprints Flask
│   │   ├── auth.py            admin.py            plan.py
│   │   ├── profile.py         history.py          analyses.py
│   │   ├── reports.py         roi.py              decision.py
│   │   ├── forecast.py        ranking.py          recommendation.py
│   │   ├── zones.py           wilayas.py          comparaison_phase3.py
│   │   ├── dataset_api.py     data_service_api.py search.py
│   │   ├── models.py          misc.py
│   │   └── __init__.py
│   │
│   ├── utils/
│   │   ├── data_service.py             # Façade pour les routes
│   │   ├── roi.py                      # NPV / IRR / LCOE / payback
│   │   ├── reports.py                  # Génération PDF (ReportLab)
│   │   └── wilaya_pdf.py
│   │
│   └── reports/                        # PDF générés
│
└── frontend/
    ├── index.html                      # Point d'entrée SPA
    ├── manifest.json                   # PWA
    ├── README.md
    ├── css/
    │   ├── main.css                    # Design system dark theme
    │   ├── responsive.css              # Media queries + print
    │   ├── plan.css                    # Paywall styling
    │   └── roi.css
    ├── js/
    │   ├── app.js                      # Router SPA
    │   ├── app-state.js
    │   ├── api.js                      # Client API (fetch + JWT)
    │   ├── auth.js
    │   ├── plan.js  /  plan-gate.js    # Feature gating
    │   ├── data-service.js
    │   ├── i18n.js                     # Loader locales/
    │   ├── components.js               # KPI, modal, toast, sidebar
    │   ├── utils.js
    │   ├── offline-sync.js             # PWA sync
    │   ├── mock-data.js                # Fallback offline
    │   ├── forecast_update.js
    │   └── pages/                      # 18 pages
    │       ├── landing.js             ranking.js
    │       ├── wilaya-dashboard.js    zone-analysis.js
    │       ├── comparison.js          forecast.js
    │       ├── history.js             roi.js
    │       ├── reports.js             profile.js
    │       ├── pricing.js             offline.js
    │       ├── login.js               register.js
    │       └── admin-{dashboard,users,analytics,logs,reports}.js
    └── locales/
        ├── fr.json
        └── en.json
```

---

## 🖼️ Aperçu

> Lancer `python app.py` puis ouvrir `http://localhost:5000` :

- 🏠 **Landing** — carte Leaflet animée des 58 wilayas, recherche rapide
- 🏆 **Classement** — top 10 GHI : Bordj Badji Mokhtar, In Guezzam, Tamanrasset, Illizi, Djanet…
- 📊 **Dashboard Wilaya** — radar score composite + profils horaires été/hiver
- 🎯 **Analyse zone** — verdict Build/Study/Wait avec explicabilité
- 📈 **Prévision** — Random Forest production-ready (MAPE 18.2 %)
- 💰 **ROI** — 3 scénarios sur 25 ans, NPV/IRR/Payback/LCOE
- 📄 **Rapports** — PDF Investor/Government/EPC (exemples dans `backend/reports/`)
- 🛡️ **Admin** — 5 pages (dashboard, users, analytics, logs, reports)

---

## 🗺️ Roadmap

- [ ] 🔌 **Intégration paiement** réel (CIB / BaridiMob)
- [ ] 🌍 **Module API publique** (plan Enterprise)
- [ ] 🛰️ Ajout de **données satellite SEVIRI / Sentinel-2**
- [ ] 🇩🇿 **Localisation arabe (RTL)** complète
- [ ] 🐳 Image **Docker** + déploiement Kubernetes
- [ ] 🧪 **Tests unitaires** Pytest + couverture
- [ ] 📊 **Dashboard Grafana** pour la supervision
- [ ] 🤖 Migration vers les **transformers déployés** (PatchTST, TFT, N-HiTS) en production
- [ ] 📱 App mobile native (capacitor / Flutter)

---

## 🧪 Tests rapides

```bash
# Health check
curl http://localhost:5000/api/health

# Classement
curl http://localhost:5000/api/classement | jq

# Détails Adrar
curl http://localhost:5000/api/wilaya/Adrar | jq

# Prévision Random Forest pour Tamanrasset
curl "http://localhost:5000/api/forecast-simple/Tamanrasset?horizon=24"
```

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour proposer une amélioration :

```bash
git checkout -b feature/ma-fonctionnalite
git commit -m "feat: ajout de XYZ"
git push origin feature/ma-fonctionnalite
# Puis ouvrir une Pull Request
```

Merci de respecter le style existant (PEP-8 côté Python, ESLint vanilla côté JS) et d'ajouter une description claire du changement.


---

## 🙏 Crédits & sources

- **Données météorologiques** : [NASA POWER](https://power.larc.nasa.gov/) (`data_source = NASA_real`)
- **Cartographie** : [OpenStreetMap](https://www.openstreetmap.org/) via [Leaflet](https://leafletjs.com/)
- **Modèles deep-learning** : architectures PatchTST, TFT (PyTorch Forecasting), N-HiTS
- **Inspiration métier** : Sonelgaz, CDER (Centre de Développement des Énergies Renouvelables d'Algérie), Ministère de l'Énergie

---

<div align="center">

**🌞 SolarDecide DZ — Décider, c'est rayonner.**

Made with ❤️ for Algeria's solar future.

</div>
