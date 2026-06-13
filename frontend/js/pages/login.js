const LoginPage = {
  render() {
    const content = document.getElementById('page-content');

    // Show a contextual banner when the user was redirected from a protected page
    const intendedPage = localStorage.getItem('intendedPage');
    const explanatoryBanner = intendedPage ? `
      <div style="margin-bottom:16px;padding:10px 14px;background:rgba(245,158,11,0.10);border:1px solid rgba(245,158,11,0.30);border-radius:var(--radius-md);font-size:13px;color:var(--amber-400)">
        <i class="fas fa-lock"></i> ${I18N.t('auth.login.required')}
      </div>
    ` : '';

    content.innerHTML = `
      <div class="page-wrapper" style="display:flex;justify-content:center;align-items:center;min-height:80vh">
        <div class="card" style="width:100%;max-width:400px;padding:32px">
          <div style="text-align:center;margin-bottom:24px">
            <div style="width:48px;height:48px;background:var(--amber-400);border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 16px">
              <i class="fas fa-solar-panel" style="color:#000;font-size:24px"></i>
            </div>
            <h2>${I18N.t('auth.login.title')}</h2>
            <p style="color:var(--text-secondary);font-size:14px">${I18N.t('auth.login.sub')}</p>
          </div>
          ${explanatoryBanner}
          <form id="login-form" onsubmit="LoginPage.submit(event)">
            <div class="form-group">
              <label class="form-label">${I18N.t('auth.login.email')}</label>
              <input type="email" class="form-input" id="login-email" required placeholder="nom@entreprise.com">
            </div>
            <div class="form-group" style="margin-bottom:24px">
              <label class="form-label">${I18N.t('auth.login.password')}</label>
              <input type="password" class="form-input" id="login-password" required placeholder="••••••••">
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">
              <i class="fas fa-sign-in-alt"></i> ${I18N.t('auth.login.submit')}
            </button>
          </form>
          <div style="text-align:center;margin-top:24px;font-size:14px;color:var(--text-secondary)">
            ${I18N.t('auth.login.no_account')}
            <a href="#" onclick="App.navigate('register');return false;" style="color:var(--amber-400);font-weight:600">
              ${I18N.t('auth.login.signup_link')}
            </a>
          </div>
        </div>
      </div>
    `;
  },

  async submit(e) {
    e.preventDefault();

    const email    = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    Utils.toast('info', I18N.t('auth.login.title'), I18N.t('auth.login.checking'));

    const res = await API.login(email, password);

    if (res && res.status === 200) {
      // Verify the session was actually written before proceeding
      const storedUser = sessionStorage.getItem('user');
      if (!storedUser) {
        Utils.toast('error', I18N.t('common.error'), I18N.t('auth.login.fail'));
        return;
      }

      Utils.toast('success', I18N.t('auth.login.title'), I18N.t('auth.login.success'));

      // Re-render the app shell so the avatar replaces the sign-in button
      Components.renderAppShell();

      // Restore the page the user originally requested, then clear the stored intent
      const intendedPage   = localStorage.getItem('intendedPage');
      const intendedParams = localStorage.getItem('intendedParams');
      localStorage.removeItem('intendedPage');
      localStorage.removeItem('intendedParams');

      if (intendedPage && App.pages[intendedPage]) {
        const params = intendedParams ? JSON.parse(intendedParams) : {};
        App.navigate(intendedPage, params);
      } else {
        App.navigate('landing');
      }
    } else {
      console.error('Login failed:', res);
      Utils.toast('error', I18N.t('common.error'), res?.error || I18N.t('auth.login.fail'));
    }
  },
};

window.LoginPage = LoginPage;