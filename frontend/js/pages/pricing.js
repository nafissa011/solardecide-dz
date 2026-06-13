const PricingPage = {
  _loading: false,

  async render() {
    const content     = document.getElementById('page-content');
    const T           = (k) => I18N.t(k);
    const currentPlan = (window.Plan && Plan.current()) || 'free';

    // Sync the user's plan in the background so the "current" badge is always accurate
    if (window.Plan?.refresh) Plan.refresh().catch(() => {});

    content.innerHTML = `
      <div class="page-wrapper">
        <section style="text-align:center;padding:40px 16px 24px">
          <div class="hero-tag" style="margin-bottom:14px">
            <i class="fas fa-tags"></i> ${T('pricing.title')}
          </div>
          <h1 style="font-size:36px;font-weight:800;margin:0 0 10px"
              data-i18n="pricing.title">${T('pricing.title')}</h1>
          <p style="color:var(--text-secondary);font-size:15px;max-width:640px;margin:0 auto"
             data-i18n="pricing.subtitle">${T('pricing.subtitle')}</p>
          <p style="color:var(--text-muted);font-size:12px;margin-top:8px"
             data-i18n="pricing.billing_note">${T('pricing.billing_note')}</p>
        </section>

        <section style="padding:0 16px 60px;max-width:1100px;margin:0 auto">
          <div class="pricing-grid">
            ${this._renderCard('free',       currentPlan, T)}
            ${this._renderCard('pro',        currentPlan, T)}
            ${this._renderCard('enterprise', currentPlan, T)}
          </div>
          <div style="margin-top:42px;text-align:center;color:var(--text-muted);font-size:12px">
            <i class="fas fa-shield-alt" style="margin-right:6px"></i>
            ${T('pricing.compare_plans')}
          </div>
        </section>
      </div>
    `;
  },

  _renderCard(plan, currentPlan, T) {
    const price = { free: '0', pro: '4 000', enterprise: '7 000' }[plan];

    const heading = {
      free:       T('pricing.plan_free'),
      pro:        T('pricing.plan_pro'),
      enterprise: T('pricing.plan_enterprise'),
    }[plan];

    const desc = {
      free:       T('pricing.free_desc'),
      pro:        T('pricing.pro_desc'),
      enterprise: T('pricing.enterprise_desc'),
    }[plan];

    const popular   = plan === 'pro';
    const isCurrent = currentPlan === plan;

    const featuresHtml = this._features(plan).map(f => `
      <div class="plan-feature-row ${f.in ? 'included' : 'excluded'}">
        <i class="fas fa-${f.in ? 'check' : 'times'}"></i>
        <span>${f.label}</span>
      </div>
    `).join('');

    const cta = this._cta(plan, isCurrent, T);

    return `
      <div class="pricing-card ${popular ? 'featured' : ''}">
        ${popular ? `<div class="popular-tag">${T('pricing.popular')}</div>` : ''}
        <h3>${heading}</h3>
        <p style="color:var(--text-secondary);font-size:13px;margin:0">${desc}</p>
        <div class="price">
          <span class="amount">${price}</span>
          <span class="currency">DZD</span>
          <span class="period">${T('pricing.monthly')}</span>
        </div>
        <div class="features">${featuresHtml}</div>
        ${cta}
      </div>
    `;
  },

  // Feature matrix — each row declares availability across all three plans
  _features(plan) {
    const rows = [
      { f: 'Accueil et navigation complete',              free: true,  pro: true,  enterprise: true  },
      { f: 'Classement national des 58 wilayas',          free: true,  pro: true,  enterprise: true  },
      { f: 'Dashboard wilaya (apercu)',                   free: true,  pro: true,  enterprise: true  },
      { f: 'Export CSV du classement',                    free: false, pro: true,  enterprise: true  },
      { f: 'Analyse de zone complete',                    free: false, pro: true,  enterprise: true  },
      { f: 'Comparaison de wilayas',                      free: false, pro: true,  enterprise: true  },
      { f: 'Prevision 24h et 7 jours',                    free: false, pro: true,  enterprise: true  },
      { f: 'Calcul ROI complet',                          free: false, pro: true,  enterprise: true  },
      { f: 'Rapport investisseur PDF (avec filigrane)',   free: false, pro: true,  enterprise: false },
      { f: 'Rapport investisseur PDF (sans filigrane)',   free: false, pro: false, enterprise: true  },
      { f: 'Recommandations IA (5 / mois)',               free: false, pro: true,  enterprise: false },
      { f: 'Recommandations IA illimitees',               free: false, pro: false, enterprise: true  },
      { f: 'Historique 50 analyses',                      free: false, pro: true,  enterprise: false },
      { f: 'Historique illimite',                         free: false, pro: false, enterprise: true  },
      { f: 'Prevision 30 jours / 12 mois',                free: false, pro: false, enterprise: true  },
      { f: 'Prediction long terme 5 ans',                 free: false, pro: false, enterprise: true  },
      { f: 'Rapport gouvernemental PDF',                  free: false, pro: false, enterprise: true  },
      { f: 'Acces API avec cle',                          free: false, pro: false, enterprise: true  },
      { f: 'Export donnees brutes CSV',                   free: false, pro: false, enterprise: true  },
      { f: 'Support dedie prioritaire',                   free: false, pro: false, enterprise: true  },
    ];
    return rows.map(r => ({ label: r.f, in: r[plan] }));
  },

  // Routes the CTA button based on plan type, auth state, and whether it's already active
  _cta(plan, isCurrent, T) {
    if (isCurrent) {
      return `<button class="cta-btn ${plan} current" disabled>
                <i class="fas fa-check"></i> ${T('pricing.current')}
              </button>`;
    }
    if (plan === 'free') {
      // Send authenticated users to their profile, guests to registration
      const dest = API.isAuthenticated() ? 'profile' : 'register';
      return `<button class="cta-btn free" onclick="App.navigate('${dest}')">
                <span data-i18n="pricing.start_free">${T('pricing.start_free')}</span>
              </button>`;
    }
    if (plan === 'pro') {
      return `<button class="cta-btn pro" onclick="PricingPage.upgrade('pro')">
                <i class="fas fa-crown" style="margin-right:6px"></i>
                <span data-i18n="pricing.choose_pro">${T('pricing.choose_pro')}</span>
              </button>`;
    }
    return `<button class="cta-btn enterprise" onclick="PricingPage.contactEnterprise()">
              <i class="fas fa-envelope" style="margin-right:6px"></i>
              <span data-i18n="pricing.choose_enterprise">${T('pricing.choose_enterprise')}</span>
            </button>`;
  },

  async upgrade(plan) {
    if (this._loading) return;

    if (!API.isAuthenticated()) {
      Utils.toast('info', I18N.t('auth.login_required'), '');
      App.navigate('login');
      return;
    }

    this._loading = true;
    try {
      const headers = { 'Content-Type': 'application/json' };
      const tok = sessionStorage.getItem('auth_token');
      if (tok) headers['Authorization'] = `Bearer ${tok}`;

      const res = await fetch(`${API.BASE_URL}/upgrade-plan`, {
        method:      'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify({ plan, duration_days: 30 }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        Utils.toast('error', I18N.t('common.error'), body.message || `HTTP ${res.status}`);
        return;
      }

      const json = await res.json();

      // Patch the cached session so UI reflects the new plan without a full re-login
      try {
        const cached = JSON.parse(sessionStorage.getItem('user') || '{}');
        cached.plan            = json.data?.plan || plan;
        cached.plan_expires_at = json.data?.plan_expires_at || null;
        sessionStorage.setItem('user', JSON.stringify(cached));
      } catch (e) {
        // Silently ignore — private browsing mode blocks sessionStorage writes
      }

      if (window.Plan?.refresh) await Plan.refresh();
      Utils.toast('success', `Plan ${plan} active`, 'Simulation - paiement reel a venir');
      Components.renderAppShell();
      App.navigate('profile');
    } catch (err) {
      console.error('upgrade failed:', err);
      Utils.toast('error', I18N.t('common.error'), err.message || 'Network error');
    } finally {
      this._loading = false;
    }
  },

  contactEnterprise() {
    const subject = encodeURIComponent('SolarDecide DZ - Plan Entreprise');
    const body    = encodeURIComponent(
      'Bonjour,\n\nJe souhaite passer au plan Entreprise (7 000 DZD/mois).\n\nMerci de me recontacter.\n'
    );
    window.location.href = `mailto:contact@solardecide.dz?subject=${subject}&body=${body}`;
  },
};

window.PricingPage = PricingPage;