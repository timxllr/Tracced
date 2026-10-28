import { apiRequest } from '../api.js';

export function renderForecast(container, seriesId, navigate) {
  container.innerHTML = `
    <div style="padding: 2rem; text-align: center; color: var(--text-muted);">Berechne Prognosen...</div>
  `;

  loadForecast();

  async function loadForecast() {
    try {
      const report = await apiRequest(`/series/${seriesId}/forecast`);

      container.innerHTML = `
        <div class="view-toolbar">
          <div>
            <button id="btn-back-detail" class="btn btn-secondary" style="margin-bottom: 0.5rem; font-size: 0.8rem;">&larr; Zurück</button>
            <h1 class="view-title">Prognose: ${escapeHtml(report.series_name)}</h1>
            <p style="color: var(--text-muted); font-size: 0.9rem;">
              Bezugsbasis: <strong>${report.readings_considered} Messwerte</strong> über ${report.baseline_days_used} Tage
            </p>
          </div>
        </div>

        <div class="forecast-grid">
          ${report.forecasts.map(f => renderForecastCard(f, report.unit, report.allow_decimals)).join('')}
        </div>

        <div style="margin-top: 2rem; padding: 1.25rem; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border-color); font-size: 0.85rem; color: var(--text-muted);">
          <strong style="color: var(--text-main);">Methodik & Transparenzhinweise:</strong>
          <ul style="margin-left: 1.25rem; margin-top: 0.5rem; line-height: 1.6;">
            <li><strong>Zählerstände / Fortlaufend:</strong> Berechnung der täglichen Verbrauchsrate aus dem Standard-Bezugszeitraum (letzte 90 Tage). Automatische Erkennung und Isolierung bei Zählerwechseln/Rücksetzungen.</li>
            <li><strong>Diskrete Messungen:</strong> Lineare Regression nach der Methode der kleinsten Quadrate (OLS) inkl. Bestimmtheitsmaß (R²).</li>
            <li><strong>Halbes Jahr (6 Kalendermonate):</strong> Exakte Monatsarithmetik ab letztem Messpunkt unter Berücksichtigung von Ultimo-Tagen und Schaltjahren.</li>
          </ul>
        </div>
      `;

      document.getElementById('btn-back-detail').addEventListener('click', () => {
        navigate('series-detail', { id: seriesId });
      });

    } catch (err) {
      container.innerHTML = `
        <div style="padding: 2rem; color: var(--sync-error); text-align: center;">
          Fehler bei der Prognoseberechnung: ${escapeHtml(err.message)}
          <br><br>
          <button id="btn-back-err" class="btn btn-secondary">Zurück</button>
        </div>
      `;
      document.getElementById('btn-back-err')?.addEventListener('click', () => navigate('series-detail', { id: seriesId }));
    }
  }
}

function renderForecastCard(f, unit, allowDecimals = true) {
  let badgeClass = 'badge-good';
  let badgeText = 'Gute Datenbasis';

  if (f.quality === 'insufficient_data') {
    badgeClass = 'badge-insufficient';
    badgeText = 'Zu wenig Daten';
  } else if (f.quality === 'limited') {
    badgeClass = 'badge-limited';
    badgeText = 'Eingeschränkt verlässlich';
  } else if (f.quality === 'reset_detected') {
    badgeClass = 'badge-reset';
    badgeText = 'Zählerwechsel isoliert';
  }

  const targetDateStr = new Date(f.target_date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const decimalOptions = allowDecimals === false
    ? { maximumFractionDigits: 0 }
    : { minimumFractionDigits: 1, maximumFractionDigits: 2 };
  const valStr = f.forecasted_value !== null ? parseFloat(f.forecasted_value).toLocaleString('de-DE', decimalOptions) : '—';
  const changeStr = f.expected_change !== null ? (f.expected_change >= 0 ? '+' : '') + parseFloat(f.expected_change).toLocaleString('de-DE', decimalOptions) : '';

  return `
    <div class="forecast-card">
      <div style="display: flex; justify-content: space-between; align-items: baseline;">
        <span style="font-weight: 700; color: var(--text-main); font-size: 1.05rem;">${escapeHtml(f.horizon_label)}</span>
        <span style="font-size: 0.75rem; color: var(--text-subtle);">${round(f.duration_days, 1)} Tage</span>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.75rem;">Stichtag: ${targetDateStr}</div>
      
      <div style="margin: 0.75rem 0;">
        <div style="font-size: 1.8rem; font-weight: 800; color: var(--text-main);">
          ${valStr} <span style="font-size: 0.9rem; font-weight: 500; color: var(--text-muted);">${escapeHtml(unit)}</span>
        </div>
        ${changeStr ? `<div style="font-size: 0.85rem; color: var(--accent-emerald); font-weight: 600;">Änderung: ${changeStr} ${escapeHtml(unit)}</div>` : ''}
      </div>

      <div class="forecast-badge ${badgeClass}">${badgeText}</div>
      <div style="font-size: 0.75rem; color: var(--text-subtle); margin-top: 0.5rem; line-height: 1.4;">
        ${escapeHtml(f.quality_message)}
      </div>
      ${f.rule_note ? `<div style="font-size: 0.7rem; color: var(--primary); margin-top: 0.4rem;">${escapeHtml(f.rule_note)}</div>` : ''}
    </div>
  `;
}

function round(val, dec) {
  return parseFloat(val).toFixed(dec);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[m]));
}
