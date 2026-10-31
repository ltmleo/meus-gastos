import { store, refresh, setBasis, quitApp } from '../main.js';
import { api } from '../api.js';
import { $, $$, icon, guard, confirmDialog } from '../ui.js';
import { esc } from '../format.js';
import securitySection from './security-settings.js';
import { peopleCard } from './people.js';

const KIND = { expense: 'Gasto', income: 'Ganho', transfer: 'Transferência' };

export default async function settings(app) {
  const s = await api('settings');
  const total = store.data.transactions.length;
  const protectedDb = Boolean(store.security?.protected);
  app.innerHTML = `
  <div id="security"></div>
  <div id="people"></div>
  <article class="card" style="margin-bottom:16px">
    <div class="card-head"><div><h2>Em que mês contar cada gasto</h2><p>Vale para Painel, Economizar, Orçamento, Lançamentos e Relatório.</p></div></div>
    <div class="grid cols-2">
      <label class="check-tile ${store.basis === 'purchase' ? 'ok' : ''}" style="cursor:pointer"><input type="radio" name="basis" value="purchase" ${store.basis === 'purchase' ? 'checked' : ''}>
        <span><b>Mês da compra</b> (recomendado)<br><small>Uma compra de 15/09 conta em setembro, mesmo vindo na fatura de outubro. Cada parcela conta no mês em que é cobrada. O mês atual fica parcial até a próxima fatura.</small></span></label>
      <label class="check-tile ${store.basis === 'invoice' ? 'ok' : ''}" style="cursor:pointer"><input type="radio" name="basis" value="invoice" ${store.basis === 'invoice' ? 'checked' : ''}>
        <span><b>Mês da fatura</b><br><small>Tudo da fatura que vence em outubro conta em outubro. Mostra quando o dinheiro saiu da conta.</small></span></label>
    </div>
  </article>
  <section class="grid cols-2">
    <article class="card">
      <div class="card-head"><div><h2>Backup e exportação</h2><p>Nada sai deste computador. Não há nuvem nem conexão com bancos.</p></div></div>
      <div class="list-row">${icon('lock', 'width="20" height="20"')}<div class="grow"><b>Banco de dados local</b><small>${protectedDb ? 'financas.cofre (criptografado)' : 'financas.sqlite3 (sem criptografia)'} · ${total} lançamentos · ${store.data.imports.length} importações</small></div></div>
      <div class="list-row">${icon('download', 'width="20" height="20"')}<div class="grow"><b>Exportar backup</b><small>${protectedDb ? 'Arquivo criptografado: abre com a mesma senha ou chave de recuperação.' : 'Atenção: sem proteção, o backup sai legível. Ative a senha acima para exportar criptografado.'}</small></div><a class="btn small" href="/api/backup">Baixar</a></div>
      <div class="list-row">${icon('file', 'width="20" height="20"')}<div class="grow"><b>Exportar lançamentos (CSV)</b><small>Para Excel ou Google Planilhas. O CSV sai sem criptografia: apague depois de usar.</small></div><button class="btn small" id="csv">Baixar CSV</button></div>
      <div class="list-row">${icon('x', 'width="20" height="20"')}<div class="grow"><b>Encerrar o app</b><small>Fecha o servidor local${protectedDb ? ' e bloqueia os dados' : ''}. Para voltar, abra o aplicativo de novo.</small></div><button class="btn small" id="quit-settings">Encerrar</button></div>
    </article>
    <article class="card">
      <div class="card-head"><div><h2>Contas próprias</h2><p>PIX entre contas de vocês viram transferência, sem contar como gasto ou ganho.</p></div></div>
      <form class="row" id="own-form"><input name="name" placeholder="Nome completo como aparece no PIX" style="flex:1" required><button class="btn primary small">Adicionar</button></form>
      <div class="mt">${s.own_accounts.map(n => `<div class="list-row"><div class="grow"><b>${esc(n)}</b></div><button class="btn small danger" data-own="${esc(n)}">Remover</button></div>`).join('') || '<p class="muted">Nenhuma conta própria cadastrada.</p>'}</div>
    </article>
  </section>
  <article class="card mt">
    <div class="card-head"><div><h2>Regras de categoria aprendidas</h2><p>Criadas quando você corrige uma categoria. Têm prioridade sobre as sugestões automáticas.</p></div><input id="rule-q" type="search" placeholder="Filtrar regras…"></div>
    <div id="rules"></div>
  </article>
  <p class="muted mt" style="font-size:12px;text-align:center">Meus Gastos ${esc(store.security?.version || '')} · software livre (AGPL-3.0) · <a href="https://github.com/ltmleo/meus-gastos/releases" target="_blank" rel="noopener noreferrer">novas versões</a></p>
  <article class="card mt">
    <div class="card-head"><div><h2>Titulares de cartão</h2><p>Associação lembrada entre o nome impresso na fatura e a pessoa.</p></div></div>
    ${Object.entries(s.holder_rules).map(([h, p]) => `<div class="list-row"><div class="grow"><b>${esc(h)}</b></div><span class="chip accent">${esc(p)}</span></div>`).join('') || '<p class="muted">Nenhum titular associado ainda.</p>'}
  </article>`;

  $$('input[name="basis"]', app).forEach(input => input.addEventListener('change', async () => {
    setBasis(input.value);
    store.month = '';
    await refresh();
  }));

  securitySection($('#security', app));
  $('#quit-settings', app).addEventListener('click', quitApp);
  peopleCard($('#people', app));

  const drawRules = (q = '') => {
    const list = s.category_rules.filter(r => !q || r.key.toLowerCase().includes(q.toLowerCase()) || r.category.toLowerCase().includes(q.toLowerCase()));
    $('#rules', app).innerHTML = list.length ? `<div class="table-wrap"><table><thead><tr><th>Estabelecimento</th><th>Tipo</th><th>Categoria</th><th></th></tr></thead><tbody>${list.map(r => {
      const [kind, merchant] = r.key.includes(':') ? r.key.split(/:(.*)/s) : ['expense', r.key];
      return `<tr><td>${esc(merchant)}</td><td>${KIND[kind] || esc(kind)}</td><td><span class="chip">${esc(r.category)}</span></td><td style="text-align:right"><button class="btn small" data-forget="${esc(r.key)}">Esquecer</button></td></tr>`;
    }).join('')}</tbody></table></div>` : '<p class="muted">Nenhuma regra.</p>';
    $$('[data-forget]', app).forEach(b => b.addEventListener('click', async () => {
      if (await guard(() => api('forget-rule', { key: b.dataset.forget }), 'Regra removida.')) {
        s.category_rules = s.category_rules.filter(r => r.key !== b.dataset.forget);
        drawRules($('#rule-q', app).value);
      }
    }));
  };
  drawRules();
  $('#rule-q', app).addEventListener('input', e => drawRules(e.target.value));

  $('#own-form', app).addEventListener('submit', async e => {
    e.preventDefault();
    const name = new FormData(e.target).get('name');
    if (!await confirmDialog('Cadastrar conta própria?', `PIX enviados ou recebidos de <b>${esc(name)}</b> (nome completo exato) passarão a ser transferências, inclusive os já importados.`, 'Cadastrar')) return;
    const result = await guard(() => api('own-account', { name }));
    if (result) { await refresh(); }
  });
  $$('[data-own]', app).forEach(b => b.addEventListener('click', async () => {
    if (await guard(() => api('own-account', { name: b.dataset.own, remove: true }), 'Conta removida. Lançamentos já ajustados não mudam.')) await refresh();
  }));
  $('#csv', app).addEventListener('click', () => {
    const header = ['data', 'mes_da_compra', 'mes_fatura_extrato', 'descricao', 'valor', 'tipo', 'categoria', 'responsavel', 'meio', 'banco', 'cartao', 'parcela'];
    // Spreadsheet formula injection: a description starting with = + - @ would run as a formula.
    const cell = v => { let t = String(v ?? ''); if (/^[=+\-@\t\r]/.test(t) && !/^-?\d+(,\d+)?$/.test(t)) t = "'" + t; return `"${t.replace(/"/g, '""')}"`; };
    const lines = store.data.transactions.map(r => [r.date, r.period, r.month, r.description, (r.cents / 100).toFixed(2).replace('.', ','), KIND[r.kind], r.category, r.person, r.payment_channel, r.bank, r.card, r.installment].map(cell).join(';'));
    const blob = new Blob(['﻿' + [header.join(';'), ...lines].join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'lancamentos.csv' });
    a.click();
    URL.revokeObjectURL(a.href);
  });
}
