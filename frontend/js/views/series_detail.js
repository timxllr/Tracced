import { apiRequest } from '../api.js';
import { renderLineChart } from '../charts.js';
import { showSeriesModal } from './dashboard.js';

export function renderSeriesDetail(container, seriesId, navigate) {
  container.innerHTML = `
    <div style="padding: 2rem; text-align: center; color: var(--text-muted);">Lade Messreihe...</div>
  `;

  loadDetail();

  async function loadDetail() {
    try {
      const series = await apiRequest(`/series/${seriesId}`);
      const typeLabel = series.series_type === 'continuous_cumulative' ? 'Fortlaufender Zählerstand' : 'Diskrete Messung';
      const decimalsLabel = series.allow_decimals === false ? ' &bull; Ganzzahlige Werte' : '';

      container.innerHTML = `
        <div class="view-toolbar">
          <div>
            <button id="btn-back" class="btn btn-secondary" style="margin-bottom: 0.5rem; font-size: 0.8rem;">&larr; Zurück zur Übersicht</button>
            <h1 class="view-title">${escapeHtml(series.name)}</h1>
            <p style="color: var(--text-muted); font-size: 0.9rem;">
              Einheit: <strong>${escapeHtml(series.unit)}</strong> &bull; Typ: ${typeLabel}${decimalsLabel}
            </p>
          </div>
          <div class="btn-group">
            <button id="btn-add-reading" class="btn btn-primary">+ Messwert erfassen</button>
            <button id="btn-view-forecast" class="btn btn-secondary">Prognosen anzeigen</button>
            <button id="btn-edit-series" class="btn btn-secondary">Bearbeiten</button>
            <button id="btn-delete-series" class="btn btn-danger">Löschen</button>
          </div>
        </div>

        <div class="chart-box">
          <div class="chart-header">
            <h3 style="font-size: 1.1rem; color: var(--text-main);">Messwertverlauf</h3>
            <span style="font-size: 0.85rem; color: var(--text-muted);">${series.readings.length} erfasste Werte</span>
          </div>
          <canvas id="series-canvas" style="width: 100%; height: 280px;"></canvas>
        </div>

        <div class="data-table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>Zeitstempel</th>
                <th>Messwert (${escapeHtml(series.unit)})</th>
                <th>Notiz</th>
                <th style="text-align: right;">Aktionen</th>
              </tr>
            </thead>
            <tbody id="readings-tbody">
              ${renderReadingsRows(series.readings, series.unit, series.allow_decimals)}
            </tbody>
          </table>
        </div>
      `;

      // Event Listener
      document.getElementById('btn-back').addEventListener('click', () => navigate('dashboard'));
      document.getElementById('btn-add-reading').addEventListener('click', () => showReadingModal(series, null, loadDetail));
      document.getElementById('btn-view-forecast').addEventListener('click', () => navigate('forecast', { id: series.id }));
      document.getElementById('btn-edit-series').addEventListener('click', () => showSeriesModal(series, loadDetail));
      document.getElementById('btn-delete-series').addEventListener('click', () => confirmDeleteSeries(series, navigate));

      // Zeilenaktionen (Bearbeiten / Löschen)
      container.querySelectorAll('.btn-edit-reading').forEach(btn => {
        btn.addEventListener('click', () => {
          const rId = btn.getAttribute('data-id');
          const reading = series.readings.find(r => r.id === rId);
          if (reading) showReadingModal(series, reading, loadDetail);
        });
      });

      container.querySelectorAll('.btn-delete-reading').forEach(btn => {
        btn.addEventListener('click', async () => {
          const rId = btn.getAttribute('data-id');
          if (confirm('Diesen Messwert unwiderruflich löschen?')) {
            try {
              await apiRequest(`/readings/${rId}`, { method: 'DELETE' });
              loadDetail();
            } catch (err) {
              alert('Fehler beim Löschen: ' + err.message);
            }
          }
        });
      });

      // Chart zeichnen
      setTimeout(() => {
        renderLineChart('series-canvas', series.readings, series.unit, { decimals: series.allow_decimals !== false });
      }, 50);

    } catch (err) {
      container.innerHTML = `
        <div style="padding: 2rem; color: var(--sync-error); text-align: center;">
          Fehler: ${escapeHtml(err.message)}
          <br><br>
          <button id="btn-back-err" class="btn btn-secondary">Zurück zum Dashboard</button>
        </div>
      `;
      document.getElementById('btn-back-err')?.addEventListener('click', () => navigate('dashboard'));
    }
  }
}

function renderReadingsRows(readings, unit, allowDecimals = true) {
  if (!readings || readings.length === 0) {
    return `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 2rem;">Noch keine Messwerte vorhanden.</td></tr>`;
  }

  // Neueste zuerst in der Tabelle
  const sorted = [...readings].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

  return sorted.map(r => {
    const d = new Date(r.timestamp);
    const dateStr = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    const valStr = parseFloat(r.value).toLocaleString('de-DE', allowDecimals
      ? { minimumFractionDigits: 1, maximumFractionDigits: 4 }
      : { maximumFractionDigits: 0 });

    return `
      <tr>
        <td style="font-weight: 500;">${dateStr}</td>
        <td style="font-weight: 700; color: var(--text-main);">${valStr} ${escapeHtml(unit)}</td>
        <td style="color: var(--text-muted); font-size: 0.85rem;">${escapeHtml(r.note || '—')}</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-edit-reading" data-id="${r.id}" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;">Bearbeiten</button>
          <button class="btn btn-danger btn-delete-reading" data-id="${r.id}" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;">Löschen</button>
        </td>
      </tr>
    `;
  }).join('');
}

function showReadingModal(series, reading, onSuccess) {
  const isEdit = !!reading;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';

  // Standard-Zeitstempel: Jetzt oder bestehender
  let defaultTime;
  if (isEdit) {
    const dt = new Date(reading.timestamp);
    dt.setMinutes(dt.getMinutes() - dt.getTimezoneOffset());
    defaultTime = dt.toISOString().slice(0, 16);
  } else {
    const dt = new Date();
    dt.setMinutes(dt.getMinutes() - dt.getTimezoneOffset());
    defaultTime = dt.toISOString().slice(0, 16);
  }

  overlay.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h3>${isEdit ? 'Messwert korrigieren' : 'Neuen Messwert erfassen'}</h3>
        <button class="modal-close">&times;</button>
      </div>
      <form id="reading-form">
        <div class="form-group">
          <label class="form-label">Datum und Uhrzeit</label>
          <input type="datetime-local" id="reading-ts" class="form-input" required value="${defaultTime}">
        </div>
        <div class="form-group">
          <label class="form-label">Messwert in ${escapeHtml(series.unit)}</label>
          <input type="number" step="${series.allow_decimals === false ? '1' : 'any'}" id="reading-val" class="form-input" required value="${isEdit ? reading.value : ''}" placeholder="${series.allow_decimals === false ? 'z.B. 12451' : 'z.B. 12450.5'}">
        </div>
        <div class="form-group">
          <label class="form-label">Optionale Notiz</label>
          <input type="text" id="reading-note" class="form-input" value="${isEdit ? escapeHtml(reading.note || '') : ''}" placeholder="z.B. Nach Zählerablesung">
        </div>
        <div id="reading-modal-error" style="color: var(--sync-error); font-size: 0.85rem; margin-bottom: 1rem; display: none;"></div>
        <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
          <button type="button" class="btn btn-secondary modal-close-btn">Abbrechen</button>
          <button type="submit" class="btn btn-primary">${isEdit ? 'Messwert speichern' : 'Messwert eintragen'}</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.querySelector('.modal-close').addEventListener('click', close);
  overlay.querySelector('.modal-close-btn').addEventListener('click', close);

  overlay.querySelector('#reading-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = overlay.querySelector('#reading-modal-error');
    errorEl.style.display = 'none';

    const tsVal = document.getElementById('reading-ts').value;
    const dateObj = new Date(tsVal);

    const payload = {
      timestamp: dateObj.toISOString(),
      value: parseFloat(document.getElementById('reading-val').value),
      note: document.getElementById('reading-note').value.trim() || null
    };

    try {
      if (isEdit) {
        payload.expected_updated_at = reading.updated_at;
        await apiRequest(`/readings/${reading.id}`, { method: 'PUT', body: payload });
      } else {
        await apiRequest(`/series/${series.id}/readings`, { method: 'POST', body: payload });
      }
      close();
      if (onSuccess) onSuccess();
    } catch (err) {
      errorEl.textContent = err.message || 'Fehler beim Speichern';
      errorEl.style.display = 'block';
    }
  });
}

async function confirmDeleteSeries(series, navigate) {
  if (confirm(`Soll die Messreihe "${series.name}" inklusive aller ${series.readings.length} Messwerte unwiderruflich gelöscht werden?`)) {
    try {
      await apiRequest(`/series/${series.id}`, { method: 'DELETE' });
      navigate('dashboard');
    } catch (err) {
      alert('Fehler beim Löschen: ' + err.message);
    }
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[m]));
}
