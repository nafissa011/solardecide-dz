// Static fallback data — used when the backend is unreachable.
// Solar values based on NASA POWER / Meteonorm ranges for Algeria.

const MOCK_DATA = {

  // 48 wilayas with solar metrics, scores, and best zones
  wilayas: [
    {
      code: '09', name: 'Tamanrasset', region: 'Sahara', climate: 'BWh', lat: 22.78, lon: 5.52,
      ghi: 2450, dni: 2710, dhi: 410, t2m: 28.4, t2m_max: 42.1, t2m_min: 14.2,
      ws10m: 4.8, rh2m: 18.2, clearness_kt: 0.74,
      score: 94, solar_score: 98, stability_score: 91, terrain_score: 88, grid_score: 45, demand_score: 55,
      installed_mw: 0, potential_mw: 42000, grid_distance_km: 820, population: 228624,
      demand_mw: 68, peak_demand: 94, status: 'optimal', data_source: 'NASA_POWER',
      communes: 10, best_zones: ['In Salah', 'In Amguel', 'Tamanrasset Centre']
    },
    {
      code: '37', name: 'Illizi', region: 'Sahara', climate: 'BWh', lat: 26.49, lon: 8.47,
      ghi: 2380, dni: 2650, dhi: 390, t2m: 27.1, t2m_max: 41.3, t2m_min: 12.8,
      ws10m: 5.2, rh2m: 16.4, clearness_kt: 0.72,
      score: 91, solar_score: 96, stability_score: 88, terrain_score: 85, grid_score: 38, demand_score: 48,
      installed_mw: 0, potential_mw: 38000, grid_distance_km: 950, population: 68170,
      demand_mw: 24, peak_demand: 31, status: 'optimal', data_source: 'NASA_POWER',
      communes: 6, best_zones: ['Djanet', 'In Amenas', 'Bordj Omar Driss']
    },
    {
      code: '08', name: 'Béchar', region: 'Sahara', climate: 'BWk', lat: 31.62, lon: -2.22,
      ghi: 2210, dni: 2480, dhi: 380, t2m: 22.8, t2m_max: 38.2, t2m_min: 8.1,
      ws10m: 4.1, rh2m: 26.3, clearness_kt: 0.68,
      score: 87, solar_score: 91, stability_score: 84, terrain_score: 82, grid_score: 62, demand_score: 65,
      installed_mw: 82, potential_mw: 28000, grid_distance_km: 420, population: 272697,
      demand_mw: 184, peak_demand: 241, status: 'high_potential', data_source: 'NASA_POWER',
      communes: 22, best_zones: ['Bechar Centre', 'Taghit', 'Abadla']
    },
    {
      code: '32', name: 'El Bayadh', region: 'Atlas Saharien', climate: 'BSk', lat: 33.68, lon: 1.01,
      ghi: 2050, dni: 2280, dhi: 360, t2m: 16.4, t2m_max: 33.1, t2m_min: 1.2,
      ws10m: 5.8, rh2m: 34.1, clearness_kt: 0.63,
      score: 83, solar_score: 87, stability_score: 80, terrain_score: 75, grid_score: 68, demand_score: 58,
      installed_mw: 24, potential_mw: 18000, grid_distance_km: 310, population: 281000,
      demand_mw: 124, peak_demand: 168, status: 'high_potential', data_source: 'NASA_POWER',
      communes: 22, best_zones: ['El Bayadh Centre', 'Brezina', 'Rogassa']
    },
    {
      code: '03', name: 'Laghouat', region: 'Atlas Saharien', climate: 'BSh', lat: 33.80, lon: 2.86,
      ghi: 1980, dni: 2190, dhi: 345, t2m: 18.2, t2m_max: 34.8, t2m_min: 3.4,
      ws10m: 4.6, rh2m: 38.4, clearness_kt: 0.61,
      score: 81, solar_score: 85, stability_score: 78, terrain_score: 80, grid_score: 72, demand_score: 69,
      installed_mw: 45, potential_mw: 14000, grid_distance_km: 245, population: 534000,
      demand_mw: 298, peak_demand: 412, status: 'high_potential', data_source: 'NASA_POWER',
      communes: 24, best_zones: ['Laghouat Centre', 'Aflou', 'Oued Morra']
    },
    {
      code: '30', name: 'Ouargla', region: 'Sahara', climate: 'BWh', lat: 31.95, lon: 5.32,
      ghi: 2280, dni: 2510, dhi: 405, t2m: 24.6, t2m_max: 39.4, t2m_min: 10.8,
      ws10m: 3.9, rh2m: 22.1, clearness_kt: 0.70,
      score: 89, solar_score: 94, stability_score: 86, terrain_score: 84, grid_score: 71, demand_score: 74,
      installed_mw: 156, potential_mw: 32000, grid_distance_km: 285, population: 664000,
      demand_mw: 412, peak_demand: 568, status: 'optimal', data_source: 'NASA_POWER',
      communes: 21, best_zones: ['Ouargla Centre', 'Hassi Messaoud', 'Ngoussa']
    },
    {
      code: '47', name: 'Ghardaïa', region: 'Sahara', climate: 'BWh', lat: 32.49, lon: 3.67,
      ghi: 2190, dni: 2410, dhi: 390, t2m: 23.1, t2m_max: 38.7, t2m_min: 8.9,
      ws10m: 3.7, rh2m: 24.8, clearness_kt: 0.67,
      score: 86, solar_score: 92, stability_score: 84, terrain_score: 78, grid_score: 75, demand_score: 71,
      installed_mw: 68, potential_mw: 22000, grid_distance_km: 210, population: 420000,
      demand_mw: 264, peak_demand: 358, status: 'optimal', data_source: 'NASA_POWER',
      communes: 13, best_zones: ['Ghardaia Centre', 'El Atteuf', 'Metlili']
    },
    {
      code: '07', name: 'Biskra', region: 'Sahara', climate: 'BWh', lat: 34.85, lon: 5.73,
      ghi: 2060, dni: 2290, dhi: 368, t2m: 22.8, t2m_max: 37.4, t2m_min: 9.1,
      ws10m: 4.2, rh2m: 35.6, clearness_kt: 0.63,
      score: 82, solar_score: 88, stability_score: 81, terrain_score: 76, grid_score: 79, demand_score: 78,
      installed_mw: 98, potential_mw: 16000, grid_distance_km: 148, population: 789000,
      demand_mw: 486, peak_demand: 648, status: 'high_potential', data_source: 'NASA_POWER',
      communes: 33, best_zones: ['Biskra Centre', 'Tolga', 'Sidi Okba']
    },
    {
      code: '29', name: 'Mascara', region: 'Nord-Ouest', climate: 'Csa', lat: 35.39, lon: 0.14,
      ghi: 1780, dni: 1950, dhi: 340, t2m: 17.4, t2m_max: 32.1, t2m_min: 4.2,
      ws10m: 3.2, rh2m: 52.3, clearness_kt: 0.55,
      score: 68, solar_score: 72, stability_score: 71, terrain_score: 65, grid_score: 82, demand_score: 77,
      installed_mw: 12, potential_mw: 4800, grid_distance_km: 88, population: 840000,
      demand_mw: 562, peak_demand: 742, status: 'moderate', data_source: 'NASA_POWER',
      communes: 47, best_zones: ['Mascara Centre', 'Mohammadia', 'Ain Fekan']
    },
    {
      code: '16', name: 'Alger', region: 'Nord', climate: 'Csa', lat: 36.74, lon: 3.06,
      ghi: 1640, dni: 1780, dhi: 318, t2m: 17.9, t2m_max: 29.8, t2m_min: 7.4,
      ws10m: 3.1, rh2m: 64.2, clearness_kt: 0.51,
      score: 58, solar_score: 62, stability_score: 68, terrain_score: 48, grid_score: 96, demand_score: 98,
      installed_mw: 0, potential_mw: 800, grid_distance_km: 0, population: 3900000,
      demand_mw: 4280, peak_demand: 5840, status: 'limited', data_source: 'NASA_POWER',
      communes: 57, best_zones: ['Bab Ezzouar', 'Baraki', 'Rouiba']
    },
    {
      code: '31', name: 'Oran', region: 'Nord-Ouest', climate: 'Csa', lat: 35.69, lon: -0.63,
      ghi: 1720, dni: 1880, dhi: 328, t2m: 17.6, t2m_max: 30.8, t2m_min: 6.8,
      ws10m: 5.6, rh2m: 62.1, clearness_kt: 0.53,
      score: 62, solar_score: 66, stability_score: 72, terrain_score: 52, grid_score: 93, demand_score: 95,
      installed_mw: 8, potential_mw: 1200, grid_distance_km: 5, population: 1850000,
      demand_mw: 1840, peak_demand: 2480, status: 'limited', data_source: 'NASA_POWER',
      communes: 26, best_zones: ['Ain Turk', 'Bir El Djir', 'Arzew']
    },
    {
      code: '04', name: 'Oum El Bouaghi', region: 'Nord-Est', climate: 'BSk', lat: 35.87, lon: 7.11,
      ghi: 1820, dni: 2040, dhi: 344, t2m: 15.8, t2m_max: 31.2, t2m_min: 2.1,
      ws10m: 4.8, rh2m: 48.6, clearness_kt: 0.57,
      score: 72, solar_score: 78, stability_score: 75, terrain_score: 70, grid_score: 81, demand_score: 74,
      installed_mw: 18, potential_mw: 6200, grid_distance_km: 92, population: 710000,
      demand_mw: 374, peak_demand: 512, status: 'moderate', data_source: 'NASA_POWER',
      communes: 29, best_zones: ['Ain Beida', 'Ksar Sbahi', 'Sigus']
    },
    {
      code: '01', name: 'Adrar', region: 'Sahara', climate: 'BWh', lat: 27.87, lon: -0.29,
      ghi: 2420, dni: 2690, dhi: 408, t2m: 27.2, t2m_max: 41.8, t2m_min: 13.4,
      ws10m: 5.1, rh2m: 19.8, clearness_kt: 0.73,
      score: 92, solar_score: 97, stability_score: 90, terrain_score: 86, grid_score: 42, demand_score: 52,
      installed_mw: 12, potential_mw: 39000, grid_distance_km: 760, population: 450000,
      demand_mw: 156, peak_demand: 210, status: 'optimal', data_source: 'NASA_POWER',
      communes: 28, best_zones: ['Adrar Centre', 'Timimoun', 'Reggane']
    },
    {
      code: '11', name: 'Tamanrasset Sud', region: 'Sahara', climate: 'BWh', lat: 20.12, lon: 4.38,
      ghi: 2520, dni: 2780, dhi: 420, t2m: 29.8, t2m_max: 44.2, t2m_min: 16.1,
      ws10m: 5.4, rh2m: 14.8, clearness_kt: 0.76,
      score: 96, solar_score: 99, stability_score: 94, terrain_score: 82, grid_score: 28, demand_score: 41,
      installed_mw: 0, potential_mw: 55000, grid_distance_km: 1200, population: 38000,
      demand_mw: 18, peak_demand: 26, status: 'optimal', data_source: 'synthetic',
      communes: 4, best_zones: ['In Guezzam', 'Tinzaouatine']
    },
    {
      code: '22', name: 'Sidi Bel Abbès', region: 'Nord-Ouest', climate: 'Csa', lat: 35.19, lon: -0.63,
      ghi: 1760, dni: 1930, dhi: 332, t2m: 17.1, t2m_max: 31.4, t2m_min: 4.8,
      ws10m: 3.4, rh2m: 54.8, clearness_kt: 0.55,
      score: 65, solar_score: 69, stability_score: 68, terrain_score: 62, grid_score: 85, demand_score: 78,
      installed_mw: 6, potential_mw: 3200, grid_distance_km: 72, population: 604000,
      demand_mw: 384, peak_demand: 508, status: 'moderate', data_source: 'NASA_POWER',
      communes: 52, best_zones: ['Sidi Bel Abbes Centre', 'Telagh', 'Tessala']
    },
    {
      code: '05', name: 'Batna', region: 'Nord-Est', climate: 'Csa', lat: 35.56, lon: 6.17,
      ghi: 1870, dni: 2080, dhi: 348, t2m: 15.4, t2m_max: 31.8, t2m_min: 1.4,
      ws10m: 3.8, rh2m: 50.2, clearness_kt: 0.58,
      score: 73, solar_score: 79, stability_score: 74, terrain_score: 72, grid_score: 84, demand_score: 82,
      installed_mw: 28, potential_mw: 7400, grid_distance_km: 114, population: 1320000,
      demand_mw: 684, peak_demand: 918, status: 'moderate', data_source: 'NASA_POWER',
      communes: 61, best_zones: ['Timgad', 'Menaa', 'N Gaous']
    },
  ],

  // Monthly averages per wilaya (GHI, DNI, T2M, WS10M, demand, clearness)
  monthlyTimeSeries: {
    labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'],
    tamanrasset: {
      ghi:       [228, 238, 268, 278, 292, 308, 318, 314, 284, 252, 218, 204],
      dni:       [280, 290, 318, 322, 338, 362, 376, 368, 332, 296, 258, 240],
      t2m:       [14.2, 16.8, 21.4, 26.8, 31.2, 34.8, 37.2, 36.4, 31.8, 25.6, 19.2, 14.8],
      ws10m:     [4.2, 4.8, 5.2, 5.6, 5.4, 4.8, 4.2, 4.0, 4.4, 4.6, 4.4, 4.0],
      demand:    [48, 52, 58, 68, 76, 88, 94, 91, 72, 64, 54, 50],
      clearness: [0.72, 0.74, 0.75, 0.76, 0.77, 0.78, 0.77, 0.76, 0.74, 0.72, 0.70, 0.68]
    },
    ouargla: {
      ghi:       [192, 210, 248, 268, 282, 298, 308, 302, 268, 234, 196, 178],
      dni:       [240, 258, 296, 316, 328, 348, 362, 354, 316, 278, 238, 218],
      t2m:       [10.8, 13.4, 18.2, 22.8, 27.4, 31.2, 34.8, 33.6, 28.4, 21.8, 14.8, 11.2],
      ws10m:     [3.4, 3.8, 4.2, 4.4, 4.2, 3.8, 3.4, 3.2, 3.6, 3.8, 3.6, 3.2],
      demand:    [312, 328, 368, 412, 448, 498, 568, 548, 468, 412, 348, 322],
      clearness: [0.68, 0.70, 0.72, 0.74, 0.75, 0.76, 0.76, 0.75, 0.73, 0.70, 0.67, 0.65]
    },
    alger: {
      ghi:       [98, 118, 158, 192, 218, 238, 248, 238, 198, 158, 112, 92],
      dni:       [118, 142, 188, 232, 262, 284, 294, 282, 238, 186, 132, 108],
      t2m:       [10.2, 11.4, 13.8, 16.4, 19.8, 23.2, 26.4, 26.8, 23.4, 19.2, 14.8, 11.4],
      ws10m:     [3.2, 3.4, 3.6, 3.4, 3.2, 3.0, 2.8, 2.8, 3.0, 3.2, 3.4, 3.2],
      demand:    [3680, 3820, 3640, 3480, 3520, 3840, 4280, 4120, 3680, 3480, 3780, 4240],
      clearness: [0.42, 0.46, 0.52, 0.56, 0.58, 0.60, 0.61, 0.60, 0.57, 0.52, 0.46, 0.40]
    }
  },

  // Typical day irradiance profile by climate zone and season (W/m²)
  hourlyProfile: {
    labels: Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`),
    sahara_summer: [0, 0, 0, 0, 0, 30, 180, 380, 560, 720, 840, 920, 940, 900, 820, 700, 520, 340, 160, 40, 0, 0, 0, 0],
    sahara_winter: [0, 0, 0, 0, 0, 0, 80, 260, 460, 620, 740, 800, 820, 780, 700, 580, 420, 240, 80, 10, 0, 0, 0, 0],
    north_summer:  [0, 0, 0, 0, 0, 28, 148, 328, 488, 628, 728, 800, 812, 770, 692, 572, 432, 278, 128, 28, 0, 0, 0, 0],
    north_winter:  [0, 0, 0, 0, 0, 0, 48, 188, 348, 488, 588, 648, 662, 622, 548, 442, 308, 158, 38, 0, 0, 0, 0, 0, 0]
  },

  forecastData: {
    models: [
      {
        id: 'patchtst', name: 'PatchTST', type: 'Transformer', status: 'thesis',
        mae: 0.0445, rmse: 0.0563, mape: 4.45, r2: 0.9870, training_time: '1.2h', params: '1.2M',
        description: 'Patch-based self-supervised learning for time-series — Thesis Model'
      },
      {
        id: 'tft', name: 'TFT', type: 'Transformer', status: 'available',
        mae: 0.1602, rmse: 0.2610, mape: 16.02, r2: 0.7200, training_time: '2.8h', params: '2.1M',
        description: 'Temporal Fusion Transformer production-ready'
      },
      {
        id: 'nhits', name: 'N-HiTS', type: 'MLP-Based', status: 'available',
        mae: 0.0076, rmse: 0.0206, mape: 0.76, r2: 0.9983, training_time: '0.9h', params: '0.8M',
        description: 'Neural hierarchical interpolation for time series forecasting'
      },
      {
        id: 'vmd_patchtst', name: 'VMD-PatchTST', type: 'Transformer', status: 'thesis',
        mae: 0.0390, rmse: 0.0521, mape: 3.90, r2: 0.9900, training_time: '1.8h', params: '1.5M',
        description: 'VMD-decomposed PatchTST for enhanced solar irradiance forecasting'
      },
      {
        id: 'mlp_vmd', name: 'MLP_VMD', type: 'MLP-Based', status: 'available',
        mae: 0.8819, rmse: 1.1980, mape: 88.19, r2: 0.9848, training_time: '0.5h', params: '0.3M',
        description: 'Multi-layer Perceptron with VMD decomposition'
      },
      {
        id: 'residualmlp_vmd', name: 'ResidualMLP_VMD', type: 'MLP-Based', status: 'available',
        mae: 0.2631, rmse: 0.3814, mape: 26.31, r2: 0.9985, training_time: '0.7h', params: '0.4M',
        description: 'Residual MLP with VMD decomposition'
      },
      {
        id: 'random_forest_vmd', name: 'RandomForest_VMD', type: 'Ensemble', status: 'available',
        mae: 0.3944, rmse: 0.8827, mape: 39.44, r2: 0.9917, training_time: '0.3h', params: 'N/A',
        description: 'Random Forest with VMD decomposition'
      },
      {
        id: 'gradient_boosting_vmd', name: 'GradientBoosting_VMD', type: 'Ensemble', status: 'available',
        mae: 0.2243, rmse: 0.4553, mape: 22.43, r2: 0.9978, training_time: '0.4h', params: 'N/A',
        description: 'Gradient Boosting with VMD decomposition'
      },
      {
        id: 'xgboost', name: 'XGBoost', type: 'Ensemble', status: 'available',
        mae: 0.2916, rmse: 0.5611, mape: 29.16, r2: 0.9967, training_time: '0.5h', params: 'N/A',
        description: 'Extreme Gradient Boosting'
      },
      {
        id: 'lightgbm', name: 'LightGBM', type: 'Ensemble', status: 'available',
        mae: 0.2508, rmse: 0.3618, mape: 25.08, r2: 0.9986, training_time: '0.6h', params: 'N/A',
        description: 'Light Gradient Boosting Machine'
      },
      {
        id: 'tabnet', name: 'TabNet', type: 'Neural Network', status: 'available',
        mae: 0.6678, rmse: 0.8598, mape: 66.78, r2: 0.9922, training_time: '1.8h', params: '2.5M',
        description: 'Deep neural network with sequential attention'
      },
      {
        id: 'stacking_ensemble', name: 'Stacking Ensemble', type: 'Ensemble', status: 'available',
        mae: 0.2737, rmse: 0.4562, mape: 27.37, r2: 0.9978, training_time: '2.2h', params: 'N/A',
        description: 'Stacked ensemble of multiple models'
      },
      {
        id: 'gcn', name: 'GCN', type: 'Graph Neural Network', status: 'experimental',
        mae: 22.1370, rmse: 23.5168, mape: 2213.70, r2: -4.8705, training_time: '3.2h', params: '5.1M',
        description: 'Graph Convolutional Network for spatial-temporal data'
      }
    ],
    variables: ['GHI', 'DNI', 'DHI', 'T2M', 'WS10M', 'demand_mw', 'CLEARNESS_KT'],
    horizons: ['24h', '48h', '7j', '14j', '30j'],

    // 30-day sample with confidence intervals
    forecast30d: {
      labels: Array.from({ length: 30 }, (_, i) => {
        const d = new Date(2025, 5, 1 + i);
        return `${d.getDate()}/${d.getMonth() + 1}`;
      }),
      actual:    [284, 278, 292, 308, 318, 314, 288, 276, 292, 310, 322, 316, 294, 278, 284, 302, 318, 324, 306, 288, 276, 292, 308, 320, 314, 296, 280, 294, 310, 322],
      predicted: [281, 275, 289, 312, 321, 318, 291, 274, 290, 314, 318, 320, 298, 275, 282, 306, 315, 326, 309, 285, 278, 295, 310, 316, 318, 292, 283, 296, 312, 324],
      lower_ci:  [268, 262, 276, 296, 306, 304, 278, 261, 277, 298, 304, 306, 285, 262, 269, 292, 301, 312, 295, 272, 265, 281, 295, 302, 304, 278, 270, 282, 298, 310],
      upper_ci:  [294, 288, 302, 328, 336, 332, 304, 287, 303, 330, 332, 334, 311, 288, 295, 320, 329, 340, 323, 298, 291, 309, 325, 330, 332, 306, 296, 310, 326, 338],
    }
  },

  zones: [
    {
      id: 'z001', wilaya: 'Tamanrasset', name: 'In Amguel Sud', lat: 22.14, lon: 5.68,
      area_km2: 280, ghi: 2510, dni: 2780, clearness_kt: 0.77,
      score: 96, solar_score: 99, stability_score: 94, terrain_score: 91, grid_score: 32, demand_score: 48,
      elevation: 1420, terrain_type: 'flat', grid_dist_km: 890, road_dist_km: 180,
      risk_seismic: 'low', risk_flood: 'low', risk_sand: 'medium', risk_political: 'low',
      land_status: 'public', data_source: 'NASA_POWER',
      recommendation: 'build', potential_mw: 2400,
      rationale: ['GHI > 2500 kWh/m²/an — classe mondiale', 'Terrain plat sans obstacles', 'Risques naturels minimaux', 'Espace disponible >250 km²']
    },
    {
      id: 'z002', wilaya: 'Ouargla', name: 'Hassi Messaoud Zone Est', lat: 31.68, lon: 6.12,
      area_km2: 180, ghi: 2310, dni: 2540, clearness_kt: 0.71,
      score: 91, solar_score: 95, stability_score: 88, terrain_score: 85, grid_score: 78, demand_score: 82,
      elevation: 148, terrain_type: 'flat', grid_dist_km: 48, road_dist_km: 22,
      risk_seismic: 'low', risk_flood: 'low', risk_sand: 'medium', risk_political: 'low',
      land_status: 'industrial', data_source: 'NASA_POWER',
      recommendation: 'build', potential_mw: 1800,
      rationale: ['Proximité réseau HT existant (48 km)', 'GHI excellent pour Sahara Nord', 'Zone industrielle — usage énergétique fort', 'Infrastructures pétrolières existantes']
    },
    {
      id: 'z003', wilaya: 'Adrar', name: 'Timimoun Plain', lat: 29.24, lon: 0.23,
      area_km2: 340, ghi: 2460, dni: 2720, clearness_kt: 0.74,
      score: 93, solar_score: 97, stability_score: 92, terrain_score: 90, grid_score: 41, demand_score: 44,
      elevation: 282, terrain_type: 'flat', grid_dist_km: 640, road_dist_km: 14,
      risk_seismic: 'low', risk_flood: 'low', risk_sand: 'high', risk_political: 'low',
      land_status: 'public', data_source: 'NASA_POWER',
      recommendation: 'study', potential_mw: 3200,
      rationale: ['GHI exceptionnel 2460 kWh/m²/an', 'Terrain idéal sur 340 km²', 'Éloignement réseau = investissement infra requis', 'Risque ensablement à mitiger']
    },
    {
      id: 'z004', wilaya: 'Béchar', name: 'Béchar Nord Industrial', lat: 31.89, lon: -2.18,
      area_km2: 95, ghi: 2240, dni: 2490, clearness_kt: 0.69,
      score: 88, solar_score: 91, stability_score: 86, terrain_score: 80, grid_score: 71, demand_score: 76,
      elevation: 782, terrain_type: 'semi-flat', grid_dist_km: 12, road_dist_km: 8,
      risk_seismic: 'low', risk_flood: 'low', risk_sand: 'medium', risk_political: 'low',
      land_status: 'public', data_source: 'NASA_POWER',
      recommendation: 'build', potential_mw: 820,
      rationale: ['Connexion réseau à 12 km seulement', 'GHI très favorable', 'Zone industrielle disponible', 'Logistique accessible']
    },
    {
      id: 'z005', wilaya: 'Laghouat', name: 'Aflou Heights', lat: 34.12, lon: 2.09,
      area_km2: 62, ghi: 2010, dni: 2230, clearness_kt: 0.62,
      score: 79, solar_score: 83, stability_score: 77, terrain_score: 74, grid_score: 81, demand_score: 73,
      elevation: 1441, terrain_type: 'highland', grid_dist_km: 24, road_dist_km: 12,
      risk_seismic: 'medium', risk_flood: 'low', risk_sand: 'low', risk_political: 'low',
      land_status: 'agricultural', data_source: 'estimated',
      recommendation: 'study', potential_mw: 480,
      rationale: ['Altitude élevée améliore refroidissement panneaux', 'Réseau HT accessible', 'Terrain agricole — étude foncière requise', 'Sismicité modérée à surveiller']
    },
  ],

  equipment: {
    panels: [
      {
        id: 'pv001', name: 'LONGi Hi-MO 6', brand: 'LONGi', power_wp: 580, efficiency: 22.0,
        type: 'Monocrystallin PERC', temp_coeff: -0.29, warranty_years: 25, price_usd: 142,
        suitable_for: ['desert', 'standard'], recommended: true, data_source: 'measured'
      },
      {
        id: 'pv002', name: 'JA Solar JAM72', brand: 'JA Solar', power_wp: 545, efficiency: 21.1,
        type: 'Monocrystallin', temp_coeff: -0.35, warranty_years: 25, price_usd: 128,
        suitable_for: ['standard'], recommended: false, data_source: 'measured'
      },
      {
        id: 'pv003', name: 'Trina Vertex S+', brand: 'Trina', power_wp: 595, efficiency: 22.5,
        type: 'Monocrystallin TOPCon', temp_coeff: -0.28, warranty_years: 30, price_usd: 168,
        suitable_for: ['desert', 'high_temp'], recommended: true, data_source: 'measured'
      },
      {
        id: 'pv004', name: 'Canadian Solar HiKu7', brand: 'Canadian Solar', power_wp: 620, efficiency: 21.8,
        type: 'Monocrystallin', temp_coeff: -0.34, warranty_years: 25, price_usd: 152,
        suitable_for: ['large_scale'], recommended: false, data_source: 'measured'
      },
    ],
    inverters: [
      {
        id: 'inv001', name: 'SMA Sunny Central 2750', brand: 'SMA', power_kw: 2750, efficiency: 98.7,
        type: 'Central', cooling: 'Air', warranty_years: 5, price_usd: 48000,
        suitable_for: ['large_scale', 'utility'], recommended: true, data_source: 'measured'
      },
      {
        id: 'inv002', name: 'Huawei SUN2000-100KTL', brand: 'Huawei', power_kw: 100, efficiency: 99.0,
        type: 'String', cooling: 'Natural', warranty_years: 10, price_usd: 6800,
        suitable_for: ['commercial', 'utility'], recommended: true, data_source: 'measured'
      },
      {
        id: 'inv003', name: 'ABB PVS-250', brand: 'ABB', power_kw: 250, efficiency: 98.4,
        type: 'Central', cooling: 'Air', warranty_years: 5, price_usd: 18400,
        suitable_for: ['utility'], recommended: false, data_source: 'measured'
      },
    ],
    storage: [
      {
        id: 'bat001', name: 'Tesla Megapack 2', brand: 'Tesla', capacity_mwh: 3.9, power_mw: 1.5,
        chemistry: 'LFP', cycles: 6000, warranty_years: 10, price_usd_kwh: 280,
        suitable_for: ['grid_scale', 'utility'], recommended: true, data_source: 'estimated'
      },
      {
        id: 'bat002', name: 'BYD Battery-Box Premium', brand: 'BYD', capacity_mwh: 0.1024, power_mw: 0.05,
        chemistry: 'LFP', cycles: 8000, warranty_years: 10, price_usd_kwh: 240,
        suitable_for: ['commercial'], recommended: false, data_source: 'measured'
      },
    ],
    trackers: [
      {
        id: 'tr001', name: 'NEXTracker NX Horizon', brand: 'NEXTracker', gain_pct: 25,
        type: '1-axis', availability: 99.5, price_usd_w: 0.08, recommended: true
      },
      {
        id: 'tr002', name: 'GameChange GCI', brand: 'GameChange', gain_pct: 22,
        type: '1-axis', availability: 99.2, price_usd_w: 0.07, recommended: false
      },
    ]
  },

  roiScenarios: {
    conservative: {
      label: 'Conservateur', color: '#6b7280',
      capex_per_mw: 680000, opex_per_mw_yr: 12000,
      tariff_usd_kwh: 0.028, degradation_pct: 0.6,
      financing_rate: 8.5, equity_pct: 30, debt_pct: 70,
      npv: 12800000, irr: 9.2, payback: 14.2, lcoe: 0.031
    },
    base: {
      label: 'Base', color: '#f59e0b',
      capex_per_mw: 620000, opex_per_mw_yr: 10000,
      tariff_usd_kwh: 0.034, degradation_pct: 0.5,
      financing_rate: 7.0, equity_pct: 30, debt_pct: 70,
      npv: 22400000, irr: 13.8, payback: 11.4, lcoe: 0.026
    },
    optimistic: {
      label: 'Optimiste', color: '#22c55e',
      capex_per_mw: 560000, opex_per_mw_yr: 8500,
      tariff_usd_kwh: 0.042, degradation_pct: 0.4,
      financing_rate: 5.5, equity_pct: 30, debt_pct: 70,
      npv: 38600000, irr: 19.4, payback: 8.8, lcoe: 0.021
    }
  },

  nationalStats: {
    total_solar_potential_twh: 5.2e6,
    installed_capacity_mw: 742,
    pipeline_mw: 4800,
    target_2030_mw: 22000,
    avg_ghi: 2050,
    coverage_pct: 3.4,
    sahara_pct: 84,
    top_wilaya: 'Tamanrasset',
    wilayas_analyzed: 48,
    communes_analyzed: 1541,
    data_period: '2000-2024',
    last_updated: '2025-03'
  },

  offlinePacks: [
    {
      id: 'pk001', wilaya: 'Tamanrasset', size_mb: 284, version: '2025.03', status: 'available',
      includes: ['Solar GHI/DNI 25ans', 'Carte topo offline', 'Profils communes', 'Modèles ML']
    },
    {
      id: 'pk002', wilaya: 'Ouargla', size_mb: 312, version: '2025.03', status: 'downloaded',
      downloaded_at: '2025-03-12', includes: ['Solar GHI/DNI 25ans', 'Carte topo offline', 'Profils communes']
    },
    {
      id: 'pk003', wilaya: 'Adrar', size_mb: 248, version: '2025.03', status: 'available',
      includes: ['Solar GHI/DNI 25ans', 'Carte topo offline', 'Profils communes', 'Modèles ML']
    },
    {
      id: 'pk004', wilaya: 'Béchar', size_mb: 298, version: '2025.03', status: 'updating',
      includes: ['Solar GHI/DNI 25ans', 'Carte topo offline', 'Profils communes']
    },
    {
      id: 'pk005', wilaya: 'Ghardaïa', size_mb: 268, version: '2025.03', status: 'available',
      includes: ['Solar GHI/DNI 25ans', 'Carte topo offline', 'Profils communes']
    },
    {
      id: 'pk006', wilaya: 'Illizi', size_mb: 224, version: '2025.02', status: 'outdated',
      includes: ['Solar GHI/DNI 25ans', 'Carte topo offline']
    },
    {
      id: 'pk007', wilaya: 'El Bayadh', size_mb: 242, version: '2025.03', status: 'available',
      includes: ['Solar GHI/DNI 25ans', 'Carte topo offline', 'Profils communes']
    },
    {
      id: 'pk008', wilaya: 'Biskra', size_mb: 256, version: '2025.03', status: 'downloaded',
      downloaded_at: '2025-03-08', includes: ['Solar GHI/DNI 25ans', 'Carte topo offline', 'Profils communes', 'Modèles ML']
    },
  ],

  dataSources: [
    {
      id: 'ds001', name: 'NASA POWER', type: 'measured', coverage: '48 wilayas',
      period: '1981-2024', resolution: '0.5°×0.5°', variables: ['GHI', 'DNI', 'DHI', 'T2M', 'WS10M', 'RH2M'],
      status: 'active', records: 18540000, reliability: 97.2,
      url: 'https://power.larc.nasa.gov', license: 'Open'
    },
    {
      id: 'ds002', name: 'Meteonorm 8', type: 'estimated', coverage: '28 stations',
      period: '1991-2020', resolution: 'Station', variables: ['GHI', 'DNI', 'T2M'],
      status: 'active', records: 2840000, reliability: 94.8,
      url: 'https://meteonorm.com', license: 'Commercial'
    },
    {
      id: 'ds003', name: 'PVGIS 5.2', type: 'estimated', coverage: '48 wilayas',
      period: '2005-2020', resolution: '0.05°×0.05°', variables: ['GHI', 'DNI', 'PVOUT'],
      status: 'active', records: 8240000, reliability: 96.1,
      url: 'https://re.jrc.ec.europa.eu/pvg_tools', license: 'Open'
    },
    {
      id: 'ds004', name: 'Sonelgaz Demand', type: 'measured', coverage: '14 wilayas',
      period: '2015-2024', resolution: 'Wilaya', variables: ['demand_mw', 'peak_demand'],
      status: 'partial', records: 745000, reliability: 98.4,
      url: 'internal', license: 'Restricted'
    },
    {
      id: 'ds005', name: 'Synthetic GAN Model', type: 'synthetic', coverage: '6 wilayas',
      period: '2000-2024', resolution: 'Commune', variables: ['GHI', 'DNI', 'demand_mw'],
      status: 'experimental', records: 1240000, reliability: 84.2,
      url: 'internal', license: 'Research'
    },
    {
      id: 'ds006', name: 'MERRA-2 Reanalysis', type: 'estimated', coverage: '48 wilayas',
      period: '1980-2024', resolution: '0.625°×0.5°', variables: ['WS10M', 'T2M', 'RH2M', 'PRECIP_MM'],
      status: 'active', records: 22800000, reliability: 95.4,
      url: 'https://gmao.gsfc.nasa.gov/reanalysis/MERRA-2', license: 'Open'
    },
  ],

  notifications: [
    { id: 'n1', type: 'info',    title: 'Nouvelles données disponibles', msg: 'NASA POWER Q1-2025 intégré',               time: '2h', read: false },
    { id: 'n2', type: 'success', title: 'Modèle PatchTST entraîné',       msg: 'MAE 13.6 — meilleure performance',         time: '5h', read: false },
    { id: 'n3', type: 'warning', title: 'Pack Illizi obsolète',            msg: 'Mise à jour disponible (v2025.03)',        time: '1j', read: true  },
    { id: 'n4', type: 'info',    title: 'Rapport Tamanrasset généré',      msg: 'Rapport PDF prêt au téléchargement',      time: '2j', read: true  },
  ]
};

window.MOCK_DATA = MOCK_DATA;