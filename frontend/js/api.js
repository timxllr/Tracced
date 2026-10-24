/**
 * API-Client für Tracced mit integrierter Synchronisationsüberwachung,
 * automatischer CSRF-Token-Übergabe und Konfliktbehandlung.
 */

let currentCsrfToken = null;
let syncListeners = [];

export const SyncStatus = {
  SYNCED: 'synced',
  SYNCING: 'syncing',
  ERROR: 'error'
};

let currentSyncState = {
  status: SyncStatus.SYNCED,
  message: 'Bereit',
  lastSynced: new Date()
};

export function subscribeSyncStatus(callback) {
  syncListeners.push(callback);
  callback(currentSyncState);
  return () => {
    syncListeners = syncListeners.filter(cb => cb !== callback);
  };
}

function updateSyncStatus(status, message) {
  currentSyncState = {
    status,
    message,
    lastSynced: status === SyncStatus.SYNCED ? new Date() : currentSyncState.lastSynced
  };
  syncListeners.forEach(cb => cb(currentSyncState));
}

export function setCsrfToken(token) {
  currentCsrfToken = token;
}

export async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : `/api/v1${endpoint}`;
  
  const headers = {
    'Accept': 'application/json',
    ...(options.headers || {})
  };

  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  // Bei modifizierenden Anfragen CSRF-Token mitsenden
  if (options.method && options.method !== 'GET' && currentCsrfToken) {
    headers['X-CSRF-Token'] = currentCsrfToken;
  }

  if (options.method && options.method !== 'GET') {
    updateSyncStatus(SyncStatus.SYNCING, 'Wird synchronisiert...');
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include' // Cookies mitsenden
    });

    if (response.status === 401) {
      updateSyncStatus(SyncStatus.ERROR, 'Nicht angemeldet');
      throw new Error('UNAUTHORIZED');
    }

    if (response.status === 409) {
      const errData = await response.json().catch(() => ({}));
      updateSyncStatus(SyncStatus.ERROR, errData.detail || 'Konflikt beim Abgleich');
      const err = new Error(errData.detail || 'Konflikt: Datensatz wurde anderweitig geändert.');
      err.isConflict = true;
      throw err;
    }

    if (response.status === 204) {
      updateSyncStatus(SyncStatus.SYNCED, 'Synchronisiert');
      return null;
    }

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const msg = errData.detail || `Serverfehler (${response.status})`;
      updateSyncStatus(SyncStatus.ERROR, msg);
      throw new Error(msg);
    }

    const data = await response.json();
    if (options.method && options.method !== 'GET') {
      updateSyncStatus(SyncStatus.SYNCED, 'Synchronisiert');
    }
    return data;
  } catch (error) {
    if (error.message !== 'UNAUTHORIZED') {
      updateSyncStatus(SyncStatus.ERROR, error.message || 'Verbindungsfehler');
    }
    throw error;
  }
}
