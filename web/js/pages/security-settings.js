import { store, refresh } from '../main.js';
import { api } from '../api.js';
import { $, $$, icon, guard, modal, confirmDialog, toast, options } from '../ui.js';
import { esc } from '../format.js';

const AUTO_LOCK = [[5, '5 minutos'], [15, '15 minutos'], [30, '30 minutos'], [60, '1 hora'], [0, 'Nunca']];
const kb = bytes => bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

/** Rough strength: length and variety. Only guidance; the server enforces the minimum. */
function strength(password) {
  let score = Math.min(4, Math.floor(password.length / 4));
  score += [/[a-z]/, /[A-Z]/, /\d/, /[^\w\s]/, /\s/].filter(r => r.test(password)).length;
  if (password.length < 8 || new Set(password).size < 4) score = Math.min(score, 2);
  return Math.min(4, Math.floor(score / 2));
}
const STRENGTH = [['Muito fraca', 'var(--bad)'], ['Fraca', 'var(--bad)'], ['Razoável', 'var(--warn)'], ['Boa', 'var(--good)'], ['Forte', 'var(--good)']];

function passwordFields(prefix = '') {
  return `<label class="field">${prefix}Senha<input name="password" type="password" autocomplete="new-password" minlength="8" required>
      <div class="strength"><i data-strength></i></div><small data-strength-label>Mínimo de 8 caracteres. Uma frase longa é mais forte e mais fácil de lembrar.</small></label>
    <label class="field">Repita a senha<input name="confirm" type="password" autocomplete="new-password" required></label>`;
}
function bindStrength(dialog) {
  const input = $('[name=password]', dialog);
  input.addEventListener('input', () => {
    const level = strength(input.value);
    $('[data-strength]', dialog).style.cssText = `width:${(level + 1) * 20}%;background:${STRENGTH[level][1]}`;
    $('[data-strength-label]', dialog).textContent = input.value ? STRENGTH[level][0] : 'Mínimo de 8 caracteres.';
  });
}

/** Show the recovery key once, and make the user confirm it was stored. */
async function showRecovery(code, title = 'Guarde sua chave de recuperação') {
  await modal(`<form>
    <div class="dialog-head"><h2>${esc(title)}</h2></div>
    <p>Se esquecer a senha, esta chave é <b>a única forma</b> de abrir seus dados. Ela aparece só agora: anote no papel ou guarde no gerenciador de senhas. Não a deixe em arquivo no mesmo computador.</p>
    <div class="recovery-code">${esc(code)}</div>
    <div class="row"><button type="button" class="btn small" id="copy-code">${icon('copy')}Copiar</button><button type="button" class="btn small" id="print-code">${icon('file')}Imprimir</button></div>
    <label class="row" style="font-size:13px;text-align:left"><input type="checkbox" required> Guardei a chave em um lugar seguro</label>
    <div class="dialog-foot"><span></span><button class="btn primary">Concluir</button></div>
  </form>`, { onOpen: dialog => {
    dialog.addEventListener('cancel', e => e.preventDefault(), true);  // must acknowledge
    $('#copy-code', dialog).addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(code); toast('Chave copiada. Cole no gerenciador de senhas e limpe a área de transferência.'); } catch { toast('Não foi possível copiar.', 'error'); }
    });
    $('#print-code', dialog).addEventListener('click', () => {
      const w = window.open('', '_blank', 'width=600,height=400');
      if (!w) return toast('Permita a janela de impressão.', 'error');
      w.document.write(`<title>Chave de recuperação</title><body style="font:16px system-ui;padding:40px"><h2>Meus Gastos · chave de recuperação</h2><p>Guarde em local seguro, longe do computador.</p><pre style="font-size:22px;letter-spacing:.08em">${esc(code)}</pre></body>`);
      w.document.close();
      w.print();
    });
  } });
}

export default async function securitySection(target) {
  const status = await api('security/status');
  const exposed = (await api('security/exposed')).groups;
  store.security = { ...store.security, ...status };
  target.innerHTML = `
  <article class="card" style="margin-bottom:16px">
    <div class="card-head"><div><h2>${icon('lock', 'width="17" height="17" style="vertical-align:-3px"')} Proteção dos dados</h2>
      <p>${status.protected ? 'Banco criptografado com AES-256-GCM. A chave é derivada da sua senha (scrypt) e nunca é gravada.' : 'Hoje o banco fica em texto aberto: qualquer programa ou pessoa com acesso a este usuário do Windows consegue lê-lo.'}</p></div>
      <span class="chip ${status.protected ? 'good' : 'bad'}">${status.protected ? 'Protegido' : 'Sem proteção'}</span></div>
    ${status.protected ? `
      <div class="list-row">${icon('lock', 'width="20" height="20"')}<div class="grow"><b>Bloqueio automático</b><small>Após este tempo sem uso, o app fecha os dados da memória e pede a senha de novo.</small></div>
        <select id="auto-lock">${options(AUTO_LOCK, status.auto_lock)}</select></div>
      <div class="list-row">${icon('edit', 'width="20" height="20"')}<div class="grow"><b>Trocar senha</b><small>A chave de recuperação continua valendo.</small></div><button class="btn small" id="change-password">Trocar</button></div>
      <div class="list-row">${icon('repeat', 'width="20" height="20"')}<div class="grow"><b>Nova chave de recuperação</b><small>Invalida a chave anterior. Use se ela pode ter sido vista por alguém.</small></div><button class="btn small" id="new-recovery">Gerar</button></div>
      <div class="list-row">${icon('alert', 'width="20" height="20"')}<div class="grow"><b>Remover proteção</b><small>Volta a gravar o banco sem criptografia.</small></div><button class="btn small danger" id="disable">Remover</button></div>`
    : `<div class="banner" style="margin:0">${icon('info')}<div class="grow">Ao ativar, o banco passa a ficar só no arquivo criptografado <code>data/financas.cofre</code>; o arquivo aberto é sobrescrito e apagado. Você recebe uma chave de recuperação para o caso de esquecer a senha.</div>
        <button class="btn primary" id="enable">Proteger com senha</button></div>`}
  </article>
  <article class="card" style="margin-bottom:16px">
    <div class="card-head"><div><h2>Cópias sem proteção neste computador</h2><p>Arquivos fora do banco que podem conter dados financeiros legíveis.</p></div>
      <span class="chip ${exposed.length ? 'warn' : 'good'}">${exposed.length ? `${exposed.reduce((s, g) => s + g.count, 0)} arquivos` : 'Nenhum'}</span></div>
    ${exposed.map(g => `<div class="list-row">${icon('file', 'width="20" height="20"')}<div class="grow"><b>${esc(g.label)}</b>
        <small>${esc(g.folder)} · ${g.count} ${g.count === 1 ? 'arquivo' : 'arquivos'} · ${kb(g.bytes)} · ${g.files.slice(0, 3).map(esc).join(', ')}${g.count > 3 ? '…' : ''}</small></div>
        <button class="btn small danger" data-wipe="${esc(g.key)}">Apagar</button></div>`).join('') || '<p class="muted">Nenhum arquivo exposto encontrado nas pastas do app.</p>'}
    <p style="font-size:12px;margin-top:10px" class="muted">Apagar sobrescreve o conteúdo antes de remover. Em SSD isso não garante a destruição física: ative o BitLocker no Windows para proteger o disco inteiro. Downloads (PDFs, CSVs, backups) ficam fora desta lista.</p>
  </article>`;

  $('#enable', target)?.addEventListener('click', async () => {
    const result = await modal(`<form>
      <div class="dialog-head"><h2>Proteger com senha</h2><button type="button" class="icon-btn" data-close aria-label="Fechar">${icon('x')}</button></div>
      <p>O app vai pedir esta senha ao abrir e depois de ficar parado. Sem a senha e sem a chave de recuperação, <b>ninguém consegue recuperar os dados, nem você</b>.</p>
      ${passwordFields()}
      <label class="row" style="font-size:13px"><input type="checkbox" name="ack" required> Entendi que não existe “esqueci a senha” sem a chave de recuperação</label>
      <div class="dialog-foot"><button type="button" class="btn" data-close>Cancelar</button><button class="btn primary">Criptografar banco</button></div>
    </form>`, { onOpen: bindStrength });
    if (!result) return;
    const f = Object.fromEntries(result.data);
    if (f.password !== f.confirm) return toast('As senhas não conferem.', 'error');
    const response = await guard(() => api('security/enable', { password: f.password }));
    if (!response) return;
    await showRecovery(response.recovery);
    toast('Banco criptografado.');
    await refresh();
  });

  $('#auto-lock', target)?.addEventListener('change', e => guard(() => api('security/auto-lock', { minutes: +e.target.value }), 'Bloqueio automático atualizado.'));

  $('#change-password', target)?.addEventListener('click', async () => {
    const result = await modal(`<form>
      <div class="dialog-head"><h2>Trocar senha</h2><button type="button" class="icon-btn" data-close aria-label="Fechar">${icon('x')}</button></div>
      <label class="field">Senha atual<input name="current" type="password" autocomplete="current-password" required></label>
      ${passwordFields('Nova ')}
      <div class="dialog-foot"><button type="button" class="btn" data-close>Cancelar</button><button class="btn primary">Trocar senha</button></div>
    </form>`, { onOpen: bindStrength });
    if (!result) return;
    const f = Object.fromEntries(result.data);
    if (f.password !== f.confirm) return toast('As senhas não conferem.', 'error');
    await guard(() => api('security/password', { current: f.current, new: f.password }), 'Senha trocada. Outras janelas abertas vão pedir a senha nova.');
  });

  $('#new-recovery', target)?.addEventListener('click', async () => {
    const result = await modal(`<form>
      <div class="dialog-head"><h2>Gerar nova chave de recuperação</h2><button type="button" class="icon-btn" data-close aria-label="Fechar">${icon('x')}</button></div>
      <p>A chave atual deixa de funcionar.</p>
      <label class="field">Senha atual<input name="password" type="password" autocomplete="current-password" required></label>
      <div class="dialog-foot"><button type="button" class="btn" data-close>Cancelar</button><button class="btn primary">Gerar</button></div>
    </form>`);
    if (!result) return;
    const response = await guard(() => api('security/recovery', { password: result.data.get('password') }));
    if (response) await showRecovery(response.recovery, 'Nova chave de recuperação');
  });

  $('#disable', target)?.addEventListener('click', async () => {
    const result = await modal(`<form>
      <div class="dialog-head"><h2>Remover proteção?</h2><button type="button" class="icon-btn" data-close aria-label="Fechar">${icon('x')}</button></div>
      <p>O banco volta a ser gravado sem criptografia em <code>data/financas.sqlite3</code> e o cofre é apagado.</p>
      <label class="field">Senha atual<input name="password" type="password" autocomplete="current-password" required></label>
      <div class="dialog-foot"><button type="button" class="btn" data-close>Cancelar</button><button class="btn danger">Remover proteção</button></div>
    </form>`);
    if (!result) return;
    if (await guard(() => api('security/disable', { password: result.data.get('password') }), 'Proteção removida.')) await refresh();
  });

  $$('[data-wipe]', target).forEach(button => button.addEventListener('click', async () => {
    const group = exposed.find(g => g.key === button.dataset.wipe);
    const sure = await confirmDialog(`Apagar ${group.label.toLowerCase()}?`,
      `${group.count} ${group.count === 1 ? 'arquivo' : 'arquivos'} em <code>${esc(group.folder)}</code> serão sobrescritos e apagados. Isso não pode ser desfeito.${group.key === 'faturas' ? ' Se quiser guardar as faturas originais, mova-as antes para um local protegido.' : ''}`, 'Apagar definitivamente', true);
    if (!sure) return;
    const response = await guard(() => api('security/wipe', { group: group.key }));
    if (response) { toast(`${response.removed} arquivos apagados.`); securitySection(target); }
  }));
}
