// Bundles: /locales/{fr,en}.json — loaded once at boot, kept in memory.
// AR is disabled (no ar.json); the AR button shows an info toast.
//
// Key format:  I18N.t('topbar.upgrade'), I18N.t('forecast.h_24h_sub')
//
// DOM translation via attributes:
//   data-i18n, data-i18n-placeholder, data-i18n-tooltip,
//   data-i18n-title, data-i18n-aria-label, data-i18n-html
// Call I18N.applyDom() after each render to propagate changes.

const I18N = {
  currentLang: 'fr',
  availableLangs: ['fr', 'en'],
  disabledLangs:  ['ar'],

  bundles: { fr: null, en: null },

  _ready: false,
  _pendingDom: false,

  // Resolves a dotted key (e.g. "topbar.upgrade") against a bundle object
  _lookup(bundle, key) {
    if (!bundle || !key) return undefined;
    const parts = key.split('.');
    let cur = bundle;
    for (const p of parts) {
      if (cur == null || typeof cur !== 'object') return undefined;
      cur = cur[p];
    }
    return (typeof cur === 'string' || typeof cur === 'number') ? cur : undefined;
  },

  // Falls back: current lang → FR → raw key
  t(key) {
    if (!key) return '';
    const lang = this.currentLang in this.bundles && this.bundles[this.currentLang]
      ? this.currentLang
      : 'fr';
    const val = this._lookup(this.bundles[lang], key);
    if (val !== undefined) return val;
    const fr = this._lookup(this.bundles.fr, key);
    return fr !== undefined ? fr : key;
  },

  async setLang(lang) {
    if (!this.availableLangs.includes(lang)) return;
    if (!this.bundles[lang]) await this.loadBundle(lang);
    this.currentLang = lang;
    document.documentElement.lang = lang;
    document.documentElement.dir = (lang === 'ar') ? 'rtl' : 'ltr';
    try { localStorage.setItem('lang', lang); } catch (e) { /* private mode */ }

    this.applyDom();

    // Re-render shell + page so inline I18N.t('...') calls also update
    if (window.Components?.renderAppShell) Components.renderAppShell();
    if (window.App?.currentPage) {
      App.navigate(App.currentPage, App.currentParams || {}, { replaceHistory: true });
    }
  },

  async loadBundle(lang) {
    if (this.bundles[lang]) return this.bundles[lang];
    try {
      const res = await fetch(`locales/${lang}.json`, { cache: 'force-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.bundles[lang] = await res.json();
      return this.bundles[lang];
    } catch (err) {
      console.warn(`[i18n] Failed to load ${lang}.json:`, err);
      this.bundles[lang] = {};
      return this.bundles[lang];
    }
  },

  applyDom(root = document) {
    root.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = this.t(key);
    });
    root.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) el.setAttribute('placeholder', this.t(key));
    });
    root.querySelectorAll('[data-i18n-tooltip]').forEach(el => {
      const key = el.getAttribute('data-i18n-tooltip');
      if (key) el.setAttribute('data-tooltip', this.t(key));
    });
    root.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      if (key) el.setAttribute('title', this.t(key));
    });
    root.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
      const key = el.getAttribute('data-i18n-aria-label');
      if (key) el.setAttribute('aria-label', this.t(key));
    });
    root.querySelectorAll('[data-i18n-html]').forEach(el => {
      const key = el.getAttribute('data-i18n-html');
      if (key) el.innerHTML = this.t(key);
    });
  },

  // Always loads FR first — it's the fallback bundle
  async init() {
    let saved = null;
    try { saved = localStorage.getItem('lang'); } catch (e) {}
    if (saved && this.availableLangs.includes(saved)) {
      this.currentLang = saved;
    }
    await this.loadBundle('fr');
    if (this.currentLang !== 'fr') {
      await this.loadBundle(this.currentLang);
    }
    document.documentElement.lang = this.currentLang;
    document.documentElement.dir  = (this.currentLang === 'ar') ? 'rtl' : 'ltr';
    this._ready = true;
    this.applyDom();
  },

  isReady() { return this._ready; },
};

// Awaited by App.init() before first render
window.I18N = I18N;
window.t = (key) => I18N.t(key);
window.I18N_READY = I18N.init();