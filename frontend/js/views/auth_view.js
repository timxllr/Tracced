import { apiRequest, setCsrfToken } from '../api.js';

export function renderLogin(container, onLoginSuccess) {
  container.innerHTML = `
    <div style="min-height: 75vh; display: flex; align-items: center; justify-content: center; padding: 1rem;">
      <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-lg); max-width: 400px; width: 100%; padding: 2rem; box-shadow: var(--shadow-modal);">
        <div style="text-align: center; margin-bottom: 1.5rem;">
          <h2 style="font-size: 1.5rem; color: var(--text-main); margin-bottom: 0.25rem;">Tracced</h2>
          <p style="color: var(--text-muted); font-size: 0.85rem;">Sichere Messwert-Erfassung & Analyse</p>
        </div>

        <form id="login-form">
          <div class="form-group">
            <label class="form-label">E-Mail-Adresse</label>
            <input type="email" id="login-email" class="form-input" required autocomplete="username" placeholder="benutzer@example.com">
          </div>
          <div class="form-group">
            <label class="form-label">Passwort</label>
            <input type="password" id="login-password" class="form-input" required autocomplete="current-password" placeholder="••••••••">
          </div>
          <div id="login-error" style="color: var(--sync-error); font-size: 0.85rem; margin-bottom: 1rem; display: none;"></div>
          <button type="submit" id="btn-login-submit" class="btn btn-primary" style="width: 100%; padding: 0.75rem;">Anmelden</button>
        </form>

        <div style="margin-top: 1.5rem; border-top: 1px solid var(--border-color); padding-top: 1rem; font-size: 0.75rem; color: var(--text-subtle); text-align: center;">
          Geschlossenes System. Benutzerkonten werden über die Server-CLI angelegt.
        </div>
      </div>
    </div>
  `;

  const form = document.getElementById('login-form');
  const errorEl = document.getElementById('login-error');
  const submitBtn = document.getElementById('btn-login-submit');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorEl.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Wird angemeldet...';

    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    try {
      const res = await apiRequest('/auth/login', {
        method: 'POST',
        body: { email, password }
      });

      if (res.csrf_token) {
        setCsrfToken(res.csrf_token);
      }
      onLoginSuccess(res.user);
    } catch (err) {
      errorEl.textContent = err.message === 'UNAUTHORIZED' ? 'Ungültige E-Mail-Adresse oder Passwort.' : (err.message || 'Anmeldefehler');
      errorEl.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Anmelden';
    }
  });
}
