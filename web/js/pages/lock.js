import { api } from '../api.js';
import { $, icon } from '../ui.js';
import { esc } from '../format.js';

/** Full-screen unlock form. Resolves once the server accepted the password or recovery key. */
export default function lockScreen(app, status = {}) {
  return new Promise(resolve => {
    let mode = 'password';
    const draw = (message = '', wait = 0) => {
      app.innerHTML = `<div class="lock-wrap"><form class="card lock-card" autocomplete="off">
        <div class="lock-icon">${icon('lock')}</div>
        <h1>Meus Gastos está bloqueado</h1>
        <p>Seus dados estão criptografados neste computador (AES-256). ${mode === 'password' ? 'Digite a senha para abrir.' : 'Digite a chave de recuperação que você guardou ao ativar a proteção.'}</p>
        ${mode === 'password'
          ? '<label class="field">Senha<input name="secret" type="password" autocomplete="current-password" required autofocus></label>'
          : '<label class="field">Chave de recuperação<input name="secret" type="text" placeholder="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX" spellcheck="false" autocapitalize="characters" required autofocus></label>'}
        <p class="lock-error" role="alert">${esc(message)}</p>
        <button class="btn primary" ${wait ? 'disabled' : ''}>${wait ? `Aguarde ${wait}s` : 'Desbloquear'}</button>
        <button type="button" class="ghost small" id="switch-mode">${mode === 'password' ? 'Esqueci a senha: usar chave de recuperação' : 'Voltar para a senha'}</button>
        <button type="button" class="ghost small" id="quit-locked">Encerrar o app</button>
        <small>Nada sai deste computador. Após ${status.auto_lock || 15} minutos sem uso o app bloqueia sozinho.</small>
      </form></div>`;
      const form = $('form', app);
      form.secret.focus();
      $('#quit-locked', app).addEventListener('click', () => import('../main.js').then(m => m.quitApp()));
      $('#switch-mode', app).addEventListener('click', () => { mode = mode === 'password' ? 'recovery' : 'password'; draw(); });
      if (wait) setTimeout(() => draw(message, wait - 1), 1000);
      form.addEventListener('submit', async e => {
        e.preventDefault();
        const button = $('button.primary', form);
        button.disabled = true;
        button.textContent = 'Abrindo…';
        try {
          await api('security/unlock', mode === 'password' ? { password: form.secret.value } : { recovery: form.secret.value });
          resolve();
        } catch (error) {
          draw(error.message, error.data?.retry_in || 0);
        }
      });
    };
    draw('', status.retry_in || 0);
  });
}
