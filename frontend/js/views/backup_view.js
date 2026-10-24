import { apiRequest } from '../api.js';

export function renderBackup(container, navigate) {
  container.innerHTML = `
    <div class="view-toolbar">
      <div>
        <button id="btn-back-dash" class="btn btn-secondary" style="margin-bottom: 0.5rem; font-size: 0.8rem;">&larr; Zurück zum Dashboard</button>
        <h1 class="view-title">Datensicherung & Import</h1>
        <p style="color: var(--text-muted); font-size: 0.9rem;">Vollständiger Datenexport und atomarer Import</p>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem;">
      <!-- Export Box -->
      <div class="series-card" style="cursor: default;">
        <div>
          <h3 style="color: var(--text-main); margin-bottom: 0.5rem;">Daten exportieren</h3>
          <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1.5rem; line-height: 1.5;">
            Lade sämtliche Messreihen und Messwerte als vollständiges, versionsgesichertes JSON-Backup herunter oder exportiere eine tabellarische CSV-Datei für Tabellenkalkulationen.
          </p>
        </div>
        <div class="btn-group" style="margin-top: 1rem;">
          <a id="btn-export-json" class="btn btn-primary" href="/api/v1/backup/export/json" download="tracced_backup.json">JSON-Backup herunterladen</a>
          <a id="btn-export-csv" class="btn btn-secondary" href="/api/v1/backup/export/csv" download="tracced_backup.csv">CSV-Tabelle herunterladen</a>
        </div>
      </div>

      <!-- Import Box -->
      <div class="series-card" style="cursor: default;">
        <div>
          <h3 style="color: var(--text-main); margin-bottom: 0.5rem;">Daten wiederherstellen / importieren</h3>
          <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem; line-height: 1.5;">
            Wähle eine Tracced JSON-Backup-Datei aus. Die Datei wird vorab vollständig geprüft. Der Import erfolgt in einer einzigen atomaren Transaktion.
          </p>
          <div class="form-group">
            <input type="file" id="backup-file-input" accept=".json" class="form-input" style="font-size: 0.85rem;">
          </div>
        </div>
        <div style="margin-top: 1rem;">
          <button id="btn-validate-import" class="btn btn-secondary" style="width: 100%;" disabled>Backup prüfen</button>
        </div>
      </div>
    </div>

    <!-- Validierungsbericht Container -->
    <div id="import-report-box" style="margin-top: 1.5rem; display: none;"></div>
  `;

  document.getElementById('btn-back-dash').addEventListener('click', () => navigate('dashboard'));

  const fileInput = document.getElementById('backup-file-input');
  const validateBtn = document.getElementById('btn-validate-import');
  const reportBox = document.getElementById('import-report-box');

  let parsedData = null;

  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          parsedData = JSON.parse(event.target.result);
          validateBtn.disabled = false;
          validateBtn.textContent = 'Backup prüfen & analysieren';
        } catch (err) {
          alert('Ungültige JSON-Datei: ' + err.message);
          validateBtn.disabled = true;
        }
      };
      reader.readAsText(file);
    }
  });

  validateBtn.addEventListener('click', async () => {
    if (!parsedData) return;
    validateBtn.disabled = true;
    validateBtn.textContent = 'Prüfe...';

    try {
      const report = await apiRequest('/backup/validate', {
        method: 'POST',
        body: parsedData
      });

      renderValidationReport(report, parsedData, reportBox, navigate);
    } catch (err) {
      alert('Validierungsfehler: ' + err.message);
    } finally {
      validateBtn.disabled = false;
      validateBtn.textContent = 'Backup prüfen & analysieren';
    }
  });
}

function renderValidationReport(report, data, container, navigate) {
  container.style.display = 'block';

  const isValid = report.valid;
  const statusColor = isValid ? 'var(--accent-emerald)' : 'var(--sync-error)';

  container.innerHTML = `
    <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 1.5rem;">
      <h3 style="color: ${statusColor}; margin-bottom: 0.75rem;">
        ${isValid ? '✓ Prüfbericht: Backup ist gültig und bereit' : '✗ Fehlerhafte Backup-Datei'}
      </h3>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.25rem;">
        <div style="background: var(--bg-secondary); padding: 0.75rem; border-radius: var(--radius-md);">
          <div style="font-size: 0.75rem; color: var(--text-muted);">Neue Messreihen</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-main);">${report.series_to_create}</div>
        </div>
        <div style="background: var(--bg-secondary); padding: 0.75rem; border-radius: var(--radius-md);">
          <div style="font-size: 0.75rem; color: var(--text-muted);">Zusammenzuführende Reihen</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-main);">${report.series_to_merge}</div>
        </div>
        <div style="background: var(--bg-secondary); padding: 0.75rem; border-radius: var(--radius-md);">
          <div style="font-size: 0.75rem; color: var(--text-muted);">Neue Messwerte</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-main);">${report.readings_to_create}</div>
        </div>
        <div style="background: var(--bg-secondary); padding: 0.75rem; border-radius: var(--radius-md);">
          <div style="font-size: 0.75rem; color: var(--text-muted);">Bereits vorhandene Duplikate</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-subtle);">${report.readings_duplicate_skipped}</div>
        </div>
      </div>

      ${report.warnings && report.warnings.length > 0 ? `
        <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-md); padding: 0.75rem; margin-bottom: 1rem; font-size: 0.85rem; color: #fbbf24;">
          <strong>Hinweise / Abweichungen:</strong>
          <ul style="margin-left: 1rem; margin-top: 0.25rem;">
            ${report.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
          </ul>
        </div>
      ` : ''}

      ${!isValid ? `
        <div style="color: var(--sync-error); font-size: 0.9rem; margin-bottom: 1rem;">
          <strong>Kritische Fehler:</strong>
          <ul>${report.errors.map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul>
        </div>
      ` : `
        <div style="border-top: 1px solid var(--border-color); padding-top: 1.25rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
          <div>
            <label class="form-label">Import-Strategie</label>
            <select id="import-mode-select" class="form-select" style="width: auto;">
              <option value="merge">Zusammenführen (Merge - Neue Werte ergänzen)</option>
              <option value="replace">Vollständiges Ersetzen (Bestehende Daten überschreiben)</option>
            </select>
          </div>
          <button id="btn-execute-import" class="btn btn-primary">Atomaren Import jetzt ausführen</button>
        </div>
      `}
    </div>
  `;

  if (isValid) {
    document.getElementById('btn-execute-import').addEventListener('click', async () => {
      const mode = document.getElementById('import-mode-select').value;
      if (mode === 'replace') {
        if (!confirm('WARNUNG: Beim vollständigen Ersetzen werden alle bisherigen Messreihen gelöscht und durch das Backup ersetzt. Fortfahren?')) {
          return;
        }
      }

      const execBtn = document.getElementById('btn-execute-import');
      execBtn.disabled = true;
      execBtn.textContent = 'Importiere atomar...';

      try {
        await apiRequest('/backup/execute', {
          method: 'POST',
          body: { mode, data }
        });
        alert('Import erfolgreich abgeschlossen!');
        navigate('dashboard');
      } catch (err) {
        alert('Fehler beim Import (Rollback ausgeführt): ' + err.message);
        execBtn.disabled = false;
        execBtn.textContent = 'Atomaren Import jetzt ausführen';
      }
    });
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[m]));
}
