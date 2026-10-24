import { apiRequest } from '../api.js';

export function renderDashboard(container, navigate) {
  container.innerHTML = `
    <div class="view-toolbar">
      <div>
        <h1 class="view-title">Meine Messreihen</h1>
        <p style="color: var(--text-muted); font-size: 0.9rem;">Zentrale Erfassung und Synchronisation</p>
      </div>
      <div class="btn-group">
        <button id="btn-new-series" class="btn btn-primary">+ Neue Messreihe</button>
        <button id="btn-backup-view" class="btn btn-secondary">Backup & Restore</button>
      </div>
    </div>

    <div id="series-list-container" class="series-grid">
      <div style="color: var(--text-muted); grid-column: 1/-1; text-align: center; padding: 3rem;">Lade Messreihen...</div>
    </div>
  `;

  document.getElementById('btn-new-series').addEventListener('click', () => showSeriesModal(null, () => loadSeries()));
  document.getElementById('btn-backup-view').addEventListener('click', () => navigate('backup'));

  async function loadSeries() {
    const listEl = document.getElementById('series-list-container');
    try {
      const seriesList = await apiRequest('/series');
      if (seriesList.length === 0) {
        listEl.innerHTML = `
          <div style="color: var(--text-muted); grid-column: 1/-1; text-align: center; padding: 4rem 1rem; background: var(--bg-card); border-radius: var(--radius-lg); border: 1px dashed var(--border-color);">
            <h3 style="color: var(--text-main); margin-bottom: 0.5rem;">Noch keine Messreihen vorhanden</h3>
            <p style="margin-bottom: 1.5rem;">Erstelle deine erste Messreihe (z.B. Stromzähler oder Gewicht), um Werte zu erfassen.</p>
            <button id="btn-empty-new" class="btn btn-primary">+ Erste Messreihe anlegen</button>
          </div>
        `;
        document.getElementById('btn-empty-new')?.addEventListener('click', () => showSeriesModal(null, () => loadSeries()));
        return;
      }

      listEl.innerHTML = seriesList.map(s => {
        const typeBadge = s.series_type === 'continuous_cumulative' ? 'Zählerstand' : 'Diskrete Messung';
        const decimalOptions = s.allow_decimals === false
          ? { maximumFractionDigits: 0 }
          : { minimumFractionDigits: 1, maximumFractionDigits: 4 };
        const valText = s.latest_reading ? parseFloat(s.latest_reading.value).toLocaleString('de-DE', decimalOptions) : '—';
        const dateText = s.latest_reading ? new Date(s.latest_reading.timestamp).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Keine Messwerte';

        return `
          <div class="series-card" data-id="${s.id}">
            <div>
              <div class="series-card-header">
                <span class="series-title">${escapeHtml(s.name)}</span>
                <span class="series-badge">${typeBadge}</span>
              </div>
              <div class="series-value-display">
                <span class="series-current-val">${valText}</span>
                <span class="series-unit">${escapeHtml(s.unit)}</span>
              </div>
            </div>
            <div class="series-meta">
              <span>${s.readings_count} Einträge</span>
              <span>${dateText}</span>
            </div>
          </div>
        `;
      }).join('');

      listEl.querySelectorAll('.series-card').forEach(card => {
        card.addEventListener('click', () => {
          navigate('series-detail', { id: card.getAttribute('data-id') });
        });
      });
    } catch (err) {
      listEl.innerHTML = `<div style="color: var(--sync-error); grid-column: 1/-1; text-align: center;">Fehler beim Laden: ${escapeHtml(err.message)}</div>`;
    }
  }

  loadSeries();
}

export function showSeriesModal(series, onSuccess) {
  const isEdit = !!series;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h3>${isEdit ? 'Messreihe bearbeiten' : 'Neue Messreihe anlegen'}</h3>
        <button class="modal-close">&times;</button>
      </div>
      <form id="series-form">
        <div class="form-group">
          <label class="form-label">Name der Messreihe</label>
          <input type="text" id="series-name" class="form-input" required value="${isEdit ? escapeHtml(series.name) : ''}" placeholder="z.B. Stromzähler Hauptwohnung">
        </div>
        <div class="form-group">
          <label class="form-label">Einheit</label>
          <input type="text" id="series-unit" class="form-input" required value="${isEdit ? escapeHtml(series.unit) : ''}" placeholder="z.B. kWh, kg, °C">
        </div>
        <div class="form-group">
          <label class="form-label">Art der Messreihe</label>
          <select id="series-type" class="form-select">
            <option value="continuous_cumulative" ${isEdit && series.series_type === 'continuous_cumulative' ? 'selected' : ''}>Fortlaufender Zählerstand (z. B. Stromzähler)</option>
            <option value="discrete_metric" ${isEdit && series.series_type === 'discrete_metric' ? 'selected' : ''}>Diskrete Messung (z.B. Gewicht, Temperatur)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Nachkommastellen</label>
          <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; color: var(--text-main); font-size: 0.9rem;">
            <input type="checkbox" id="series-decimals" style="width: 1rem; height: 1rem; accent-color: var(--primary);" ${!isEdit || series.allow_decimals !== false ? 'checked' : ''}>
            Nachkommastellen erlauben
          </label>
          <p style="margin-top: 0.35rem; font-size: 0.8rem; color: var(--text-muted);">
            Deaktiviert werden Werte nur als ganze Zahl angezeigt (z. B. 286.897 statt 286.897,4).
          </p>
        </div>
        <div class="form-group">
          <label class="form-label">Optionale Beschreibung</label>
          <textarea id="series-desc" class="form-textarea" rows="2" placeholder="Zusatzinformationen...">${isEdit ? escapeHtml(series.description || '') : ''}</textarea>
        </div>
        <div id="series-modal-error" style="color: var(--sync-error); font-size: 0.85rem; margin-bottom: 1rem; display: none;"></div>
        <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
          <button type="button" class="btn btn-secondary modal-close-btn">Abbrechen</button>
          <button type="submit" class="btn btn-primary">${isEdit ? 'Änderungen speichern' : 'Messreihe erstellen'}</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.querySelector('.modal-close').addEventListener('click', close);
  overlay.querySelector('.modal-close-btn').addEventListener('click', close);

  overlay.querySelector('#series-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = overlay.querySelector('#series-modal-error');
    errorEl.style.display = 'none';

    const payload = {
      name: document.getElementById('series-name').value.trim(),
      unit: document.getElementById('series-unit').value.trim(),
      series_type: document.getElementById('series-type').value,
      allow_decimals: document.getElementById('series-decimals').checked,
      description: document.getElementById('series-desc').value.trim() || null
    };

    try {
      if (isEdit) {
        payload.expected_updated_at = series.updated_at;
        await apiRequest(`/series/${series.id}`, { method: 'PUT', body: payload });
      } else {
        await apiRequest('/series', { method: 'POST', body: payload });
      }
      close();
      if (onSuccess) onSuccess();
    } catch (err) {
      errorEl.textContent = err.message || 'Fehler beim Speichern';
      errorEl.style.display = 'block';
    }
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[m]));
}
