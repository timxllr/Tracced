/**
 * Leichtgewichtige, interaktive Canvas-Diagramme für Zeitreihen und Verläufe.
 * Funktioniert vollständig ohne Fremdbibliotheken oder Node.js-Buildsystem.
 */

export function renderLineChart(canvasId, readings, unit, options = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  
  // High-DPI Skalierung für scharfe Darstellung auf Retina-/Mobil-Displays
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const padRight = 20;
  const padTop = 30;
  const padBottom = 40;

  ctx.clearRect(0, 0, w, h);

  if (!readings || readings.length === 0) {
    ctx.fillStyle = '#64748b';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Keine Messwerte für ein Diagramm vorhanden', w / 2, h / 2);
    return;
  }

  const sorted = [...readings].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  const values = sorted.map(r => parseFloat(r.value));
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const valRange = maxVal === minVal ? 1 : maxVal - minVal;

  const t0 = new Date(sorted[0].timestamp).getTime();
  const tEnd = new Date(sorted[sorted.length - 1].timestamp).getTime();
  const timeRange = tEnd === t0 ? 1 : tEnd - t0;

  // Achsenbeschriftung vorbereiten und linken Rand an die breiteste Beschriftung anpassen
  const steps = 4;
  const axisDigits = options.decimals === false ? 0 : 1;
  ctx.font = '11px sans-serif';
  const yTicks = [];
  for (let i = 0; i <= steps; i++) {
    const yVal = minVal + (valRange / steps) * i;
    const label = `${yVal.toLocaleString('de-DE', { minimumFractionDigits: axisDigits, maximumFractionDigits: axisDigits })} ${unit}`;
    yTicks.push({ yVal, label });
  }
  const maxLabelWidth = Math.max(...yTicks.map(t => ctx.measureText(t.label).width));
  const padLeft = Math.max(60, Math.ceil(maxLabelWidth) + 16);

  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;

  // Koordinaten-Transformation
  const getX = (ts) => padLeft + ((new Date(ts).getTime() - t0) / timeRange) * chartW;
  const getY = (val) => padTop + chartH - ((val - minVal) / valRange) * chartH;

  // Horizontale Gitterlinien
  ctx.strokeStyle = '#233150';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#94a3b8';
  ctx.font = '11px sans-serif';
  ctx.textAlign = 'right';

  for (const tick of yTicks) {
    const yPx = getY(tick.yVal);
    ctx.beginPath();
    ctx.moveTo(padLeft, yPx);
    ctx.lineTo(w - padRight, yPx);
    ctx.stroke();
    ctx.fillText(tick.label, padLeft - 8, yPx + 4);
  }

  // Verlaufslinie mit sanftem Farbverlauf
  ctx.beginPath();
  sorted.forEach((r, idx) => {
    const x = getX(r.timestamp);
    const y = getY(parseFloat(r.value));
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#3b82f6';
  ctx.lineWidth = 3;
  ctx.stroke();

  // Fläche unter der Linie
  ctx.lineTo(getX(sorted[sorted.length - 1].timestamp), padTop + chartH);
  ctx.lineTo(getX(sorted[0].timestamp), padTop + chartH);
  ctx.closePath();
  const gradient = ctx.createLinearGradient(0, padTop, 0, padTop + chartH);
  gradient.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
  gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');
  ctx.fillStyle = gradient;
  ctx.fill();

  // Datenpunkte zeichnen
  sorted.forEach((r) => {
    const x = getX(r.timestamp);
    const y = getY(parseFloat(r.value));
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#0b0f19';
    ctx.fill();
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  // Zeitstempel unten
  ctx.fillStyle = '#64748b';
  ctx.textAlign = 'left';
  ctx.fillText(new Date(t0).toLocaleDateString('de-DE'), padLeft, h - 12);
  ctx.textAlign = 'right';
  ctx.fillText(new Date(tEnd).toLocaleDateString('de-DE'), w - padRight, h - 12);
}
