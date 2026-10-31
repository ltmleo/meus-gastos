import { store, refresh, categoryOptions, monthOf, KINDS, CHANNELS, BANKS, PEOPLE_COLORS } from '../main.js';
import { api } from '../api.js';
import { $, $$, icon, guard, options, modal, confirmDialog, toast, segmented } from '../ui.js';
import { esc, money, monthShort, dateShort, prettyName, parseMoney, centsInput, today } from '../format.js';

const PAGE = 80;
const KIND_LABEL = Object.fromEntries(KINDS);
const BANK_LABEL = Object.fromEntries(BANKS);
const state = { q: '', month: '', category: '', person: '', kind: '', channel: '', max: '', view: 'list', page: 0, selected: new Set() };

/** Mirrors finance.classification.merchant_key so groups match the server's rule. */
export function merchantKey(description) {
  let t = description.toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Z0-9]+/g, ' ').trim();
  t = t.replace(/^\d{2} \d{2}(?: \d{4})? /, '');
  t = t.replace(/^(?:PIX (?:ENVIADO|RECEBIDO)|PAGAMENTO DE BOLETO(?: OUTROS BANCOS)?|COMPRA CARTAO DEB MC \d{2} \d{2})\s+/, '');
  return t.replace(/^(?:MP|DL|HNA|PAG|PAGSEGURO)\s+/, '');
}

export default function transactions(app, params) {
  Object.assign(state, { q: params.get('q') || '', month: params.has('m') ? params.get('m') : store.month, category: params.get('categoria') || '',
    person: params.get('p') || '', kind: params.get('tipo') || '', max: params.get('max') || '', page: 0, selected: new Set() });
  if (params.get('categoria') === 'Outros') state.view = 'pending';
  else state.view = 'list';
  shell(app);
}

function filtered() {
  const q = state.q.trim().toLocaleLowerCase('pt-BR');
  const max = state.max ? +state.max : null;
  return store.data.transactions.filter(r =>
    (!state.month || monthOf(r) === state.month) && (!state.category || r.category === state.category) &&
    (!state.person || r.person === state.person) && (!state.kind || r.kind === state.kind) &&
    (!state.channel || r.payment_channel === state.channel) && (max == null || (r.cents > 0 && r.cents < max)) &&
    (!q || r.description.toLocaleLowerCase('pt-BR').includes(q) || prettyName(r.description).toLocaleLowerCase('pt-BR').includes(q) || String(r.cents / 100).includes(q)));
}

function shell(app) {
  const months = store.months || [];
  app.innerHTML = `
  <div class="filters">
    <label class="search">${icon('search')}<input id="f-q" type="search" placeholder="Buscar descrição ou valor…" value="${esc(state.q)}" aria-label="Buscar"></label>
    <select id="f-month" aria-label="Mês">${options(months.map(m => [m, monthShort(m)]), state.month, 'Todos os meses')}</select>
    <select id="f-category" aria-label="Categoria">${categoryOptions('', state.category, 'Todas as categorias')}</select>
    <select id="f-person" aria-label="Responsável">${options(store.data.people, state.person, 'Todos')}</select>
    <select id="f-kind" aria-label="Tipo">${options(KINDS, state.kind, 'Todos os tipos')}</select>
    <select id="f-channel" aria-label="Meio">${options(CHANNELS, state.channel, 'Cartão e conta')}</select>
  </div>
  <div class="spread" style="margin-bottom:12px">
    ${segmented('view', [['list', 'Lista'], ['pending', `A classificar (${store.pending})`]], state.view)}
    <div class="row"><button class="btn small" id="review">${icon('spark')}Revisar sugestões</button><button class="btn small primary" id="new">${icon('plus')}Novo lançamento</button></div>
  </div>
  <div id="tx-body"></div>`;
  const bind = (id, key, event = 'change') => $(id, app).addEventListener(event, e => { state[key] = e.target.value; state.page = 0; state.selected.clear(); body(app); });
  bind('#f-q', 'q', 'input'); bind('#f-month', 'month'); bind('#f-category', 'category'); bind('#f-person', 'person'); bind('#f-kind', 'kind'); bind('#f-channel', 'channel');
  $$('[data-seg="view"] button', app).forEach(b => b.addEventListener('click', () => {
    state.view = b.dataset.value;
    $$('[data-seg="view"] button', app).forEach(x => x.classList.toggle('on', x === b));
    body(app);
  }));
  $('#new', app).addEventListener('click', () => editor());
  $('#review', app).addEventListener('click', review);
  body(app);
}

function body(app) {
  const target = $('#tx-body', app);
  if (state.view === 'pending') return pending(target);
  const rows = filtered();
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  state.page = Math.min(state.page, pages - 1);
  const visible = rows.slice(state.page * PAGE, (state.page + 1) * PAGE);
  const expenses = rows.filter(r => r.kind === 'expense').reduce((s, r) => s + r.cents, 0);
  const income = -rows.filter(r => r.kind === 'income').reduce((s, r) => s + r.cents, 0);
  target.innerHTML = `
  <article class="card">
    <div class="spread" style="margin-bottom:6px"><div class="row"><b>${rows.length} lançamentos</b>${state.max ? `<span class="chip info">abaixo de ${money(+state.max)} <button class="ghost small" id="clear-max" aria-label="Remover filtro">×</button></span>` : ''}</div>
      <div class="row"><span class="chip">Gastos ${money(expenses)}</span>${income ? `<span class="chip good">Ganhos ${money(income)}</span>` : ''}</div></div>
    ${rows.length ? `<div class="table-wrap"><table>
      <thead><tr><th style="width:28px"><input type="checkbox" id="select-all" aria-label="Selecionar página"></th><th>Data</th><th>Descrição</th><th>Categoria</th><th>Quem</th><th class="money">Valor</th><th></th></tr></thead>
      <tbody>${visible.map(row).join('')}</tbody></table></div>` : '<div class="empty-state"><p>Nenhum lançamento com esses filtros.</p></div>'}
    ${pages > 1 ? `<div class="pager"><span>Página ${state.page + 1} de ${pages}</span><div class="row"><button class="btn small" data-page="-1" ${state.page ? '' : 'disabled'}>Anterior</button><button class="btn small" data-page="1" ${state.page < pages - 1 ? '' : 'disabled'}>Próxima</button></div></div>` : ''}
  </article>
  <div id="bulk"></div>`;
  $('#clear-max', target)?.addEventListener('click', () => { state.max = ''; body(app); });
  $$('[data-page]', target).forEach(b => b.addEventListener('click', () => { state.page += +b.dataset.page; body(app); window.scrollTo({ top: 0 }); }));
  $('#select-all', target)?.addEventListener('change', e => { visible.forEach(r => e.target.checked ? state.selected.add(r.id) : state.selected.delete(r.id)); body(app); });
  $$('[data-select]', target).forEach(c => c.addEventListener('change', () => { const id = +c.dataset.select; c.checked ? state.selected.add(id) : state.selected.delete(id); c.closest('tr').classList.toggle('selected', c.checked); bulk(app); }));
  $$('[data-edit]', target).forEach(b => b.addEventListener('click', () => editor(store.data.transactions.find(r => r.id === +b.dataset.edit))));
  $$('select[data-inline]', target).forEach(s => s.addEventListener('change', () => inlineChange(app, +s.dataset.id, s.dataset.inline, s.value)));
  bulk(app);
}

function row(r) {
  const meta = [r.card && `•${r.card}`, r.installment && `parcela ${r.installment}`, r.payment_channel === 'account' ? 'conta' : r.payment_channel === 'credit' ? 'crédito' : '', BANK_LABEL[r.bank] && r.bank !== 'unspecified' ? BANK_LABEL[r.bank] : '', r.kind !== 'expense' ? KIND_LABEL[r.kind] : ''].filter(Boolean);
  return `<tr class="${state.selected.has(r.id) ? 'selected' : ''}">
    <td><input type="checkbox" data-select="${r.id}" ${state.selected.has(r.id) ? 'checked' : ''} aria-label="Selecionar"></td>
    <td class="num" style="white-space:nowrap">${dateShort(r.date)}<div class="meta" title="Mês da fatura/extrato">${r.payment_channel === 'credit' ? 'fatura ' : ''}${monthShort(r.month)}</div></td>
    <td><span class="desc" title="${esc(r.description)}">${esc(prettyName(r.description))}</span><span class="meta">${meta.map(esc).join(' · ')}</span></td>
    <td><select class="inline" data-inline="category" data-id="${r.id}" aria-label="Categoria">${categoryOptions(r.kind, r.category)}</select>${r.category === 'Outros' ? ' <span class="chip warn">revisar</span>' : ''}</td>
    <td><select class="inline" data-inline="person" data-id="${r.id}" aria-label="Responsável">${options(store.data.people, r.person)}</select></td>
    <td class="money ${r.cents < 0 ? 'neg' : ''}"><b style="font-weight:600">${money(r.kind === 'income' ? -r.cents : r.cents)}</b></td>
    <td><button class="icon-btn" data-edit="${r.id}" aria-label="Editar">${icon('edit')}</button></td>
  </tr>`;
}

async function inlineChange(app, id, key, value) {
  const ok = await guard(() => api('bulk-update', { ids: [id], changes: { [key]: value } }));
  if (!ok) return;
  const current = store.data.transactions.find(r => r.id === id);
  current[key] = value;
  if (key === 'category') current.category_source = 'manual';
  toast('Salvo.');
  if (key === 'category') {
    const key2 = merchantKey(current.description);
    const siblings = store.data.transactions.filter(r => r.id !== id && r.kind === current.kind && r.category !== value && merchantKey(r.description) === key2);
    const remember = await confirmDialog('Aplicar aos parecidos?', `Encontramos ${siblings.length ? `<b>${siblings.length}</b> outros lançamentos de` : 'nenhum outro lançamento de'} <b>${esc(prettyName(current.description))}</b>. Quer classificá-los como <b>${esc(value)}</b> e lembrar essa regra nas próximas importações?`, 'Aplicar e lembrar');
    if (remember) {
      await guard(() => api('classify-group', { ids: [id, ...siblings.map(r => r.id)], category: value, kind: current.kind, remember: true }), 'Regra salva.');
    }
    await refresh();
  }
}

function bulk(app) {
  const target = $('#bulk', app);
  if (!target) return;
  const n = state.selected.size;
  if (!n) { target.innerHTML = ''; return; }
  target.innerHTML = `<div class="bulkbar"><b>${n} selecionados</b>
    <select data-bulk="category" aria-label="Categoria">${categoryOptions('', '', 'Mudar categoria…')}</select>
    <select data-bulk="person" aria-label="Responsável">${options(store.data.people, '', 'Mudar responsável…')}</select>
    <select data-bulk="kind" aria-label="Tipo">${options(KINDS, '', 'Mudar tipo…')}</select>
    <button class="ghost" id="bulk-clear">Limpar seleção</button></div>`;
  $$('[data-bulk]', target).forEach(s => s.addEventListener('change', async () => {
    if (!s.value) return;
    const ok = await guard(() => api('bulk-update', { ids: [...state.selected], changes: { [s.dataset.bulk]: s.value } }), `${n} lançamentos atualizados.`);
    if (ok) { state.selected.clear(); await refresh(); }
  }));
  $('#bulk-clear', target).addEventListener('click', () => { state.selected.clear(); body(app); });
}

function pending(target) {
  const rows = store.data.transactions.filter(r => r.category === 'Outros' && r.kind === 'expense' && (!state.person || r.person === state.person));
  const groups = new Map();
  rows.forEach(r => {
    const key = merchantKey(r.description);
    const g = groups.get(key) || { key, rows: [], cents: 0 };
    g.rows.push(r); g.cents += r.cents; groups.set(key, g);
  });
  const list = [...groups.values()].sort((a, b) => b.cents - a.cents);
  target.innerHTML = `<article class="card"><div class="card-head"><div><h2>Gastos sem categoria</h2><p>Todos os meses, agrupados por estabelecimento ou destinatário. Classifique uma vez e a regra vale para as próximas importações.</p></div></div>
    ${list.length ? list.map((g, i) => `<div class="list-row"><div class="grow"><b>${esc(prettyName(g.rows[0].description))}</b><small>${g.rows.length} ${g.rows.length === 1 ? 'lançamento' : 'lançamentos'} · ${g.rows.map(r => dateShort(r.date)).slice(0, 4).join(', ')}${g.rows.length > 4 ? '…' : ''}</small></div>
      <div class="end">${money(g.cents)}</div>
      <select data-group="${i}" aria-label="Categoria">${categoryOptions('expense', '', 'Escolher categoria…')}<optgroup label="Não é gasto">${options([['transfer:Transferências', 'Transferência entre contas'], ['transfer:Investimentos', 'Investimento']])}</optgroup></select></div>`).join('')
      : `<div class="empty-state">${icon('check')}<h3>Tudo classificado</h3><p>Nenhum gasto em Outros com os filtros atuais.</p></div>`}</article>`;
  $$('[data-group]', target).forEach(s => s.addEventListener('change', async () => {
    if (!s.value) return;
    const g = list[+s.dataset.group];
    const [kind, category] = s.value.includes(':') ? s.value.split(':') : ['expense', s.value];
    const ok = await guard(() => api('classify-group', { ids: g.rows.map(r => r.id), category, kind, remember: true }), `${g.rows.length} classificados como ${category}.`);
    if (ok) await refresh();
  }));
}

export async function editor(existing) {
  const r = existing || { date: today(), month: store.month || today().slice(0, 7), description: '', cents: 0, kind: 'expense', category: 'Outros', person: store.person || store.data.people[0], payment_channel: 'unspecified', bank: 'unspecified' };
  const result = await modal(`<form>
    <div class="dialog-head"><h2>${existing ? 'Editar lançamento' : 'Novo lançamento'}</h2><button type="button" class="icon-btn" data-close aria-label="Fechar">${icon('x')}</button></div>
    ${existing ? `<small>Original: ${esc(existing.description)}${existing.installment ? ' · parcela ' + esc(existing.installment) : ''}${existing.card ? ' · cartão •' + esc(existing.card) : ''}</small>` : ''}
    <label class="field">Descrição<input name="description" required maxlength="500" value="${esc(r.description)}"></label>
    <div class="grid cols-2"><label class="field">Tipo<select name="kind">${options(KINDS, r.kind)}</select></label>
      <label class="field">Valor (R$)<input name="amount" required inputmode="decimal" value="${centsInput(r.kind === 'income' ? -r.cents : r.cents)}"><small data-amount-hint></small></label></div>
    <div class="suggest-box" id="suggest"><span>Digite a descrição para receber uma sugestão de categoria.</span></div>
    <div class="grid cols-2"><label class="field">Categoria<select name="category">${categoryOptions(r.kind, r.category)}</select></label>
      <label class="field">Responsável<select name="person">${options(store.data.people, r.person)}</select></label></div>
    <div class="grid cols-2"><label class="field">Data da compra<input type="date" name="date" required value="${esc(r.date)}"></label>
      <label class="field">Mês de referência<input type="month" name="month" required value="${esc(r.month)}"><small>Mês da fatura/extrato. Nos painéis, o gasto conta no mês da compra.</small></label></div>
    <div class="grid cols-2"><label class="field">Meio<select name="payment_channel">${options(CHANNELS, r.payment_channel)}</select></label>
      <label class="field">Banco<select name="bank">${options(BANKS, r.bank)}</select></label></div>
    <label class="row" style="font-size:13px"><input type="checkbox" name="remember" checked> Lembrar a categoria para este estabelecimento</label>
    <div class="dialog-foot">${existing ? `<button type="submit" class="btn danger" value="delete" formnovalidate>${icon('trash')}Excluir</button>` : '<span></span>'}<div class="row"><button type="button" class="btn" data-close>Cancelar</button><button class="btn primary" value="save">Salvar</button></div></div>
  </form>`, { onOpen: dialog => {
    const form = $('form', dialog);
    const hint = () => { $('[data-amount-hint]', form).textContent = { expense: 'Gasto positivo; estorno com sinal negativo.', income: 'Valor recebido, sem sinal.', transfer: 'Saída positiva, entrada negativa.' }[form.kind.value]; };
    hint();
    let timer;
    const suggest = async () => {
      if (!form.description.value.trim()) return;
      const s = await api('classify', { description: form.description.value, kind: form.kind.value, id: existing?.id }).catch(() => null);
      if (!s) return;
      $('#suggest', form).innerHTML = `<span>Sugestão: <b>${esc(s.category)}</b> · <small>${esc(s.category_reason || '')}</small></span>${s.category !== form.category.value ? '<button type="button" class="btn small" id="use-suggestion">Usar</button>' : ''}`;
      $('#use-suggestion', form)?.addEventListener('click', () => { form.category.value = s.category; suggest(); });
    };
    form.description.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(suggest, 350); });
    form.kind.addEventListener('change', () => { form.category.innerHTML = categoryOptions(form.kind.value, form.category.value); hint(); suggest(); });
    form.category.addEventListener('change', suggest);
    suggest();
  } });
  if (!result) return;
  if (result.submitter === 'delete') {
    if (await confirmDialog('Excluir lançamento?', 'Esta ação não pode ser desfeita.', 'Excluir', true)) {
      if (await guard(() => api('delete', { kind: 'transactions', id: existing.id }), 'Lançamento excluído.')) await refresh();
    }
    return;
  }
  const f = Object.fromEntries(result.data);
  let cents = parseMoney(f.amount);
  if (cents == null) return toast('Valor inválido. Use o formato 123,45.', 'error');
  if (f.kind === 'income') cents = -Math.abs(cents);
  const rowData = { description: f.description, kind: f.kind, cents, category: f.category, person: f.person, date: f.date, month: f.month, payment_channel: f.payment_channel, bank: f.bank };
  if (await guard(() => api('save', { row: rowData, id: existing?.id, remember: Boolean(f.remember) }), 'Lançamento salvo.')) await refresh();
}

async function review() {
  const { rows } = await api('category-review');
  if (!rows.length) return toast('Nenhuma sugestão nova: suas categorias estão em dia.');
  const result = await modal(`<form style="width:min(760px,calc(100vw - 32px))">
    <div class="dialog-head"><h2>Sugestões de categoria</h2><button type="button" class="icon-btn" data-close aria-label="Fechar">${icon('x')}</button></div>
    <p>O classificador local encontrou ${rows.length} lançamentos que podem ser melhor classificados. Correções manuais nunca são alteradas.</p>
    <div class="table-wrap" style="max-height:50vh;overflow:auto"><table><thead><tr><th></th><th>Descrição</th><th>Atual</th><th>Sugestão</th><th class="money">Valor</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td><input type="checkbox" name="id" value="${r.id}" ${r.confidence === 'high' ? 'checked' : ''}></td><td><span class="desc">${esc(prettyName(r.description))}</span><span class="meta">${esc(r.category_reason || '')}</span></td><td>${esc(r.previous_category)}${r.previous_kind !== r.kind ? ' · ' + KIND_LABEL[r.previous_kind] : ''}</td><td><b>${esc(r.category)}</b>${r.previous_kind !== r.kind ? ' · ' + KIND_LABEL[r.kind] : ''}</td><td class="money">${money(r.cents)}</td></tr>`).join('')}
    </tbody></table></div>
    <div class="dialog-foot"><button type="button" class="btn" data-close>Cancelar</button><button class="btn primary">Aplicar selecionadas</button></div></form>`);
  if (!result) return;
  const ids = result.data.getAll('id').map(Number);
  if (ids.length && await guard(() => api('category-review', { ids }), `${ids.length} lançamentos atualizados.`)) await refresh();
}
