import { store, loadDashboard, monthOf, PEOPLE_COLORS, KINDS } from '../main.js';
import { draw, columns, sankey, strip, legend, tipRow } from '../charts.js';
import { $, icon, toast, options, modal } from '../ui.js';
import { apiFile } from '../api.js';
import { esc, money, money0, monthShort, monthLong, monthName, pct, prettyName, dateShort, dateBR, today } from '../format.js';
import { flowData } from './overview.js';

// Kept only in memory for this tab, so switching months does not ask again.
let pdfPassword = '';
const pdfProtectDefault = () => { try { return sessionStorage.getItem('pdfProtect') === '1'; } catch { return false; } };

const SEVERITY = { alert: 'Atenção', warning: 'Aumento', tip: 'Dica', info: 'Informação', good: 'Bom sinal' };
const CHANNEL = { credit: 'Cartão', account: 'Conta', unspecified: '—' };

export default async function report(app, params) {
  store.month = params.get('m') || store.month;
  store.person = params.get('p') ?? store.person;
  store.channel = params.get('c') ?? store.channel;
  if (params.get('b')) store.basis = params.get('b') === 'invoice' ? 'invoice' : 'purchase';
  app.innerHTML = '<div class="report"><div class="skeleton" style="min-height:600px"></div></div>';
  try { await loadDashboard(); } catch (error) { return toast(error.message, 'error'); }
  const d = store.dash, k = d.kpis;
  const rows = store.data.transactions.filter(r => monthOf(r) === d.month && (!store.person || r.person === store.person) && (!store.channel || r.payment_channel === store.channel));
  const expenses = rows.filter(r => r.kind === 'expense').sort((a, b) => a.date.localeCompare(b.date) || b.cents - a.cents);
  const income = rows.filter(r => r.kind === 'income').sort((a, b) => a.date.localeCompare(b.date));
  const transfers = rows.filter(r => r.kind === 'transfer').sort((a, b) => a.date.localeCompare(b.date));
  const scope = [store.person || 'Casal (todos)', store.channel ? CHANNEL[store.channel] : 'cartão e conta', store.basis === 'invoice' ? 'por mês da fatura' : 'por mês da compra'].join(' · ');
  const savingCards = d.insights.filter(i => i.saving);
  const otherCards = d.insights.filter(i => !i.saving);

  app.innerHTML = `
  <div class="report-toolbar no-print">
    <a class="btn small" href="/?m=${d.month}" data-link>${icon('left')}Voltar</a>
    <select id="r-month" aria-label="Mês">${options(store.months.map(m => [m, monthLong(m)]), d.month)}</select>
    <select id="r-person" aria-label="Pessoa">${options([['', 'Casal (todos)'], ...store.data.people.map(p => [p, p])], store.person)}</select>
    <span class="grow"></span>
    <button class="btn small" id="r-print">${icon('file')}Imprimir</button>
    <label class="pdf-lock" title="O PDF só abre com esta senha"><input type="checkbox" id="r-protect" ${pdfProtectDefault() ? 'checked' : ''}>${icon('lock', 'width="14" height="14"')} Senha no PDF</label>
    <input id="r-pass" type="password" placeholder="Senha do PDF" autocomplete="new-password" maxlength="128" value="${esc(pdfPassword)}" aria-label="Senha do PDF">
    <a class="btn small" id="r-pdf" href="#">${icon('download')}Baixar PDF</a>
    <button class="btn small primary" id="r-share" title="Enviar o PDF pelo WhatsApp ou outro app">${icon('share')}<span>Compartilhar</span></button>
  </div>
  <article class="report">
    <header class="r-cover">
      <div class="r-brand"><span class="brand-mark" aria-hidden="true"></span><span>meus gastos<small>finanças pessoais</small></span></div>
      <div><span class="r-eyebrow">Relatório mensal</span><h1>${esc(capitalize(monthLong(d.month)))}</h1>
        <p>${esc(scope)} · gerado em ${dateBR(today())} · ${rows.length} lançamentos</p></div>
    </header>

    <section class="r-kpis">
      ${kpi('Gastos do mês', money(k.expense), comparison(k, d.partial))}
      ${kpi('Ganhos', k.has_income ? money(k.income) : '—', k.has_income ? `${income.length} entradas` : 'extrato da conta não importado')}
      ${kpi('Resultado', k.result != null ? money(k.result) : '—', k.savings_rate != null ? (k.savings_rate >= 0 ? `guardou ${pct(k.savings_rate)} da renda` : 'gastou mais do que entrou') : 'precisa dos ganhos do mês', k.result != null && k.result < 0 ? 'bad' : k.result != null ? 'good' : '')}
      ${kpi('Economia possível', money0(d.potential_saving) + '/mês', `${money0(d.potential_saving * 12)} em 12 meses`, 'good')}
    </section>

    <section class="r-block">
      <h2>Resumo</h2>
      <div class="r-summary">${narrative(d, expenses).map(p => `<p>${p}</p>`).join('')}</div>
    </section>

    <section class="r-block r-avoid">
      <h2>${k.has_income ? 'Para onde foi a renda' : 'Para onde foram os gastos'}</h2>
      <div class="r-legend">${legend([{ label: 'Fixos', color: 'var(--s7)' }, { label: 'Essenciais', color: 'var(--s1)' }, { label: 'Estilo de vida', color: 'var(--s4)' }, ...(k.has_income ? [{ label: k.income >= k.expense ? 'Guardado' : 'Além da renda', color: k.income >= k.expense ? 'var(--income)' : 'var(--expense)' }] : [])])}</div>
      <div class="chart" data-r="sankey"></div>
    </section>

    <section class="r-block r-page">
      <h2>Gastos por categoria</h2>
      <p class="r-note">Comparação com a média de ${d.baseline_months.length ? (d.baseline_months.length === 1 ? 'mês anterior' : `${d.baseline_months.length} meses anteriores`) + ' (' + d.baseline_months.map(monthShort).join(', ') + ')' : '— (sem histórico)'}.</p>
      <table class="r-table">
        <thead><tr><th>Categoria</th><th class="money">Este mês</th><th class="money">% do mês</th><th class="money">Média</th><th class="money">Variação</th><th class="money">Lanç.</th></tr></thead>
        <tbody>${d.categories.filter(c => c.cents || c.avg).map(c => {
          const diff = c.avg ? (c.compare - c.avg) / c.avg * 100 : null;
          return `<tr><td><span class="r-bar" style="--w:${Math.max(0, c.share)}%"></span>${esc(c.category)}${c.fixed ? ' <small>fixo</small>' : ''}</td><td class="money">${money(c.cents)}</td><td class="money">${pct(c.share, 1)}</td><td class="money">${c.avg ? money(c.avg) : '—'}</td>
            <td class="money ${diff > 5 ? 'r-up' : diff < -5 ? 'r-down' : ''}">${diff == null || Math.abs(diff) < 1 ? '—' : `${diff > 0 ? '+' : '−'}${pct(Math.abs(diff))}`}</td><td class="money">${c.count}</td></tr>`;
        }).join('')}</tbody>
        <tfoot><tr><td>Total</td><td class="money">${money(k.expense)}</td><td class="money">100%</td><td class="money">${k.baseline != null ? money(k.baseline) : '—'}</td><td class="money">${k.baseline ? signed((k.expense - k.baseline) / k.baseline * 100) : '—'}</td><td class="money">${k.count}</td></tr></tfoot>
      </table>
    </section>

    <section class="r-block r-avoid">
      <h2>Ganhos e gastos nos últimos meses</h2>
      <div class="r-legend">${legend([{ label: 'Ganhos', color: 'var(--income)' }, { label: 'Gastos', color: 'var(--expense)' }])}</div>
      <div class="chart" data-r="cashflow"></div>
      <table class="r-table r-compact">
        <thead><tr><th>Mês</th>${d.cashflow.map(f => `<th class="money">${monthShort(f.month)}</th>`).join('')}</tr></thead>
        <tbody>
          <tr><td>Ganhos</td>${d.cashflow.map(f => `<td class="money">${f.has_income ? money0(f.income) : '—'}</td>`).join('')}</tr>
          <tr><td>Gastos</td>${d.cashflow.map(f => `<td class="money">${f.available ? money0(f.expense) : '—'}</td>`).join('')}</tr>
          <tr><td>Resultado</td>${d.cashflow.map(f => `<td class="money ${f.result < 0 ? 'r-up' : ''}">${f.result != null ? money0(f.result) : '—'}</td>`).join('')}</tr>
        </tbody>
      </table>
    </section>

    <section class="r-grid r-avoid">
      <div class="r-block">
        <h2>Quem gastou</h2>
        <div class="chart">${strip(600, Object.entries(k.people).filter(([, v]) => v > 0).map(([p, v]) => ({ label: p, value: v, color: PEOPLE_COLORS[p] })), { height: 12 })}</div>
        <table class="r-table">${Object.entries(k.people).filter(([, v]) => v).map(([p, v]) => `<tr><td><i class="dot" style="background:${PEOPLE_COLORS[p]}"></i> ${p}</td><td class="money">${money(v)}</td><td class="money">${pct(v / Math.max(1, k.expense) * 100)}</td></tr>`).join('')}</table>
      </div>
      <div class="r-block">
        <h2>Fixos, essenciais e estilo de vida</h2>
        <table class="r-table">
          <tr><td><i class="swatch" style="background:var(--s7)"></i> Fixos</td><td class="money">${money(k.fixed)}</td><td class="money">${pct(k.fixed / Math.max(1, k.expense) * 100)}</td></tr>
          <tr><td><i class="swatch" style="background:var(--s1)"></i> Outros essenciais</td><td class="money">${money(k.essential - k.fixed)}</td><td class="money">${pct((k.essential - k.fixed) / Math.max(1, k.expense) * 100)}</td></tr>
          <tr><td><i class="swatch" style="background:var(--s4)"></i> Estilo de vida</td><td class="money">${money(k.expense - k.essential)}</td><td class="money">${pct((k.expense - k.essential) / Math.max(1, k.expense) * 100)}</td></tr>
        </table>
        <p class="r-note">Estilo de vida é onde cortes têm efeito mais rápido.</p>
      </div>
    </section>

    <section class="r-grid r-avoid">
      <div class="r-block"><h2>Maiores gastos</h2><table class="r-table">${d.largest.map(r => `<tr><td>${dateShort(r.date)}</td><td>${esc(prettyName(r.description))}<small>${esc(r.category)}${r.installment ? ' · parcela ' + esc(r.installment) : ''}</small></td><td class="money">${money(r.cents)}</td></tr>`).join('')}</table></div>
      <div class="r-block"><h2>Onde mais compraram</h2><table class="r-table">${d.merchants.slice(0, 8).map(m => `<tr><td>${esc(prettyName(m.description))}<small>${m.count} ${m.count === 1 ? 'compra' : 'compras'} · ${esc(m.category)}</small></td><td class="money">${money(m.cents)}</td></tr>`).join('')}</table></div>
    </section>

    <section class="r-block r-page">
      <h2>Oportunidades de economia</h2>
      ${savingCards.length ? `<table class="r-table r-insights"><thead><tr><th>Ponto</th><th class="money">Potencial/mês</th></tr></thead><tbody>${savingCards.map(i => `<tr><td><span class="r-sev ${i.severity}">${SEVERITY[i.severity]}</span> <b>${esc(i.title)}</b><small>${esc(i.body)}</small></td><td class="money"><b>${money0(i.saving)}</b></td></tr>`).join('')}</tbody></table>
        <p class="r-note">O total de ${money0(d.potential_saving)}/mês conta cada categoria uma vez, mesmo quando ela aparece em mais de um item.</p>` : '<p>Nenhum ponto de economia identificado neste mês.</p>'}
      ${otherCards.length ? `<h3>Outras observações</h3><ul class="r-list">${otherCards.map(i => `<li><span class="r-sev ${i.severity}">${SEVERITY[i.severity]}</span> <b>${esc(i.title)}.</b> ${esc(i.body)}</li>`).join('')}</ul>` : ''}
    </section>

    ${d.budgets.length ? `<section class="r-block r-avoid"><h2>Orçamento</h2><table class="r-table"><thead><tr><th>Categoria</th><th class="money">Limite</th><th class="money">Gasto</th><th class="money">Uso</th><th>Situação</th></tr></thead><tbody>
      ${d.budgets.map(b => `<tr><td>${esc(b.category)}</td><td class="money">${money(b.limit)}</td><td class="money">${money(b.spent)}</td><td class="money">${pct(b.pct)}</td><td><span class="r-meter ${b.status}"><i style="width:${Math.min(100, b.pct)}%"></i></span> ${b.status === 'over' ? 'estourado' : b.status === 'near' ? 'perto do limite' : 'dentro'}</td></tr>`).join('')}</tbody></table></section>` : ''}

    <section class="r-grid r-avoid">
      <div class="r-block"><h2>Assinaturas e contas fixas</h2>${d.recurring.length ? `<table class="r-table">${d.recurring.map(r => `<tr><td>${esc(prettyName(r.description))}<small>${esc(r.category)} · ${r.months} meses${r.active ? '' : ' · sem cobrança recente'}</small></td><td class="money">${money(r.average)}<small>${money0(r.annual)}/ano</small></td></tr>`).join('')}</table>` : '<p class="r-note">Ainda sem meses suficientes para identificar recorrências.</p>'}</div>
      <div class="r-block"><h2>Parcelas a pagar</h2>${d.installments.active.length ? `<table class="r-table">${d.installments.active.map(a => `<tr><td>${esc(prettyName(a.description))}<small>parcela ${esc(a.installment)} · até ${monthShort(a.end_month)}</small></td><td class="money">${money(a.cents)}<small>faltam ${money(a.remaining_cents)}</small></td></tr>`).join('')}
        <tfoot><tr><td>Total a pagar</td><td class="money">${money(d.installments.total_remaining)}</td></tr></tfoot></table>` : '<p class="r-note">Nenhuma parcela futura.</p>'}</div>
    </section>

    <section class="r-block r-page">
      <h2>Lançamentos do mês</h2>
      ${txTable('Gastos', expenses)}
      ${income.length ? txTable('Ganhos', income, true) : ''}
      ${transfers.length ? txTable('Transferências (fora de gastos e ganhos)', transfers) : ''}
    </section>

    <footer class="r-footer">Meus Gastos · relatório gerado localmente, sem conexão com bancos. Valores por mês de referência da fatura/extrato. Insights são observações do histórico, não recomendações de investimento.</footer>
  </article>`;

  draw($('[data-r="sankey"]', app), w => sankey(w, flowData(d), { rowHeight: 22, minHeight: 300 }));
  draw($('[data-r="cashflow"]', app), w => columns(w, {
    labels: d.cashflow.map(f => monthShort(f.month)), height: 200, valueLabels: 'highlight',
    highlight: d.cashflow.findIndex(f => f.month === d.month),
    series: [
      { label: 'Ganhos', color: 'var(--income)', values: d.cashflow.map(f => f.has_income ? f.income : null) },
      { label: 'Gastos', color: 'var(--expense)', values: d.cashflow.map(f => f.available ? f.expense : null) },
    ],
    extraTip: i => d.cashflow[i].result != null ? tipRow('', 'Resultado', money(d.cashflow[i].result)) : '',
  }));

  const go = () => {
    const query = new URLSearchParams({ m: $('#r-month').value, ...($('#r-person').value ? { p: $('#r-person').value } : {}) });
    history.replaceState({}, '', '/relatorio?' + query);
    report(app, query);
  };
  $('#r-month').addEventListener('change', go);
  $('#r-person').addEventListener('change', go);
  $('#r-print').addEventListener('click', () => window.print());

  // The PDF is prepared in the background: browsers only open the share sheet
  // during the click itself, so the file must already exist by then.
  // With "Senha no PDF", the file is prepared again (debounced) for the typed password.
  const fileName = `relatorio-${d.month}${store.person ? '-' + store.person.toLowerCase() : ''}.pdf`;
  const cache = new Map();  // password -> Promise<File>
  let pdfFile = null;
  const protect = $('#r-protect'), passInput = $('#r-pass');
  const wanted = () => protect.checked ? passInput.value : '';
  const ready = () => !protect.checked || passInput.value.length >= 4;
  const getPdf = () => {
    const password = wanted();
    if (!cache.has(password)) {
      cache.set(password, apiFile('report.pdf', { ...pdfFilters(d.month), password })
        .then(blob => new File([blob], fileName, { type: 'application/pdf' }))
        .catch(error => { cache.delete(password); throw error; }));
    }
    return cache.get(password).then(file => { if (password === wanted()) pdfFile = file; return file; });
  };
  const prepare = () => { pdfFile = null; if (ready() && params.get('print') !== '1') getPdf().catch(() => {}); };
  let typing;
  const syncProtection = () => {
    passInput.hidden = !protect.checked;
    try { sessionStorage.setItem('pdfProtect', protect.checked ? '1' : ''); } catch { /* optional */ }
    pdfPassword = passInput.value;
    for (const id of ['#r-pdf', '#r-share']) {
      $(id).toggleAttribute('aria-disabled', !ready());
      $(id).title = ready() ? '' : 'Digite a senha do PDF (mínimo 4 caracteres)';
    }
    clearTimeout(typing);
    typing = setTimeout(prepare, 600);
  };
  protect.addEventListener('change', () => { syncProtection(); if (protect.checked) passInput.focus(); });
  passInput.addEventListener('input', syncProtection);
  passInput.hidden = !protect.checked;
  prepare();
  const download = file => {
    const url = URL.createObjectURL(file);
    Object.assign(document.createElement('a'), { href: url, download: file.name }).click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };
  const busy = (button, text) => { button.dataset.label = button.innerHTML; button.textContent = text; button.setAttribute('aria-disabled', 'true'); };
  const idle = button => { button.innerHTML = button.dataset.label; button.removeAttribute('aria-disabled'); };
  const needPassword = () => { toast('Digite a senha do PDF (mínimo 4 caracteres) ou desmarque “Senha no PDF”.', 'error'); passInput.focus(); };

  $('#r-share').addEventListener('click', async e => {
    const button = e.currentTarget;
    if (!ready()) return needPassword();
    const text = shareText(d, protect.checked);
    const canShareFiles = file => Boolean(navigator.canShare?.({ files: [file] }));
    if (!pdfFile) {
      busy(button, 'Preparando PDF…');
      try { await getPdf(); } catch (error) { idle(button); return toast(error.message, 'error'); }
      idle(button);
    }
    if (!canShareFiles(pdfFile)) return shareFallback(pdfFile, text, download);
    try {
      await navigator.share({ files: [pdfFile], title: `Relatório de ${monthLong(d.month)}`, text });
    } catch (error) {
      if (error.name === 'AbortError') return;  // user closed the share sheet
      if (error.name === 'NotAllowedError') {
        // The click "expired" while the PDF was being generated: one more click shares it.
        button.innerHTML = icon('share') + '<span>Compartilhar agora</span>';
        return toast('PDF pronto. Clique em “Compartilhar agora”.');
      }
      shareFallback(pdfFile, text, download);
    }
  });

  $('#r-pdf').addEventListener('click', async e => {
    e.preventDefault();
    if (!ready()) return needPassword();
    const button = e.currentTarget;
    busy(button, 'Gerando PDF…');
    try {
      download(await getPdf());
      toast(protect.checked ? 'PDF protegido com senha gerado.' : 'PDF gerado.');
    } catch (error) {
      toast(error.message + (protect.checked ? '' : ' Abrindo a impressão: escolha “Salvar como PDF”.'), 'error');
      if (!protect.checked) window.print();  // printing would drop the password
    } finally {
      idle(button);
    }
  });
}

/** Short message that goes along with the PDF (or alone, if the PDF cannot be attached). */
function shareText(d, locked = false) {
  // A protected PDF must not travel with its numbers in clear text beside it.
  if (locked) return `📊 Relatório de ${monthLong(d.month)}${store.person ? ' · ' + store.person : ''}
🔒 PDF protegido com senha (combine a senha fora desta conversa).`;
  const k = d.kpis;
  const ref = d.partial ? null : (k.baseline ?? k.previous);
  const lines = [`📊 Relatório de ${monthLong(d.month)}${d.partial ? ' (mês em andamento)' : ''}${store.person ? ' · ' + store.person : ''}`,
    `Gastos: ${money(k.expense)}${ref ? ` (${signed((k.expense - ref) / ref * 100)} vs. média)` : ''}`];
  if (k.has_income) lines.push(`Ganhos: ${money(k.income)}`, `Resultado: ${money(k.result)}`);
  const top = d.categories.filter(c => c.cents > 0).slice(0, 3);
  if (top.length) lines.push(`Maiores: ${top.map(c => `${c.category} ${money0(c.cents)}`).join(', ')}`);
  if (d.potential_saving && !d.partial) lines.push(`Economia possível: ${money0(d.potential_saving)}/mês`);
  return lines.join('\n');
}

/** Without file sharing: save the PDF and open WhatsApp with the summary ready to send. */
async function shareFallback(file, text, download) {
  download(file);
  const encoded = encodeURIComponent(text);
  await modal(`<div class="dialog-body">
    <div class="dialog-head"><h2>Enviar pelo WhatsApp</h2><button type="button" class="icon-btn" data-close aria-label="Fechar">${icon('x')}</button></div>
    <p>Este navegador não consegue anexar arquivos direto. O PDF <b>${esc(file.name)}</b> foi salvo em Downloads: abra a conversa e anexe-o (ou arraste o arquivo para a janela do WhatsApp).</p>
    <pre class="share-preview">${esc(text)}</pre>
    <div class="row">
      <a class="btn primary" href="whatsapp://send?text=${encoded}">${icon('chat')}Abrir WhatsApp</a>
      <a class="btn" href="https://web.whatsapp.com/send?text=${encoded}" target="_blank" rel="noopener noreferrer">WhatsApp Web</a>
      <button type="button" class="btn" id="copy-summary">${icon('copy')}Copiar resumo</button>
    </div>
    <small>A mensagem é preenchida no WhatsApp, mas só é enviada quando você escolher o contato e confirmar.</small>
  </div>`, { onOpen: dialog => {
    $('#copy-summary', dialog).addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(text); toast('Resumo copiado.'); } catch { toast('Não foi possível copiar.', 'error'); }
    });
  } });
}

function pdfFilters(month) {
  return { m: month, p: store.person || '', c: store.channel || '', b: store.basis === 'invoice' ? 'invoice' : '' };
}

const capitalize = s => s.charAt(0).toUpperCase() + s.slice(1);
const signed = v => `${v > 0 ? '+' : '−'}${pct(Math.abs(v))}`;

function kpi(label, value, sub, tone = '') {
  return `<div class="r-kpi ${tone}"><span>${esc(label)}</span><b>${value}</b><small>${sub}</small></div>`;
}

function comparison(k, partial = false) {
  const ref = partial ? null : (k.baseline ?? k.previous);
  if (!ref) return `${k.count} lançamentos${partial ? ' · mês em andamento' : ''}`;
  const diff = (k.expense - ref) / ref * 100;
  return `${signed(diff)} vs. ${k.baseline != null ? 'média recente' : 'mês anterior'} (${money0(ref)})`;
}

/** Plain-language summary built only from the numbers on the page. */
function narrative(d, expenses) {
  const k = d.kpis, m = monthName(d.month);
  const out = [];
  if (d.partial) out.push('<b>Mês em andamento:</b> as compras no cartão deste mês só chegam com a próxima fatura, então os números ainda estão incompletos.');
  const ref = d.partial ? null : (k.baseline ?? k.previous);
  let first = `Em ${m}, os gastos somaram <b>${money(k.expense)}</b> em ${k.count} lançamentos`;
  if (ref) {
    const diff = (k.expense - ref) / ref * 100;
    first += Math.abs(diff) < 3 ? ', praticamente igual à média recente' : `, <b>${pct(Math.abs(diff))} ${diff > 0 ? 'acima' : 'abaixo'}</b> da ${k.baseline != null ? 'média dos meses anteriores' : 'do mês anterior'} (${money(ref)})`;
  }
  out.push(first + (k.credits ? `. Estornos devolveram ${money(k.credits)}.` : '.'));
  if (k.has_income) {
    out.push(k.result >= 0
      ? `Entraram <b>${money(k.income)}</b> e sobraram <b>${money(k.result)}</b>, uma taxa de poupança de ${pct(k.savings_rate)}.`
      : `Entraram <b>${money(k.income)}</b>: os gastos passaram a renda em <b>${money(-k.result)}</b>.`);
  } else {
    out.push('O extrato da conta deste mês não foi importado, então ganhos e resultado não aparecem; os números de gastos refletem o que foi lido nas faturas.');
  }
  const top = d.categories.filter(c => c.cents > 0).slice(0, 3);
  if (top.length) out.push(`As maiores categorias foram ${top.map(c => `${esc(c.category)} (${money0(c.cents)}, ${pct(c.share)})`).join(', ')}. Juntas, representam ${pct(top.reduce((s, c) => s + c.share, 0))} do mês.`);
  const ups = d.partial ? [] : d.categories.filter(c => c.avg && c.compare - c.avg >= 15000 && (c.compare - c.avg) / c.avg >= 0.25 && c.category !== 'Outros').slice(0, 3);
  if (ups.length) out.push(`Ficaram acima do normal: ${ups.map(c => `${esc(c.category)} (+${money0(c.compare - c.avg)})`).join(', ')}.`);
  const people = Object.entries(k.people).filter(([, v]) => v > 0);
  if (people.length > 1) out.push(`Divisão: ${people.map(([p, v]) => `${p} ${money0(v)} (${pct(v / k.expense * 100)})`).join(', ')}.`);
  if (d.potential_saving && !d.partial) out.push(`Seguindo as sugestões deste relatório, a economia possível é de <b>${money0(d.potential_saving)} por mês</b>, ou ${money0(d.potential_saving * 12)} em um ano.`);
  if (d.installments.total_remaining) out.push(`Há ${money(d.installments.total_remaining)} em parcelas a pagar nos próximos meses, ${money(d.installments.next_month)} já no mês que vem.`);
  return out;
}

function txTable(title, list, income = false) {
  const total = list.reduce((s, r) => s + r.cents, 0);
  return `<h3>${esc(title)} · ${list.length} · ${money(income ? -total : total)}</h3>
  <table class="r-table r-tx"><thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th>Quem</th><th>Meio</th><th class="money">Valor</th></tr></thead><tbody>
  ${list.map(r => `<tr><td>${dateShort(r.date)}</td><td>${esc(prettyName(r.description))}${r.installment ? ` <small class="inline">${esc(r.installment)}</small>` : ''}</td><td>${esc(r.category)}</td><td>${esc(r.person)}</td><td>${CHANNEL[r.payment_channel] || '—'}</td><td class="money ${r.cents < 0 && !income ? 'r-down' : ''}">${money(income ? -r.cents : r.cents)}</td></tr>`).join('')}
  </tbody></table>`;
}
