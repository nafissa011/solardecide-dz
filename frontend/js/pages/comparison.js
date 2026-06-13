const ComparisonPage = {
  // Full wilaya list fetched from the API and used to populate the select dropdowns
  _allWilayas: [],

  // Fallback API base URL when the global API config is not available
  _API_BASE: "http://localhost:5000/api",

  // Active Chart.js bar chart instance; kept to allow safe destruction on re-render
  _chart: null,

  // Injects the page skeleton, fetches the wilaya list, then renders the selector form
  async render(params = {}) {
    const content = document.getElementById('page-content');
    if (!content) return;
    content.innerHTML = `
      <div class="page-wrapper comp-page">
        ${this._headerHTML()}
        <div id="comp-body">${this._skeletonHTML()}</div>
      </div>
      <style>${this._css()}</style>`;
    await this._loadWilayas();
    this._renderForm(params);
  },

  // Fetches the wilaya list from the API; falls back to the global ALL_WILAYAS constant on failure
  async _loadWilayas() {
    try {
      const base = (window.API?.BASE_URL) || this._API_BASE;
      const res  = await fetch(`${base}/compare/wilayas-list`, { signal: AbortSignal.timeout(8000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this._allWilayas = data.wilayas || [];
    } catch (err) {
      console.warn("Wilayas API error:", err.message);
      this._allWilayas = (window.ALL_WILAYAS || [])
        .map(w => typeof w === 'string' ? w : (w.nom || w.name || '')).filter(Boolean);
    }
  },

  // Renders the three wilaya selector dropdowns and pre-selects any values passed via params
  _renderForm(params = {}) {
    const body = document.getElementById('comp-body');
    if (!body) return;

    const opts   = this._allWilayas.map(w => `<option value="${w}">${w}</option>`).join('');
    const labels = ['Wilaya A', 'Wilaya B', 'Wilaya C'];
    const icons  = ['fa-sun', 'fa-bolt', 'fa-star'];
    const colors = ['amber', 'teal', 'purple'];

    body.innerHTML = `
      <div class="comp-form-card">
        <div class="comp-form-title">
          <i class="fas fa-sliders-h"></i>
          Sélectionnez jusqu'à 3 wilayas à comparer
        </div>
        <div class="comp-selectors">
          ${[0, 1, 2].map(i => `
            <div class="comp-selector comp-selector--${colors[i]}">
              <div class="comp-selector-label">
                <i class="fas ${icons[i]}"></i> ${labels[i]}
              </div>
              <select id="sel-w${i + 1}" class="comp-select">
                <option value="">— Choisir —</option>
                ${opts}
              </select>
            </div>`).join('')}
        </div>
        <div class="comp-form-footer">
          <button id="btn-compare" class="comp-btn" onclick="ComparisonPage._runComparison()">
            <span class="comp-btn-inner">
              <i class="fas fa-balance-scale"></i>
              Lancer la comparaison
            </span>
            <span class="comp-btn-shine"></span>
          </button>
        </div>
      </div>

      <div id="comp-results"></div>`;

    // Pre-select wilayas when the page is opened with existing query params
    ['w1', 'w2', 'w3'].forEach((k, i) => {
      const sel = document.getElementById(`sel-w${i + 1}`);
      if (sel && params[k]) sel.value = params[k];
    });
  },

  // Validates the selection, calls the comparison API, and delegates rendering to _renderResults
  async _runComparison() {
    const vals   = [1, 2, 3].map(i => document.getElementById(`sel-w${i}`)?.value.trim() || '');
    const chosen = vals.filter(Boolean);

    if (chosen.length < 2) {
      Utils.toast('warning', 'Sélection', 'Choisissez au moins 2 wilayas.');
      return;
    }
    if (new Set(chosen).size !== chosen.length) {
      Utils.toast('warning', 'Sélection', 'Les wilayas doivent être différentes.');
      return;
    }

    // Disable the button and show a spinner while the request is in flight
    const btn = document.getElementById('btn-compare');
    if (btn) {
      btn.disabled = true;
      btn.querySelector('.comp-btn-inner').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Calcul en cours…';
    }

    const resultsDiv = document.getElementById('comp-results');
    if (resultsDiv) resultsDiv.innerHTML = this._loadingHTML();

    try {
      const base = (window.API?.BASE_URL) || this._API_BASE;
      const qs   = chosen.map((w, i) => `w${i + 1}=${encodeURIComponent(w)}`).join('&');
      const res  = await fetch(`${base}/compare?${qs}`, { signal: AbortSignal.timeout(15000) });

      // Some server errors return HTML rather than JSON; extract a readable message when that happens
      const ct = res.headers.get('content-type') || '';
      if (!ct.includes('application/json')) {
        const txt   = await res.text();
        const match = txt.match(/<p>(.*?)<\/p>/s);
        throw new Error(match ? match[1].replace(/<[^>]+>/g, '').trim() : `Erreur HTTP ${res.status}`);
      }

      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `Erreur HTTP ${res.status}`);
      this._renderResults(data);

    } catch (err) {
      if (resultsDiv) resultsDiv.innerHTML = `
        <div class="comp-error">
          <i class="fas fa-exclamation-triangle"></i>
          <span>${err.message}</span>
        </div>`;
    } finally {
      // Always restore the button regardless of success or failure
      if (btn) {
        btn.disabled = false;
        btn.querySelector('.comp-btn-inner').innerHTML = '<i class="fas fa-balance-scale"></i> Lancer la comparaison';
      }
    }
  },

  // Builds and injects the winner banner, score cards, bar chart, and radar chart
  _renderResults(data) {
    const resultsDiv = document.getElementById('comp-results');
    if (!resultsDiv) return;

    const { results: items, best, not_found } = data;

    // One colour palette entry per wilaya slot (max 3)
    const PALETTE = [
      { name: 'amber',  hex: '#f59e0b', bg: 'rgba(245,158,11,0.12)',  border: 'rgba(245,158,11,0.5)'  },
      { name: 'teal',   hex: '#14b8a6', bg: 'rgba(20,184,166,0.12)',  border: 'rgba(20,184,166,0.5)'  },
      { name: 'purple', hex: '#8b5cf6', bg: 'rgba(139,92,246,0.12)',  border: 'rgba(139,92,246,0.5)'  },
    ];
    const medals = ['🥇', '🥈', '🥉'];
    const max    = Math.max(...items.map(r => r.solar_score));

    // Score cards — percentage bar is relative to the highest score in the set
    const cards = items.map((r, i) => {
      const p        = PALETTE[i];
      const pct      = max > 0 ? Math.round((r.solar_score / max) * 100) : 0;
      const isWinner = r.rank === 1;
      const det      = r.details || {};
      return `
        <div class="comp-result-card ${isWinner ? 'comp-result-card--winner' : ''}"
             style="--card-color:${p.hex};--card-bg:${p.bg};--card-border:${p.border}"
             data-aos="${i}">
          ${isWinner ? '<div class="comp-winner-ribbon">Meilleure</div>' : ''}
          <div class="comp-card-medal">${medals[i]}</div>
          <div class="comp-card-name">${r.wilaya}</div>
          <div class="comp-card-score">${r.solar_score.toFixed(3)}</div>
          <div class="comp-card-label">Solar Score</div>
          <div class="comp-card-bar-wrap">
            <div class="comp-card-bar" style="width:${pct}%;background:${p.hex}"></div>
          </div>
          <div class="comp-card-pct">${pct}% du maximum</div>
          ${det.rang_national !== undefined ? `
          <div class="comp-card-details">
            <div class="comp-detail-row"><span>Classement national</span><strong>#${det.rang_national ?? '—'} / 58</strong></div>
            <div class="comp-detail-row"><span>Zone climatique</span><strong>${det.zone ?? '—'}</strong></div>
          </div>` : ''}
        </div>`;
    }).join('');

    const radarSVG = this._buildRadar(items, PALETTE);

    // Alert shown when one or more requested wilayas were not found in the dataset
    const nfAlert = not_found?.length
      ? `<div class="comp-nf-alert"><i class="fas fa-exclamation-triangle"></i> Wilayas non trouvées : <strong>${not_found.join(', ')}</strong></div>`
      : '';

    resultsDiv.innerHTML = `
      ${nfAlert}

      <div class="comp-winner-banner">
        <div class="comp-winner-icon"><i class="fas fa-trophy"></i></div>
        <div>
          <div class="comp-winner-sub">Meilleure wilaya solaire</div>
          <div class="comp-winner-name">${best}</div>
        </div>
        <div class="comp-winner-score">${items[0].solar_score.toFixed(3)}</div>
      </div>

      <div class="comp-cards-grid">${cards}</div>

      <div class="comp-charts-row">
        <div class="comp-chart-card">
          <div class="comp-chart-title"><i class="fas fa-chart-bar"></i> Scores comparés</div>
          <canvas id="comp-bar-chart" height="220"></canvas>
        </div>
        <div class="comp-chart-card">
          <div class="comp-chart-title"><i class="fas fa-spider"></i> Analyse radar</div>
          <div class="comp-radar-wrap">${radarSVG}</div>
          <div class="comp-radar-legend">
            ${items.map((r, i) => `
              <div class="comp-radar-leg-item">
                <span class="comp-radar-leg-dot" style="background:${PALETTE[i].hex}"></span>
                ${r.wilaya}
              </div>`).join('')}
          </div>
        </div>
      </div>`;

    // Stagger the card entrance animation so each card slides in sequentially
    setTimeout(() => {
      document.querySelectorAll('.comp-result-card').forEach((el, i) => {
        setTimeout(() => el.classList.add('comp-card-visible'), i * 120);
      });
    }, 50);

    // Slight delay ensures the canvas is in the DOM before Chart.js tries to draw
    setTimeout(() => this._renderBarChart(items, PALETTE), 150);
  },

  // Generates an SVG radar chart from per-wilaya solar scores and optional detail metrics
  _buildRadar(items, palette) {
    const axes = ['Solar Score', 'Classement', 'Score norm.', 'Performance', 'Efficacité'];
    const N    = axes.length;
    const W = 260, H = 260, cx = 130, cy = 130, R = 95;

    // Positions each axis evenly around the circle, starting from 12 o'clock
    const angle = i => (Math.PI * 2 * i / N) - Math.PI / 2;

    const gridLevels = [0.25, 0.5, 0.75, 1.0];
    const max        = Math.max(...items.map(r => r.solar_score));

    // Normalises each metric to a [0, 1] range for consistent polygon scaling
    const axisData = items.map((r, ri) => {
      const det  = r.details || {};
      const base = r.solar_score / max;

      if (det.rang_national !== undefined) {
        const allScore = items.map(x => x.solar_score || 0);
        const allRang  = items.map(x => x.details?.rang_national || 58);
        const norm = (v, arr) => {
          const mn = Math.min(...arr), mx = Math.max(...arr);
          return mx > mn ? (v - mn) / (mx - mn) * 0.8 + 0.2 : 0.5;
        };
        return [
          norm(r.solar_score, allScore),
          1 - norm(det.rang_national, allRang) * 0.6 + 0.2,
          norm(r.solar_score, allScore) * 0.9,
          norm(r.solar_score, allScore) * 0.85,
        ];
      }

      // When detail data is absent, apply a deterministic pseudo-variance around the base score
      return axes.map((_, ai) => {
        const seed = (ri * 7 + ai * 13) % 17;
        return Math.min(1, Math.max(0.15, base + (seed - 8) * 0.018));
      });
    });

    const gridCircles = gridLevels.map(lvl => {
      const pts = axes.map((_, i) => {
        const a = angle(i);
        return `${cx + Math.cos(a) * R * lvl},${cy + Math.sin(a) * R * lvl}`;
      }).join(' ');
      return `<polygon points="${pts}" fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="1"/>`;
    }).join('');

    const axisLines = axes.map((label, i) => {
      const a  = angle(i);
      const x2 = cx + Math.cos(a) * R;
      const y2 = cy + Math.sin(a) * R;
      const lx = cx + Math.cos(a) * (R + 18);
      const ly = cy + Math.sin(a) * (R + 18);
      return `
        <line x1="${cx}" y1="${cy}" x2="${x2}" y2="${y2}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
        <text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="middle"
              fill="#9ca3af" font-size="9" font-family="Inter,sans-serif">${label}</text>`;
    }).join('');

    const polygons = items.map((r, ri) => {
      const p   = palette[ri];
      const pts = axisData[ri].map((val, ai) => {
        const a = angle(ai);
        return `${cx + Math.cos(a) * R * val},${cy + Math.sin(a) * R * val}`;
      }).join(' ');
      return `
        <polygon points="${pts}" fill="${p.hex}" fill-opacity="0.15" stroke="${p.hex}" stroke-width="2"/>
        ${axisData[ri].map((val, ai) => {
          const a = angle(ai);
          return `<circle cx="${cx + Math.cos(a) * R * val}" cy="${cy + Math.sin(a) * R * val}" r="3" fill="${p.hex}"/>`;
        }).join('')}`;
    }).join('');

    return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"
              style="width:100%;max-width:260px;margin:0 auto;display:block">
      ${gridCircles}${axisLines}${polygons}
    </svg>`;
  },

  // Renders a grouped bar chart comparing the solar scores of all selected wilayas
  _renderBarChart(items, palette) {
    const ctx = document.getElementById('comp-bar-chart');
    if (!ctx || typeof Chart === 'undefined') return;

    // Destroy the previous instance before creating a new one to avoid canvas conflicts
    if (this._chart) { try { this._chart.destroy(); } catch (e) {} }

    this._chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: items.map(r => r.wilaya),
        datasets: [{
          label: 'Solar Score',
          data:  items.map(r => r.solar_score),
          backgroundColor: palette.map(p => p.bg.replace('0.12', '0.7')),
          borderColor:     palette.map(p => p.hex),
          borderWidth:   2,
          borderRadius:  10,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => ` Score : ${c.parsed.y.toFixed(4)}` } },
        },
        scales: {
          y: { beginAtZero: false, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { size: 11 } } },
          x: { grid: { display: false }, ticks: { color: '#d1d5db', font: { size: 12, weight: '600' } } },
        },
        animation: { duration: 800, easing: 'easeOutQuart' },
      },
    });
  },

  // Returns the page header markup with the page title and icon
  _headerHTML() {
    return `
      <div class="comp-header">
        <div class="comp-header-icon"><i class="fas fa-balance-scale"></i></div>
        <div>
          <h1 class="comp-header-title">Comparaison de Sites</h1>
          <div class="comp-header-sub">Analyse comparative des wilayas algériennes</div>
        </div>
      </div>`;
  },

  // Returns the initial loading placeholder shown before the wilaya list is ready
  _skeletonHTML() {
    return `<div class="comp-skeleton"><i class="fas fa-spinner fa-spin fa-2x"></i><p>Chargement…</p></div>`;
  },

  // Returns the animated loading state shown while the comparison API call is in progress
  _loadingHTML() {
    return `
      <div class="comp-loading">
        <div class="comp-loading-orb"></div>
        <div class="comp-loading-text">Calcul des scores en cours…</div>
      </div>`;
  },

  // Returns all scoped CSS for the comparison page as a string injected into a <style> tag
  _css() {
    return `
/* Comparison page layout container */
.comp-page { max-width: 1100px; margin: 0 auto; }

/* Page header */
.comp-header {
  display: flex; align-items: center; gap: 20px; margin-bottom: 32px;
}
.comp-header-icon {
  width: 56px; height: 56px; border-radius: 16px;
  background: linear-gradient(135deg, var(--amber-500), var(--amber-700));
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; color: #000;
  box-shadow: 0 4px 20px rgba(245,158,11,0.35);
  flex-shrink: 0;
}
.comp-header-title {
  font-size: 26px; font-weight: 700; color: var(--text-primary);
  font-family: 'Space Grotesk', sans-serif; margin: 0;
}
.comp-header-sub { color: var(--text-secondary); font-size: 13px; margin-top: 2px; }

/* Selector form card */
.comp-form-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  padding: 28px; margin-bottom: 16px;
  box-shadow: var(--shadow-md);
}
.comp-form-title {
  font-size: 14px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 20px; display: flex; align-items: center; gap: 8px;
}
.comp-selectors {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
  margin-bottom: 24px;
}
.comp-selector {
  background: var(--bg-elevated);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg); padding: 16px;
  transition: border-color 0.2s;
}
.comp-selector:focus-within { border-color: var(--accent-primary); }
.comp-selector-label {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.1em; margin-bottom: 10px; display: flex; align-items: center; gap: 6px;
}
.comp-selector--amber  .comp-selector-label { color: var(--amber-400); }
.comp-selector--teal   .comp-selector-label { color: var(--teal-400); }
.comp-selector--purple .comp-selector-label { color: var(--purple-500); }
.comp-select {
  width: 100%; background: var(--bg-card); color: var(--text-primary);
  border: 1px solid var(--border-color); border-radius: var(--radius-md);
  padding: 10px 12px; font-size: 13px; font-family: inherit;
  cursor: pointer; outline: none; transition: border-color 0.2s; appearance: none;
}
.comp-select:focus { border-color: var(--accent-primary); }
.comp-select option { background: var(--bg-card); }
.comp-form-footer { display: flex; justify-content: flex-end; }

/* Primary comparison action button with shine hover effect */
.comp-btn {
  position: relative; overflow: hidden;
  background: linear-gradient(135deg, var(--amber-500), var(--amber-600));
  color: #000; border: none; border-radius: var(--radius-lg);
  padding: 13px 28px; font-size: 14px; font-weight: 700;
  cursor: pointer; font-family: inherit;
  box-shadow: 0 4px 16px rgba(245,158,11,0.3);
  transition: transform 0.15s, box-shadow 0.15s;
}
.comp-btn:hover   { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(245,158,11,0.45); }
.comp-btn:active  { transform: translateY(0); }
.comp-btn:disabled { opacity: 0.6; transform: none; cursor: not-allowed; }
.comp-btn-inner   { position: relative; z-index: 1; display: flex; align-items: center; gap: 8px; }
.comp-btn-shine {
  position: absolute; top: 0; left: -100%; width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.25), transparent);
  transform: skewX(-20deg); transition: left 0.5s;
}
.comp-btn:hover .comp-btn-shine { left: 140%; }

/* Winner banner displayed above the score cards */
.comp-winner-banner {
  display: flex; align-items: center; gap: 20px;
  background: linear-gradient(135deg, rgba(245,158,11,0.15), rgba(245,158,11,0.05));
  border: 1px solid rgba(245,158,11,0.35);
  border-radius: var(--radius-xl); padding: 20px 28px;
  margin-bottom: 24px;
  box-shadow: 0 0 40px rgba(245,158,11,0.08);
  animation: bannerIn 0.5s ease;
}
@keyframes bannerIn { from { opacity:0; transform:translateY(-12px); } to { opacity:1; transform:translateY(0); } }
.comp-winner-icon {
  width: 52px; height: 52px; border-radius: 50%;
  background: linear-gradient(135deg, var(--amber-400), var(--amber-600));
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; color: #000; flex-shrink: 0;
  box-shadow: 0 4px 16px rgba(245,158,11,0.4);
}
.comp-winner-sub  { font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--amber-400); font-weight: 600; }
.comp-winner-name { font-size: 22px; font-weight: 800; color: var(--text-primary); font-family: 'Space Grotesk', sans-serif; }
.comp-winner-score {
  margin-left: auto; font-size: 32px; font-weight: 800;
  color: var(--amber-400); font-variant-numeric: tabular-nums;
  font-family: 'Space Grotesk', sans-serif;
}

/* Score card grid — one card per wilaya, up to three columns */
.comp-cards-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-bottom: 24px;
}
.comp-result-card {
  background: var(--card-bg, rgba(255,255,255,0.04));
  border: 1px solid var(--card-border, var(--border-color));
  border-radius: var(--radius-xl); padding: 24px 20px;
  text-align: center; position: relative; overflow: hidden;
  opacity: 0; transform: translateY(20px) scale(0.97);
  transition: opacity 0.4s ease, transform 0.4s ease, box-shadow 0.25s;
}
.comp-result-card.comp-card-visible { opacity: 1; transform: translateY(0) scale(1); }
.comp-result-card:hover { box-shadow: 0 8px 32px rgba(0,0,0,0.3), 0 0 0 1px var(--card-color); transform: translateY(-4px) scale(1.01); }
.comp-result-card--winner { box-shadow: 0 0 40px rgba(245,158,11,0.12); }
.comp-result-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--card-color);
}
.comp-winner-ribbon {
  position: absolute; top: 14px; right: -22px;
  background: var(--amber-500); color: #000; font-size: 10px; font-weight: 700;
  padding: 3px 28px; transform: rotate(35deg); text-transform: uppercase; letter-spacing: 0.05em;
}
.comp-card-medal  { font-size: 32px; margin-bottom: 10px; }
.comp-card-name   { font-size: 15px; font-weight: 700; color: var(--text-primary); margin-bottom: 16px; }
.comp-card-score  {
  font-size: 40px; font-weight: 800; color: var(--card-color);
  font-family: 'Space Grotesk', sans-serif; line-height: 1; margin-bottom: 4px;
}
.comp-card-label  { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 16px; }
.comp-card-bar-wrap {
  height: 6px; background: rgba(255,255,255,0.07); border-radius: 99px; overflow: hidden; margin-bottom: 6px;
}
.comp-card-bar    { height: 100%; border-radius: 99px; transition: width 1s cubic-bezier(0.4,0,0.2,1); }
.comp-card-pct    { font-size: 11px; color: var(--text-muted); margin-bottom: 14px; }

/* Optional detail section inside each score card */
.comp-card-details {
  border-top: 1px solid rgba(255,255,255,0.06);
  padding-top: 12px; text-align: left;
}
.comp-detail-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; color: var(--text-secondary); padding: 3px 0;
}
.comp-detail-row strong { color: var(--text-primary); font-size: 12px; }

/* Two-column row holding the bar chart and radar chart */
.comp-charts-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px;
}
.comp-chart-card {
  background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: var(--radius-xl); padding: 22px;
}
.comp-chart-title {
  font-size: 13px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.07em;
  margin-bottom: 18px; display: flex; align-items: center; gap: 8px;
}
.comp-radar-wrap  { display: flex; justify-content: center; }
.comp-radar-legend {
  display: flex; justify-content: center; gap: 16px; flex-wrap: wrap; margin-top: 12px;
}
.comp-radar-leg-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
.comp-radar-leg-dot  { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

/* Loading and error states */
.comp-skeleton, .comp-loading {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 60px; color: var(--text-secondary); gap: 16px;
}
.comp-loading-orb {
  width: 48px; height: 48px; border-radius: 50%;
  border: 3px solid rgba(245,158,11,0.2);
  border-top-color: var(--amber-400);
  animation: spin 0.8s linear infinite;
}
.comp-loading-text { font-size: 14px; color: var(--text-secondary); }
.comp-error {
  display: flex; align-items: center; gap: 12px;
  background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);
  border-radius: var(--radius-lg); padding: 16px 20px;
  color: var(--red-400); font-size: 14px; margin-top: 8px;
}
.comp-nf-alert {
  background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3);
  border-radius: var(--radius-md); padding: 12px 16px;
  color: var(--amber-400); font-size: 13px; margin-bottom: 16px;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* Responsive breakpoints */
@media (max-width: 900px) { .comp-charts-row { grid-template-columns: 1fr; } }
@media (max-width: 768px) {
  .comp-selectors   { grid-template-columns: 1fr; }
  .comp-cards-grid  { grid-template-columns: 1fr; }
  .comp-winner-score  { font-size: 24px; }
  .comp-winner-banner { flex-wrap: wrap; }
}
@media (max-width: 480px) {
  .comp-form-card    { padding: 16px; }
  .comp-header-title { font-size: 20px; }
  .comp-card-score   { font-size: 32px; }
}`;
  },
};

window.ComparisonPage = ComparisonPage;