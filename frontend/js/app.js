/**
 * Hauptapplikation von Tracced.
 * Verwaltet Navigation, Synchronisationsleiste und Ansichten-Lifecycle.
 */
import { apiRequest, setCsrfToken, subscribeSyncStatus, SyncStatus } from './api.js';
import { renderLogin } from './views/auth_view.js';
import { renderDashboard } from './views/dashboard.js';
import { renderSeriesDetail } from './views/series_detail.js';
import { renderForecast } from './views/forecast_view.js';
import { renderBackup } from './views/backup_view.js';

let currentUser = null;
let currentView = 'dashboard';
let currentViewParams = {};

const mainContainer = document.getElementById('app-main');
const headerActions = document.getElementById('header-actions');
const syncIndicator = document.getElementById('sync-indicator');
const syncText = document.getElementById('sync-text');

// Sync-Status Listener registrieren
subscribeSyncStatus((state) => {
  if (!syncIndicator || !syncText) return;
  syncIndicator.className = `sync-indicator ${state.status}`;

  if (state.status === SyncStatus.SYNCING) {
    syncText.textContent = 'Synchronisiere...';
  } else if (state.status === SyncStatus.SYNCED) {
    syncText.textContent = 'Synchronisiert';
  } else {
    syncText.textContent = state.message || 'Fehler beim Abgleich';
  }
});

// Stiller Hintergrundabgleich bei Fensterfokus
window.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && currentUser) {
    refreshCurrentView();
  }
});

export function navigate(view, params = {}) {
  currentView = view;
  currentViewParams = params;
  renderApp();
}

function refreshCurrentView() {
  if (!currentUser) return;
  if (currentView === 'dashboard') {
    renderDashboard(mainContainer, navigate);
  } else if (currentView === 'series-detail' && currentViewParams.id) {
    renderSeriesDetail(mainContainer, currentViewParams.id, navigate);
  }
}

function renderApp() {
  if (!currentUser) {
    headerActions.style.display = 'none';
    renderLogin(mainContainer, (user) => {
      currentUser = user;
      navigate('dashboard');
    });
    return;
  }

  // Header für eingeloggte Benutzer
  headerActions.style.display = 'flex';
  const userEmailEl = document.getElementById('user-email-display');
  if (userEmailEl) userEmailEl.textContent = currentUser.email;

  // View rendern
  if (currentView === 'dashboard') {
    renderDashboard(mainContainer, navigate);
  } else if (currentView === 'series-detail') {
    renderSeriesDetail(mainContainer, currentViewParams.id, navigate);
  } else if (currentView === 'forecast') {
    renderForecast(mainContainer, currentViewParams.id, navigate);
  } else if (currentView === 'backup') {
    renderBackup(mainContainer, navigate);
  }
}

// Initialer Auth-Check
async function init() {
  try {
    const statusRes = await apiRequest('/auth/status');
    if (statusRes.authenticated && statusRes.user) {
      currentUser = statusRes.user;
      if (statusRes.csrf_token) {
        setCsrfToken(statusRes.csrf_token);
      }
    }
  } catch (err) {
    currentUser = null;
  }

  // Logout-Button
  document.getElementById('btn-logout')?.addEventListener('click', async () => {
    try {
      await apiRequest('/auth/logout', { method: 'POST' });
    } catch (_) {}
    currentUser = null;
    navigate('dashboard');
  });

  renderApp();
}

init();
