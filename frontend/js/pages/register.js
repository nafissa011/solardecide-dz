const RegisterPage = {
  render() {
    const content = document.getElementById('page-content');
    content.innerHTML = `
      <div class="page-wrapper" style="display:flex;justify-content:center;align-items:center;min-height:80vh">
        <div class="card" style="width:100%;max-width:400px;padding:32px">
          <div style="text-align:center;margin-bottom:24px">
            <div style="width:48px;height:48px;background:var(--amber-400);border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 16px">
              <i class="fas fa-user-plus" style="color:#000;font-size:24px"></i>
            </div>
            <h2>${I18N.t('auth.register.title')}</h2>
            <p style="color:var(--text-secondary);font-size:14px">${I18N.t('auth.register.sub')}</p>
          </div>
          <form id="register-form" onsubmit="RegisterPage.submit(event)">
            <div class="form-group">
              <label class="form-label">${I18N.t('auth.register.name')}</label>
              <input type="text" class="form-input" id="reg-name" required minlength="2" placeholder="John Doe">
            </div>
            <div class="form-group">
              <label class="form-label">${I18N.t('auth.register.email')}</label>
              <input type="email" class="form-input" id="reg-email" required placeholder="nom@entreprise.com">
            </div>
            <div class="form-group">
              <label class="form-label">${I18N.t('auth.register.password')}</label>
              <input type="password" class="form-input" id="reg-password" required placeholder="••••••••" minlength="8">
            </div>
            <div class="form-group" style="margin-bottom:24px">
              <label class="form-label">${I18N.t('auth.register.password2')}</label>
              <input type="password" class="form-input" id="reg-password2" required placeholder="••••••••" minlength="8">
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center">
              <i class="fas fa-check"></i> ${I18N.t('auth.register.submit')}
            </button>
          </form>
          <div style="text-align:center;margin-top:24px;font-size:14px;color:var(--text-secondary)">
            ${I18N.t('auth.register.have_account')}
            <a href="#" onclick="App.navigate('login');return false;" style="color:var(--amber-400);font-weight:600">
              ${I18N.t('auth.register.login_link')}
            </a>
          </div>
        </div>
      </div>
    `;
  },

  async submit(e) {
    e.preventDefault();
    const name = document.getElementById('reg-name').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;
    const password2 = document.getElementById('reg-password2').value;

    // Validate password length before contacting the API
    if (password.length < 8) {
      Utils.toast('error', I18N.t('common.error'), I18N.t('auth.register.too_short'));
      return;
    }

    // Ensure both password fields match
    if (password !== password2) {
      Utils.toast('error', I18N.t('common.error'), I18N.t('auth.register.mismatch'));
      return;
    }

    Utils.toast('info', I18N.t('auth.register.title'), I18N.t('auth.register.creating'));
    const res = await API.register(name, email, password);

    if (res && (res.status === 201 || res.status === 200)) {
      Utils.toast('success', I18N.t('auth.register.title'), I18N.t('auth.register.success'));
      // Redirect to login page after a short delay so the user sees the success message
      setTimeout(() => App.navigate('login'), 1200);
    } else {
      Utils.toast('error', I18N.t('common.error'), res?.error || I18N.t('common.error'), 5);
    }
  }
};

window.RegisterPage = RegisterPage;