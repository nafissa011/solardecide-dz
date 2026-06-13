const Utils = {

  formatNumber(n, decimals = 0) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    return new Intl.NumberFormat('fr-DZ', { maximumFractionDigits: decimals }).format(n);
  },

  formatCurrency(n, currency = 'USD') {
    if (!n && n !== 0) return '—';
    if (n >= 1e9) return `$${(n/1e9).toFixed(2)}B`;
    if (n >= 1e6) return `$${(n/1e6).toFixed(1)}M`;
    if (n >= 1e3) return `$${(n/1e3).toFixed(0)}K`;
    return `$${n.toFixed(0)}`;
  },

  formatMW(n) {
    if (!n && n !== 0) return '—';
    if (n >= 1000) return `${(n/1000).toFixed(1)} GW`;
    return `${Math.round(n)} MW`;
  },

  formatGHI(n) {
    return `${this.formatNumber(n)} kWh/m²/an`;
  },

  // Always shows sign: +3.5% / -1.2%
  formatPct(n) {
    return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`;
  },

  scoreColor(score) {
    if (score >= 90) return 'var(--green-400)';
    if (score >= 75) return 'var(--amber-400)';
    if (score >= 60) return 'var(--yellow-500)';
    return 'var(--red-400)';
  },

  scoreClass(score) {
    if (score >= 90) return 'green';
    if (score >= 75) return 'amber';
    if (score >= 60) return 'yellow';
    return 'red';
  },

  scoreLabel(score) {
    if (score >= 90) return 'Exceptionnel';
    if (score >= 80) return 'Excellent';
    if (score >= 70) return 'Très bon';
    if (score >= 60) return 'Bon';
    if (score >= 50) return 'Modéré';
    return 'Faible';
  },

  statusBadge(status) {
    const map = {
      optimal:        { cls: 'badge-green', label: '✅ Optimal' },
      high_potential: { cls: 'badge-amber', label: '⚡ Fort potentiel' },
      moderate:       { cls: 'badge-blue',  label: '📊 Modéré' },
      limited:        { cls: 'badge-gray',  label: '⚠️ Limité' },
    };
    const s = map[status] || { cls: 'badge-gray', label: status };
    return `<span class="badge ${s.cls}">${s.label}</span>`;
  },

  dataBadge(source) {
    const map = {
      measured:  { cls: 'badge-measured',  icon: '✅', label: 'Mesuré' },
      estimated: { cls: 'badge-estimated', icon: '⚠️', label: 'Estimé' },
      synthetic: { cls: 'badge-synthetic', icon: '🧪', label: 'Synthétique' },
      predicted: { cls: 'badge-predicted', icon: '🤖', label: 'Prédit' },
      NASA_POWER:{ cls: 'badge-measured',  icon: '✅', label: 'NASA POWER' },
    };
    const s = map[source] || { cls: 'badge-gray', icon: '❓', label: source };
    return `<span class="badge ${s.cls}">${s.icon} ${s.label}</span>`;
  },

  modelBadge(status) {
    const map = {
      available:    'badge-green',
      unavailable:  'badge-gray',
      baseline:     'badge-baseline',
      benchmark:    'badge-benchmark',
      experimental: 'badge-experimental',
      thesis:       'badge-thesis'
    };
    const labels = {
      available:    'Disponible',
      unavailable:  'Indisponible',
      baseline:     'Baseline',
      benchmark:    'Benchmark',
      experimental: 'Expérimental',
      thesis:       '⭐ Thèse'
    };
    return `<span class="badge ${map[status] || 'badge-gray'}">${labels[status] || status}</span>`;
  },

  recoBadge(rec) {
    const map = {
      build: '<span class="badge badge-green">🟢 Construire</span>',
      study: '<span class="badge badge-blue">🔵 Étudier</span>',
      wait:  '<span class="badge badge-estimated">🟡 Attendre</span>',
    };
    return map[rec] || `<span class="badge badge-gray">${rec}</span>`;
  },

  riskBadge(level) {
    const map = {
      low:      '<span class="risk-level low">Faible</span>',
      medium:   '<span class="risk-level medium">Moyen</span>',
      high:     '<span class="risk-level high">Élevé</span>',
      critical: '<span class="risk-level critical">Critique</span>',
    };
    return map[level] || level;
  },

  // Köppen climate classification codes
  climateLabel(code) {
    const map = {
      BWh: 'Désert chaud (Sahara)',
      BWk: 'Désert froid',
      BSh: 'Semi-aride chaud',
      BSk: 'Semi-aride froid',
      Csa: 'Méditerranéen',
      Csb: 'Méditerranéen tempéré',
    };
    return map[code] || code;
  },

  formatDate(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleDateString('fr-DZ', { day: 'numeric', month: 'long', year: 'numeric' });
  },

  formatDateShort(dateStr) {
    const d = new Date(dateStr);
    return d.toLocaleDateString('fr-DZ', { day: '2-digit', month: '2-digit', year: 'numeric' });
  },

  // Shared Chart.js config — keeps all charts visually consistent
  chartDefaults() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: {
            color: '#9ca3af',
            font: { size: 12, family: 'Inter' },
            boxWidth: 12, boxHeight: 12,
            padding: 16
          }
        },
        tooltip: {
          backgroundColor: '#111827',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleColor: '#f9fafb',
          bodyColor: '#9ca3af',
          padding: 10,
          cornerRadius: 8,
          titleFont: { size: 12, weight: '600' },
          bodyFont: { size: 12 }
        }
      },
      scales: {
        x: {
          ticks: { color: '#6b7280', font: { size: 11 } },
          grid: { color: 'rgba(255,255,255,0.05)' },
          border: { color: 'rgba(255,255,255,0.1)' }
        },
        y: {
          ticks: { color: '#6b7280', font: { size: 11 } },
          grid: { color: 'rgba(255,255,255,0.05)' },
          border: { color: 'rgba(255,255,255,0.1)' }
        }
      }
    };
  },

  getMarkerColor(score) {
    if (score >= 90) return '#22c55e';
    if (score >= 75) return '#f59e0b';
    if (score >= 60) return '#3b82f6';
    return '#6b7280';
  },

  circleMarkerOptions(score, selected = false) {
    const color = this.getMarkerColor(score);
    return {
      radius: selected ? 12 : 8,
      fillColor: color,
      color: selected ? '#fff' : color,
      weight: selected ? 3 : 1,
      opacity: 1,
      fillOpacity: selected ? 0.9 : 0.7
    };
  },

  // SVG rotated -90deg so the arc starts at 12 o'clock
  scoreRingSVG(score, color = '#f59e0b', size = 80) {
    const r = (size/2) - 8;
    const circumference = 2 * Math.PI * r;
    const dashOffset = circumference * (1 - score/100);
    return `
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="6"/>
        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${color}" stroke-width="6"
          stroke-linecap="round" stroke-dasharray="${circumference}" stroke-dashoffset="${dashOffset}"
          style="transition: stroke-dashoffset 1s ease;"/>
      </svg>
      <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-size:${size*0.22}px;font-weight:700;color:#f9fafb;">${score}</div>
    `;
  },

  skeletonHTML(type = 'card') {
    const skeletons = {
      card: `<div class="card"><div class="card-body">
        <div class="skeleton skeleton-text title"></div>
        <div class="skeleton skeleton-text"></div>
        <div class="skeleton skeleton-text short"></div>
        <div class="skeleton skeleton-chart mt-4"></div>
      </div></div>`,
      table_row: `<tr><td><div class="skeleton skeleton-text" style="width:30px"></div></td>
        <td><div class="skeleton skeleton-text" style="width:120px"></div></td>
        <td><div class="skeleton skeleton-text" style="width:80px"></div></td>
        <td><div class="skeleton skeleton-text" style="width:60px"></div></td></tr>`,
      kpi: `<div class="kpi-card"><div class="skeleton skeleton-card"></div></div>`
    };
    return skeletons[type] || skeletons.card;
  },

  toast(type, title, msg, duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = { success: 'fa-check-circle', error: 'fa-times-circle', warning: 'fa-exclamation-triangle', info: 'fa-info-circle' };
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `
      <i class="fas ${icons[type] || icons.info} toast-icon"></i>
      <div class="toast-body">
        <div class="toast-title">${title}</div>
        ${msg ? `<div class="toast-msg">${msg}</div>` : ''}
      </div>
      <button class="toast-close" onclick="this.closest('.toast').remove()"><i class="fas fa-times" style="font-size:11px"></i></button>
    `;
    container.appendChild(el);
    if (duration > 0) setTimeout(() => el.remove(), duration);
    return el;
  },

  randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  },

  debounce(fn, delay = 300) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
  },

  // JSON round-trip — intentionally drops functions and circular refs
  clone(obj) { return JSON.parse(JSON.stringify(obj)); },

  chartColors: {
    amber:  '#f59e0b',
    teal:   '#14b8a6',
    blue:   '#3b82f6',
    green:  '#22c55e',
    red:    '#ef4444',
    purple: '#8b5cf6',
    orange: '#f97316',
    pink:   '#ec4899',
    amberAlpha: (a = 0.2) => `rgba(245,158,11,${a})`,
    tealAlpha:  (a = 0.2) => `rgba(20,184,166,${a})`,
    blueAlpha:  (a = 0.2) => `rgba(59,130,246,${a})`,
    greenAlpha: (a = 0.2) => `rgba(34,197,94,${a})`,
  },

  createLineChart(canvas, labels, datasets, options = {}) {
    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: { ...this.chartDefaults(), ...options }
    });
  },

  createBarChart(canvas, labels, datasets, options = {}) {
    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets },
      options: { ...this.chartDefaults(), ...options }
    });
  },

  // Radar doesn't use the shared scale config — r-axis needs its own setup
  createRadarChart(canvas, labels, datasets) {
    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
      type: 'radar',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#9ca3af', font: { size: 11 } } },
          tooltip: {
            backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
            titleColor: '#f9fafb', bodyColor: '#9ca3af', padding: 10, cornerRadius: 8
          }
        },
        scales: {
          r: {
            ticks: { color: '#6b7280', backdropColor: 'transparent', font: { size: 10 } },
            grid: { color: 'rgba(255,255,255,0.08)' },
            angleLines: { color: 'rgba(255,255,255,0.08)' },
            pointLabels: { color: '#9ca3af', font: { size: 11 } }
          }
        }
      }
    });
  },

  capitalize(str) { return str ? str.charAt(0).toUpperCase() + str.slice(1) : str; },

  truncate(str, len = 30) { return str && str.length > len ? str.substring(0, len) + '...' : str; },
};

window.Utils = Utils;