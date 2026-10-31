import { store, refresh, categoryOptions, KINDS, CHANNELS } from '../main.js';
import { api } from '../api.js';
import { $, $$, icon, guard, options, toast, confirmDialog } from '../ui.js';
import { esc, money, monthLong, parseMoney, centsInput, prettyName, today, dateBR } from '../format.js';

// Wizard state survives page switches inside the session (not persisted).
const wizard = { queue: [], current: null, done: [], onlyReview: false };

export default function importer(app) {
  app.innerHTML = `<div class="steps" id="steps"></div><div id="wizard"></div>
  <section class="grid cols-2 mt">
    <article class="card"><div class="card-head"><div><h2>Arquivos aceitos</h2><p>Sem conectar contas: você baixa o arquivo no app do banco e traz para cá.</p></div></div>
      <div class="list-row">${icon('file', 'width="20" height="20"')}<div class="grow"><b>Santander · fatura do cartão (PDF)</b><small>Inclui cartões adicionais, parcelas, IOF e estornos. Aceita PDF com senha.</small></div></div>
      <div class="list-row">${icon('file', 'width="20" height="20"')}<div class="grow"><b>Santander · extrato consolidado (PDF)</b><small>Conta corrente: PIX, boletos, ganhos e transferências, conferidos com os saldos.</small></div></div>
      <div class="list-row">${icon('file', 'width="20" height="20"')}<div class="grow"><b>Nubank · fatura ou conta (CSV)</b><small>Exporte pelo app em “Exportar fatura” ou “Exportar extrato”.</small></div></div>
      <div class="list-row">${icon('file', 'width="20" height="20"')}<div class="grow"><b>Qualquer banco · CSV simples</b><small>Colunas <code>data;descricao;valor</code>, ex.: 02/09/2026;Mercado;123,45</small></div></div>
      <p class="mt" style="font-size:12.5px">${icon('lock', 'width="14" height="14" style="vertical-align:-2px"')} O arquivo e a senha são lidos em memória pelo servidor local e não são guardados. O mesmo arquivo nunca é importado duas vezes.</p>
    </article>
    <article class="card"><div class="card-head"><div><h2>Importações salvas</h2><p>Remover uma importação também remove os lançamentos dela.</p></div></div>
      ${store.data.imports.length ? store.data.imports.map(i => `<div class="list-row"><div class="grow"><b>${esc(i.filename)}</b><small>${esc(dateBR(i.created_at.slice(0, 10)))} · ${store.data.transactions.filter(t => t.import_id === i.id).length} lançamentos</small></div><button class="btn small danger" data-remove-import="${i.id}">Remover</button></div>`).join('') : '<p class="muted">Nenhuma importação ainda.</p>'}
    </article>
  </section>`;
  $$('[data-remove-import]', app).forEach(b => b.addEventListener('click', async () => {
    if (!await confirmDialog('Remover importação?', 'Todos os lançamentos lidos deste arquivo serão excluídos. Esta ação não pode ser desfeita.', 'Remover', true)) return;
    if (await guard(() => api('delete', { kind: 'imports', id: +b.dataset.removeImport }), 'Importação removida.')) await refresh();
  }));
  step(app);
}

function step(app) {
  const s = wizard.current ? 2 : wizard.done.length && !wizard.queue.length ? 3 : 1;
  $('#steps', app).innerHTML = [['Escolher arquivos', 1], ['Revisar', 2], ['Pronto', 3]].map(([label, n], i) =>
    `${i ? '<span class="sep"></span>' : ''}<span class="step ${n === s ? 'on' : n < s ? 'done' : ''}"><b>${n < s ? '✓' : n}</b>${label}</span>`).join('');
  if (s === 2) return review(app);
  if (s === 3) return finished(app);
  pick(app);
}

function pick(app) {
  const target = $('#wizard', app);
  target.innerHTML = `<article class="card">
    <label class="dropzone" id="drop" tabindex="0">
      ${icon('upload')}<h3>Arraste faturas e extratos aqui</h3><p>ou clique para escolher · PDF ou CSV · vários arquivos de uma vez</p>
      <input type="file" id="file" accept=".pdf,.csv" multiple hidden>
    </label>
    <div class="file-queue" id="queue"></div>
  </article>`;
  const input = $('#file', target), drop = $('#drop', target);
  input.addEventListener('change', () => add(app, [...input.files]));
  drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  ['dragenter', 'dragover'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove('drag'); }));
  drop.addEventListener('drop', e => add(app, [...e.dataTransfer.files]));
  queue(app);
}

function queue(app) {
  const target = $('#queue', app);
  if (!target) return;
  target.innerHTML = wizard.queue.map((f, i) => `<div class="file-item">${icon('file', 'width="20" height="20"')}
    <div class="grow"><b>${esc(f.file.name)}</b><small>${f.status === 'reading' ? 'Lendo…' : f.error ? `<span style="color:var(--bad)">${esc(f.error)}</span>` : `${(f.file.size / 1024).toFixed(0)} KB · aguardando`}</small></div>
    ${f.needsPassword ? `<input type="password" placeholder="Senha do PDF" data-password="${i}" autocomplete="off" style="width:160px"><button class="btn small primary" data-retry="${i}">Abrir</button>` : ''}
    ${f.error && !f.needsPassword ? '' : ''}<button class="icon-btn" data-drop="${i}" aria-label="Remover da fila">${icon('x')}</button></div>`).join('');
  $$('[data-drop]', target).forEach(b => b.addEventListener('click', () => { wizard.queue.splice(+b.dataset.drop, 1); queue(app); }));
  $$('[data-retry]', target).forEach(b => b.addEventListener('click', () => {
    const item = wizard.queue[+b.dataset.retry];
    item.password = $(`[data-password="${b.dataset.retry}"]`, target).value;
    next(app);
  }));
  $$('[data-password]', target).forEach(p => p.addEventListener('keydown', e => { if (e.key === 'Enter') $(`[data-retry="${p.dataset.password}"]`, target).click(); }));
  $$('[data-password]', target)[0]?.focus();
}

async function add(app, files) {
  const valid = files.filter(f => /\.(pdf|csv)$/i.test(f.name));
  if (valid.length < files.length) toast('Alguns arquivos foram ignorados: use PDF ou CSV.', 'error');
  wizard.queue.push(...valid.map(file => ({ file, password: '' })));
  next(app);
}

const toBase64 = file => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result).split(',')[1]);
  reader.onerror = () => reject(new Error('Não foi possível ler o arquivo.'));
  reader.readAsDataURL(file);
});

/** Read the next waiting file; protected PDFs wait for their password. */
async function next(app) {
  const item = wizard.queue.find(f => !f.error || (f.needsPassword && f.password));
  if (!item) return queue(app);
  item.status = 'reading'; item.error = '';
  queue(app);
  try {
    if (item.file.size > 20 * 1024 * 1024) throw new Error('Arquivo maior que 20 MB.');
    const content = await toBase64(item.file);
    const preview = await api('preview', { content, filename: item.file.name, month: store.month || today().slice(0, 7), password: item.password || '', provider: 'auto' });
    wizard.queue.splice(wizard.queue.indexOf(item), 1);
    preview.rows.forEach(r => { r.include = r.include ?? true; });
    wizard.current = { ...preview, filename: item.file.name };
    step(app);
  } catch (error) {
    item.status = '';
    item.error = error.message;
    item.needsPassword = /senha/i.test(error.message);
    item.password = '';
    queue(app);
  }
}

function review(app) {
  const p = wizard.current, m = p.metadata;
  const target = $('#wizard', app);
  const included = p.rows.filter(r => r.include);
  const sum = included.reduce((s, r) => s + r.cents, 0);
  const toReview = p.rows.filter(r => r.category === 'Outros' || r.confidence === 'medium' || r.suggested_category);
  let check = '';
  if (m.source_type === 'statement' && m.credits_cents !== undefined) {
    const inc = -included.reduce((s, r) => s + Math.min(r.cents, 0), 0), out = included.reduce((s, r) => s + Math.max(r.cents, 0), 0);
    const ok = inc === m.credits_cents && out === m.debits_cents;
    check = `<div class="check-tile ${ok ? 'ok' : 'warn'}">${icon(ok ? 'check' : 'alert', 'width="18" height="18"')}<span><b>${ok ? 'Extrato conferido' : 'Confira os totais'}</b><br><small>Entradas ${money(inc)} de ${money(m.credits_cents)} · saídas ${money(out)} de ${money(m.debits_cents)}</small></span></div>`;
  } else if (m.total_cents !== undefined) {
    const diff = sum - m.total_cents;
    check = `<div class="check-tile ${diff === 0 ? 'ok' : 'warn'}">${icon(diff === 0 ? 'check' : 'alert', 'width="18" height="18"')}<span><b>${diff === 0 ? 'Soma bate com o total da fatura' : `Diferença de ${money(diff)}`}</b><br><small>Selecionado ${money(sum)} · fatura ${money(m.total_cents)}</small></span></div>`;
  } else {
    check = `<div class="check-tile">${icon('info', 'width="18" height="18"')}<span><b>Soma selecionada: ${money(sum)}</b><br><small>Este formato não informa total oficial para conferência.</small></span></div>`;
  }
  const rows = wizard.onlyReview ? toReview : p.rows;
  target.innerHTML = `<article class="card">
    <div class="card-head"><div><h2>${esc(p.filename)}</h2><p>${esc(m.detected_format || 'Arquivo reconhecido')} · ${p.rows.length} lançamentos${m.due_date ? ' · vencimento ' + dateBR(m.due_date) : ''}${m.month ? ' · ' + esc(monthLong(m.month)) : ''}${wizard.queue.length ? ` · mais ${wizard.queue.length} na fila` : ''}</p></div>
      <button class="btn small" id="discard">Descartar</button></div>
    <div class="grid cols-3">${check}
      <div class="check-tile ${toReview.length ? 'warn' : 'ok'}">${icon(toReview.length ? 'edit' : 'check', 'width="18" height="18"')}<span><b>${toReview.length ? `${toReview.length} para revisar` : 'Tudo categorizado'}</b><br><small>${toReview.length ? 'Sem categoria ou com sugestão incerta' : 'Pelas suas regras e palavras-chave'}</small></span></div>
      <div class="check-tile">${icon('list', 'width="18" height="18"')}<span><b>${included.length} de ${p.rows.length} selecionados</b><br><small>Desmarque o que não quer salvar</small></span></div>
    </div>
    ${p.warnings.length ? `<div class="banner mt">${icon('info')}<div class="grow" style="font-size:13px">${p.warnings.map(esc).join('<br>')}</div></div>` : ''}
    ${(m.holders || []).length ? `<div class="mt"><h3>Titulares dos cartões</h3><p style="font-size:12.5px">Escolha uma vez: a associação é lembrada nas próximas faturas.</p><div class="grid cols-3 mt">${m.holders.map((h, i) => `<label class="field">${esc(h)}<select data-holder="${i}">${options(store.data.people, m.holder_mapping[h], 'Quem é?')}</select><small>${money(p.rows.filter(r => r.holder === h && r.include).reduce((s, r) => s + r.cents, 0))} · cartões ${[...new Set(p.rows.filter(r => r.holder === h).map(r => '•' + r.card))].join(', ')}</small></label>`).join('')}</div></div>` : ''}
    ${m.source_type === 'invoice' && m.provider === 'nubank' ? `<label class="field mt" style="max-width:260px">Mês da fatura<input type="month" id="invoice-month" value="${esc(m.month)}"><small>O CSV do Nubank não traz o vencimento: confira.</small></label>` : ''}
    <div class="spread mt" style="margin-bottom:8px"><div class="row"><label class="row" style="font-size:13px"><input type="checkbox" id="only-review" ${wizard.onlyReview ? 'checked' : ''}> Mostrar só o que precisa de revisão</label></div>
      <label class="row" style="font-size:13px">Responsável de todos <select id="all-person">${options(store.data.people, '', '—')}</select></label></div>
    <div class="table-wrap" style="max-height:60vh;overflow:auto"><table class="preview-table"><thead><tr><th><input type="checkbox" id="toggle-all" ${included.length === p.rows.length ? 'checked' : ''} aria-label="Selecionar todos"></th><th>Data</th><th>Descrição</th><th class="money">Valor</th><th>Tipo</th><th>Categoria</th><th>Quem</th><th>Detalhes</th></tr></thead><tbody>
    ${rows.map(r => { const i = p.rows.indexOf(r); return `<tr data-row="${i}" class="${r.include ? '' : 'excluded'}">
      <td><input type="checkbox" data-key="include" ${r.include ? 'checked' : ''} aria-label="Incluir"></td>
      <td><input type="date" data-key="date" value="${esc(r.date)}" aria-label="Data"></td>
      <td><input data-key="description" value="${esc(r.description)}" aria-label="Descrição"></td>
      <td class="money"><input data-key="amount" value="${centsInput(r.cents)}" aria-label="Valor"></td>
      <td><select data-key="kind" aria-label="Tipo">${options(KINDS, r.kind)}</select></td>
      <td><select data-key="category" aria-label="Categoria">${categoryOptions(r.kind, r.category)}</select><span class="reason">${r.suggested_category ? `Talvez <b>${esc(r.suggested_category)}</b> · ` : ''}${esc(r.category_reason || '')}</span></td>
      <td><select data-key="person" aria-label="Responsável">${options(store.data.people, r.person)}</select></td>
      <td><span class="meta">${[r.card && '•' + r.card, r.installment && 'parcela ' + r.installment, CHANNELS.find(c => c[0] === r.payment_channel)?.[1]].filter(Boolean).map(esc).join(' · ')}</span></td>
    </tr>`; }).join('')}</tbody></table></div>
    <div class="spread mt"><small>Categorias que você corrigir aqui viram regras para as próximas importações.</small><button class="btn primary" id="confirm">${icon('check')}Salvar ${included.length} lançamentos</button></div>
  </article>`;

  const rerender = () => review(app);
  $('#discard', target).addEventListener('click', () => { wizard.current = null; step(app); next(app); });
  $('#only-review', target).addEventListener('change', e => { wizard.onlyReview = e.target.checked; rerender(); });
  $('#toggle-all', target).addEventListener('change', e => { p.rows.forEach(r => { r.include = e.target.checked; }); rerender(); });
  $('#all-person', target).addEventListener('change', e => { if (e.target.value) { p.rows.forEach(r => { r.person = e.target.value; }); rerender(); } });
  $('#invoice-month', target)?.addEventListener('change', e => { m.month = e.target.value; p.rows.forEach(r => { r.month = e.target.value; }); });
  $$('[data-holder]', target).forEach(s => s.addEventListener('change', () => {
    const holder = m.holders[+s.dataset.holder];
    m.holder_mapping[holder] = s.value;
    p.rows.forEach(r => { if (r.holder === holder && s.value) r.person = s.value; });
    rerender();
  }));
  $$('tr[data-row] [data-key]', target).forEach(el => el.addEventListener('change', () => {
    const r = p.rows[+el.closest('tr').dataset.row], key = el.dataset.key;
    if (key === 'include') { r.include = el.checked; return rerender(); }
    if (key === 'amount') {
      const cents = parseMoney(el.value);
      if (cents == null) { toast('Valor inválido.', 'error'); el.value = centsInput(r.cents); return; }
      r.cents = cents; return rerender();
    }
    r[key] = el.value;
    if (key === 'category' || key === 'kind') { r.category_source = 'manual'; r.suggested_category = ''; }
    if (key === 'kind') { r.category = categoryOptions(r.kind, '').match(/value="([^"]*)"/)?.[1] || r.category; }
    if (key === 'kind' || key === 'category') rerender();
  }));
  $('#confirm', target).addEventListener('click', async () => {
    const chosen = p.rows.filter(r => r.include);
    if ((m.holders || []).some(h => !m.holder_mapping[h])) return toast('Escolha quem é cada titular antes de salvar.', 'error');
    const ok = await guard(() => api('confirm', { token: p.token, rows: chosen, holder_mapping: m.holder_mapping }));
    if (!ok) return;
    wizard.done.push({ filename: p.filename, count: chosen.length, month: m.month || chosen[0]?.month, total: chosen.reduce((s, r) => s + r.cents, 0) });
    wizard.current = null;
    await refresh();
    if (wizard.queue.length) next(document.getElementById('app'));
  });
}

function finished(app) {
  const last = wizard.done[wizard.done.length - 1];
  $('#wizard', app).innerHTML = `<article class="card empty-state">${icon('check')}<h2>Importação concluída</h2>
    <p>${wizard.done.map(d => `<b>${esc(d.filename)}</b>: ${d.count} lançamentos`).join('<br>')}</p>
    <div class="row"><a class="btn primary" href="/" data-link>Ver painel</a><button class="btn" id="more">Importar mais</button></div></article>`;
  $('#more', app).addEventListener('click', () => { wizard.done = []; step(app); });
  store.month = store.data.default_months?.[store.basis] || store.month;
}
