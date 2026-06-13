/**
 * SOLARDECIDE DZ - Offline Sync Manager
 * Queues write actions in IndexedDB and replays them FIFO when connectivity returns.
 */

const OfflineSync = (() => {
  const DB_NAME = 'solardz_actions';
  const DB_VERSION = 1;
  const STORE = 'queue';
  const UNSYNCED = 0;

  let dbPromise = null;
  let syncing = false;

  function openDB() {
    if (dbPromise) return dbPromise;

    dbPromise = new Promise((resolve, reject) => {
      if (!('indexedDB' in window)) {
        reject(new Error('IndexedDB is not available in this browser'));
        return;
      }

      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: 'id' });
          store.createIndex('synced', 'synced', { unique: false });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };
      req.onsuccess = (event) => resolve(event.target.result);
      req.onerror = (event) => reject(event.target.error);
    });

    return dbPromise;
  }

  async function store(mode = 'readonly') {
    const db = await openDB();
    return db.transaction(STORE, mode).objectStore(STORE);
  }

  function requestToPromise(req) {
    return new Promise((resolve, reject) => {
      req.onsuccess = (event) => resolve(event.target.result);
      req.onerror = (event) => reject(event.target.error);
    });
  }

  function actionId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `act_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }

  function inferType(endpoint, method) {
    const clean = String(endpoint || '').replace(/^\/+/, '').split('/')[0] || 'api';
    return `${String(method || 'POST').toUpperCase()}:${clean}`;
  }

  async function enqueue(endpoint, method = 'POST', body = {}, type = null) {
    const action = {
      id: actionId(),
      type: type || inferType(endpoint, method),
      endpoint,
      method: String(method || 'POST').toUpperCase(),
      body,
      timestamp: Date.now(),
      synced: UNSYNCED,
      retries: 0,
    };

    const s = await store('readwrite');
    await requestToPromise(s.put(action));
    updateBadge();
    return action.id;
  }

  async function getAll() {
    const s = await store();
    const rows = await requestToPromise(s.getAll());
    return rows.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
  }

  async function getPending() {
    const rows = await getAll();
    return rows.filter((item) => item.synced === UNSYNCED);
  }

  async function getPendingCount() {
    return (await getPending()).length;
  }

  async function deleteAction(id) {
    const s = await store('readwrite');
    await requestToPromise(s.delete(id));
  }

  async function saveAction(action) {
    const s = await store('readwrite');
    await requestToPromise(s.put(action));
  }

  async function markRetry(action) {
    const next = {
      ...action,
      retries: (action.retries || 0) + 1,
      last_error_at: Date.now(),
    };
    if (next.retries >= 5) next.synced = -1;
    await saveAction(next);
  }

  async function replay(action) {
    const baseUrl = window.BACKEND_URL || 'http://localhost:5000/api';
    const url = `${baseUrl}${action.endpoint}`;
    const res = await fetch(url, {
      method: action.method,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Offline-Action-Id': action.id,
        'X-Offline-Queued-At': new Date(action.timestamp).toISOString(),
      },
      body: action.method === 'GET' ? undefined : JSON.stringify(action.body || {}),
      signal: AbortSignal.timeout(12000),
    });

    if (!res.ok) {
      throw new Error(`Replay failed with HTTP ${res.status}`);
    }

    return res;
  }

  async function syncNow() {
    if (syncing) return { synced: 0, failed: 0, skipped: true };
    if (!navigator.onLine) return { synced: 0, failed: 0 };

    syncing = true;
    let synced = 0;
    let failed = 0;

    try {
      const pending = await getPending();
      for (const action of pending) {
        try {
          await replay(action);
          await deleteAction(action.id);
          synced += 1;
        } catch (err) {
          console.warn(`[OfflineSync] Could not replay ${action.id}:`, err);
          await markRetry(action);
          failed += 1;
        }
      }
    } finally {
      syncing = false;
      updateBadge();
    }

    if (synced > 0 && window.Utils) {
      Utils.toast('success', 'Synchronisation', `${synced} action(s) synchronisee(s)`);
    }

    return { synced, failed };
  }

  async function clearAll() {
    const s = await store('readwrite');
    await requestToPromise(s.clear());
    updateBadge();
  }

  function updateBadge() {
    getPendingCount().then((count) => {
      const small = document.getElementById('offline-pending-count');
      if (small) small.textContent = count;

      const big = document.getElementById('offline-pending-count-big');
      if (big) big.textContent = count;

      const badge = document.getElementById('offline-sync-badge');
      if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? '' : 'none';
      }
    }).catch(() => {});
  }

  window.addEventListener('online', () => {
    setTimeout(() => syncNow().catch((err) => console.warn('[OfflineSync] Sync failed:', err)), 1000);
  });

  window.addEventListener('DOMContentLoaded', () => {
    openDB().then(updateBadge).catch(() => {});
  });

  return { enqueue, getAll, getPending, getPendingCount, syncNow, clearAll, updateBadge };
})();

window.OfflineSync = OfflineSync;
