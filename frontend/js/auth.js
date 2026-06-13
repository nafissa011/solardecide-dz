// Petit wrapper qui expose le rôle/statut admin en décodant le JWT
// stocké dans sessionStorage (même token persisté par API.login).
(function (global) {
  'use strict';

  // Décode la partie payload d'un JWT (base64url -> JSON)
  function _decodePayload(token) {
    if (!token || typeof token !== 'string') return null;
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    try {
      const padded = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const json   = atob(padded + '='.repeat((4 - padded.length % 4) % 4));
      return JSON.parse(json);
    } catch (_) { return null; }
  }

  const Auth = {
    getToken() {
      try { return sessionStorage.getItem('auth_token') || ''; }
      catch (_) { return ''; }
    },
    getUser() {
      try {
        const raw = sessionStorage.getItem('user');
        return raw ? JSON.parse(raw) : null;
      } catch (_) { return null; }
    },
    // Retourne le rôle de l'utilisateur courant : 'admin' | 'user' | ''
    getRole() {
      const u = this.getUser();
      if (u && u.role) return String(u.role).toLowerCase();
      // Si l'objet user n'a pas de rôle, on tente de le récupérer depuis le JWT
      const payload = _decodePayload(this.getToken());
      return payload && payload.role ? String(payload.role).toLowerCase() : '';
    },
    isAdmin()         { return this.getRole() === 'admin'; },
    isAuthenticated() { return !!this.getUser(); },
  };

  global.Auth = Auth;
})(typeof window !== 'undefined' ? window : globalThis);