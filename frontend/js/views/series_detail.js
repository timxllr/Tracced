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
            <button id="btn-import-readings" class="btn btn-secondary">Import</button>
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
      document.getElementById('btn-import-readings').addEventListener('click', () => showImportModal(series, loadDetail));
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

async function showImportModal(series, onSuccess) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.style.display = 'flex';

  let parsedCsv = '';
  let validationReport = null;

  overlay.innerHTML = `
    <div class="modal-content" style="max-width: 700px; max-height: 85vh; overflow-y: auto;">
      <div class="modal-header">
        <h3>Messwerte importieren – ${escapeHtml(series.name)}</h3>
        <button class="modal-close">&times;</button>
      </div>

      <div id="import-modal-body" style="padding: 1rem;">
        <!-- Schritt 1: Eingabe -->
        <div class="form-group" style="margin-bottom: 1rem;">
          <label class="form-label">CSV-Daten eingeben</label>
          <div style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem;">
            <button type="button" id="import-tab-file" class="btn btn-secondary" style="flex: 1;">Datei hochladen</button>
            <button type="button" id="import-tab-text" class="btn btn-secondary" style="flex: 1;">Text einfügen</button>
          </div>
          <div id="import-file-zone" style="border: 2px dashed var(--border-color); border-radius: var(--radius-md); padding: 1rem; text-align: center; margin-bottom: 0.5rem; display: none;">
            <input type="file" id="import-file-input" accept=".csv,.txt" style="display: none;">
            <label for="import-file-input" class="btn btn-secondary">CSV-Datei wählen</label>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.5rem;">ODER Datei hierher ziehen</p>
          </div>
          <textarea id="import-textarea" rows="6" class="form-input" style="width: 100%; font-family: monospace; font-size: 0.85rem;" placeholder="Datum;Zählerstand;Notiz
2026-10-28 17:30:20;287174;
2026-10-26 19:20:40;287096;"></textarea>
        </div>

        <!-- Schritt 2: Format -->
        <div class="form-group" style="margin-bottom: 1rem; background: var(--bg-secondary); padding: 1rem; border-radius: var(--radius-md);">
          <label class="form-label">Format spezifizieren</label>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
            <div class="form-group" style="margin-bottom: 0;">
              <label class="form-label">Trennzeichen</label>
              <select id="import-delimiter" class="form-input">
                <option value=";">Semikolon (;)</option>
                <option value=",">Komma (,)</option>
                <option value="\\t">Tabulator</option>
              </select>
            </div>
            <div class="form-group" style="margin-bottom: 0; display: flex; align-items: center; gap: 0.5rem;">
              <input type="checkbox" id="import-has-header" checked>
              <label class="form-label" style="margin-bottom: 0; font-weight: 500;">Erste Zeile ist Kopfzeile</label>
            </div>
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">Spalten-Mapping (nullbasiert)</label>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 1rem;">
              <div>
                <label class="form-label" style="font-size: 0.8rem;">Zeitstempel-Spalte</label>
                <input type="number" id="import-col-ts" value="0" min="0" class="form-input" style="width: 80px;">
              </div>
              <div>
                <label class="form-label" style="font-size: 0.8rem;">Wert-Spalte</label>
                <input type="number" id="import-col-val" value="1" min="0" class="form-input" style="width: 80px;">
              </div>
              <div>
                <label class="form-label" style="font-size: 0.8rem;">Notiz-Spalte</label>
                <input type="number" id="import-col-note" value="" min="0" class="form-input" style="width: 80px;" placeholder="optional">
              </div>
            </div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.5rem;">Beispiel: Datum;Wert;Notiz → TS=0, Wert=1, Notiz=2</p>
          </div>
        </div>

        <!-- Schritt 3: Validierung & Vorschau -->
        <div id="import-preview-box" style="display: none; margin-bottom: 1rem;">
          <div class="form-group" style="margin-bottom: 0.5rem;">
            <label class="form-label">Import-Modus</label>
            <select id="import-mode" class="form-input" style="width: 200px;">
              <option value="merge">Zusammenführen (Merge – neue Werte ergänzen, Duplikate überspringen)</option>
              <option value="replace">Ersetzen (bestehende Werte der Reihe werden gelöscht)</option>
            </select>
          </div>
          <div style="overflow-x: auto;">
            <table class="data-table" style="font-size: 0.8rem;">
              <thead>
                <tr>
                  <th>Zeile</th>
                  <th>Zeitstempel</th>
                  <th>Wert</th>
                  <th>Notiz</th>
                  <th style="width: 100px;">Status</th>
                </tr>
              </thead>
              <tbody id="import-preview-tbody"></tbody>
            </table>
          </div>
          <p id="import-summary" style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;"></p>
        </div>

        <div id="import-error" style="color: var(--sync-error); font-size: 0.85rem; margin-bottom: 1rem; display: none;"></div>
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 0.5rem; padding: 1rem; border-top: 1px solid var(--border-color);">
        <button type="button" id="import-btn-cancel" class="btn btn-secondary modal-close-btn">Abbrechen</button>
        <button type="button" id="import-btn-validate" class="btn btn-secondary" style="margin-right: 0.5rem;">Prüfen</button>
        <button type="button" id="import-btn-execute" class="btn btn-primary" disabled>Importieren</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.querySelector('.modal-close').addEventListener('click', close);
  overlay.querySelector('#import-btn-cancel').addEventListener('click', close);

  // Tabs
  const tabFile = overlay.querySelector('#import-tab-file');
  const tabText = overlay.querySelector('#import-tab-text');
  const fileZone = overlay.querySelector('#import-file-zone');
  const textarea = overlay.querySelector('#import-textarea');

  tabFile.addEventListener('click', () => {
    tabFile.classList.add('btn-primary');
    tabFile.classList.remove('btn-secondary');
    tabText.classList.add('btn-secondary');
    tabText.classList.remove('btn-primary');
    fileZone.style.display = 'block';
    textarea.style.display = 'none';
  });
  tabText.addEventListener('click', () => {
    tabText.classList.add('btn-primary');
    tabText.classList.remove('btn-secondary');
    tabFile.classList.add('btn-secondary');
    tabFile.classList.remove('btn-primary');
    fileZone.style.display = 'none';
    textarea.style.display = 'block';
  });

  // File input
  const fileInput = overlay.querySelector('#import-file-input');
  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      parsedCsv = ev.target.result;
      textarea.value = parsedCsv;
      overlay.querySelector('#import-preview-box').style.display = 'none';
      overlay.querySelector('#import-btn-execute').disabled = true;
      validationReport = null;
    };
    reader.readAsText(file);
  });

  // Prüfen-Button
  const btnValidate = overlay.querySelector('#import-btn-validate');
  const btnExecute = overlay.querySelector('#import-btn-execute');
  const previewBox = overlay.querySelector('#import-preview-box');
  const previewTbody = overlay.querySelector('#import-preview-tbody');
  const summaryEl = overlay.querySelector('#import-summary');
  const errorEl = overlay.querySelector('#import-error');

  btnValidate.addEventListener('click', async () => {
    const csvData = textarea.value.trim();
    if (!csvData) {
      errorEl.textContent = 'Bitte CSV-Daten eingeben oder Datei wählen.';
      errorEl.style.display = 'block';
      return;
    }

    const noteColInput = overlay.querySelector('#import-col-note').value.trim();
    const payload = {
      csv_data: csvData,
      delimiter: overlay.querySelector('#import-delimiter').value,
      has_header: overlay.querySelector('#import-has-header').checked,
      column_mapping: {
        timestamp_col: parseInt(overlay.querySelector('#import-col-ts').value) || 0,
        value_col: parseInt(overlay.querySelector('#import-col-val').value) || 0,
        note_col: noteColInput ? parseInt(noteColInput) : null,
      },
      mode: overlay.querySelector('#import-mode').value,
    };

    errorEl.style.display = 'none';
    btnValidate.disabled = true;
    btnValidate.textContent = 'Prüfe...';

    try {
      const report = await apiRequest(`/series/${series.id}/readings/import/validate`, {
        method: 'POST',
        body: payload,
      });
      validationReport = report;
      renderImportPreview(report, previewTbody, summaryEl);
      previewBox.style.display = 'block';
      btnExecute.disabled = report.valid_rows === 0;
      btnExecute.textContent = `Importieren (${report.valid_rows} Werte)`;
    } catch (err) {
      errorEl.textContent = err.message || 'Validierungsfehler';
      errorEl.style.display = 'block';
    } finally {
      btnValidate.disabled = false;
      btnValidate.textContent = 'Prüfen';
    }
  });

  // Importieren-Button
  btnExecute.addEventListener('click', async () => {
    if (!validationReport) return;

    const noteColInput = overlay.querySelector('#import-col-note').value.trim();
    const payload = {
      csv_data: textarea.value.trim(),
      delimiter: overlay.querySelector('#import-delimiter').value,
      has_header: overlay.querySelector('#import-has-header').checked,
      column_mapping: {
        timestamp_col: parseInt(overlay.querySelector('#import-col-ts').value) || 0,
        value_col: parseInt(overlay.querySelector('#import-col-val').value) || 0,
        note_col: noteColInput ? parseInt(noteColInput) : null,
      },
      mode: overlay.querySelector('#import-mode').value,
    };

    if (payload.mode === 'replace') {
      if (!confirm('WARNUNG: Beim Ersetzen werden alle bisherigen Messwerte dieser Reihe gelöscht. Fortfahren?')) {
        return;
      }
    }

    btnExecute.disabled = true;
    btnExecute.textContent = 'Importiere...';

    try {
      const result = await apiRequest(`/series/${series.id}/readings/import/execute`, {
        method: 'POST',
        body: payload,
      });
      close();
      if (onSuccess) onSuccess();
      alert(result.message);
    } catch (err) {
      errorEl.textContent = err.message || 'Fehler beim Import';
      errorEl.style.display = 'block';
      btnExecute.disabled = false;
      btnExecute.textContent = 'Importieren';
    }
  });
}

function renderImportPreview(report, tbody, summaryEl) {
  tbody.innerHTML = '';
  const showRows = report.preview.slice(0, 50); // max 50 in Vorschau

  for (const row of showRows) {
    const validClass = row.valid ? 'var(--text-main)' : 'var(--sync-error)';
    tbody.innerHTML += `
      <tr>
        <td style="font-size: 0.75rem; color: var(--text-muted);">${row.row_number}</td>
        <td style="font-size: 0.75rem; color: ${validClass};">${escapeHtml(row.timestamp)}</td>
        <td style="font-size: 0.75rem; font-weight: 500; color: ${validClass};">${escapeHtml(row.value)}</td>
        <td style="font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(row.note || '—')}</td>
        <td style="font-size: 0.75rem;">
          <span style="color: ${validClass};">${row.valid ? '✓' : '✗'}</span>
        </td>
      </tr>
    `;
  }

  if (report.preview.length > 50) {
    tbody.innerHTML += `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); font-size: 0.75rem;">... und ${report.preview.length - 50} weitere Zeilen</td></tr>`;
  }

  summaryEl.innerHTML = `
    <strong>${report.valid_rows}</strong> von <strong>${report.total_rows}</strong> Zeilen gültig,
    <strong>${report.invalid_rows}</strong> ungültig (Duplikate oder Formatfehler).
  `;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[m]));
}
