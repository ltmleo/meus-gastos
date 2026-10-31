import { store, PEOPLE_COLORS, navigate } from '../main.js';
import { draw, columns, line, sparkline, strip, calendar, legend, tipAttr, tipRow, sankey } from '../charts.js';
import { icon, $, $$ } from '../ui.js';
import { esc, money, money0, monthShort, monthLong, monthName, pct, prettyName, dateShort } from '../format.js';
import { insightCard, delta, actionHref } from './common.js';

export default function overview(app) {
  const d = store.dash;
  if (!d) return;
  const k = d.kpis;
  const flow = d.cashflow;
  const currentIndex = flow.findIndex(f => f.month === d.month);
  const reference = d.partial ? null : (k.baseline ?? k.previous);
  const actionable = d.insights.filter(i => i.severity !== 'good' && i.severity !== 'info').slice(0, 4);
  const shown = actionable.length ? actionable : d.insights.slice(0, 3);
  const people = Object.entries(k.people).filter(([, v]) => v);

  app.innerHTML = `
  ${d.partial ? `<div class="banner">${icon('calendar')}<div class="grow"><b>${esc(monthLong(d.month))} ainda está em andamento.</b> As compras no cartão deste mês chegam com a próxima fatura; comparações ficam desativadas até lá.</div><a class="btn small" href="/?m=${d.default_month}" data-link>Ver ${esc(monthLong(d.default_month))}</a></div>` : ''}
  <section class="grid cols-4">
    <article class="card kpi hero">
      <span class="label">Gastos do mês</span>
      <span class="value">${money(k.expense)}</span>
      <span class="sub">${delta(k.expense, reference, { label: k.baseline != null ? 'vs. média recente' : 'vs. mês anterior' }) || `${k.count} lançamentos`}</span>
      <div class="spark" data-spark></div>
    </article>
    <article class="card kpi">
      <span class="label"><i class="swatch" style="background:var(--income)"></i>Ganhos</span>
      ${k.has_income ? `<span class="value">${money(k.income)}</span><span class="sub">Entradas registradas no extrato</span>`
        : `<span class="value muted">—</span><span class="sub">Extrato deste mês não importado. <a href="/importar" data-link>Importar</a></span>`}
    </article>
    <article class="card kpi">
      <span class="label">Resultado do mês</span>
      ${k.result != null ? `<span class="value" style="color:${k.result < 0 ? 'var(--bad)' : 'var(--good)'}">${money(k.result)}</span>
        <span class="sub">${k.savings_rate >= 0 ? `Você guardou <b>${pct(k.savings_rate)}</b> do que entrou` : 'Gastou mais do que entrou'}</span>`
        : `<span class="value muted">—</span><span class="sub">Precisa dos ganhos do mês para calcular</span>`}
    </article>
    <a class="card kpi" href="/economizar?m=${d.month}" data-link style="text-decoration:none;color:inherit">
      <span class="label">${icon('piggy', 'width="15" height="15"')} Economia possível</span>
      ${d.partial ? '<span class="value muted">—</span><span class="sub">Calculada quando o mês fechar →</span>' : `<span class="value" style="color:var(--good)">${money0(d.potential_saving)}<small style="font-size:14px;font-weight:500"> /mês</small></span>
      <span class="sub">${money0(d.potential_saving * 12)} por ano seguindo ${d.insights.filter(i => i.saving).length} sugestões →</span>`}
    </a>
  </section>

  <section class="grid cols-main mt">
    <article class="card">
      <div class="card-head"><div><h2>Ganhos e gastos</h2><p>Últimos ${flow.length} meses · clique em um mês para abri-lo</p></div>
        ${legend([{ label: 'Ganhos', color: 'var(--income)' }, { label: 'Gastos', color: 'var(--expense)' }])}</div>
      <div class="chart" data-chart="cashflow"></div>
      ${flow.some(f => !f.has_income) ? '<p style="font-size:12px;margin-top:8px" class="muted">Contorno tracejado: mês sem extrato da conta importado.</p>' : ''}
    </article>
    <article class="card">
      <div class="card-head"><div><h2>O que merece atenção</h2><p>${d.insights.length} observações sobre ${esc(monthName(d.month))}</p></div>
        <a class="btn small" href="/economizar?m=${d.month}" data-link>Ver tudo</a></div>
      <div class="insights">${shown.map(insightCard).join('') || '<p class="muted">Nada fora do normal neste mês.</p>'}</div>
    </article>
  </section>

  <article class="card mt">
    <div class="card-head"><div><h2>${k.has_income ? 'Para onde foi a renda' : 'Para onde foram os gastos'}</h2>
      <p>${k.has_income ? 'Cada faixa é dinheiro: da renda para fixos, essenciais e estilo de vida, até cada categoria' : 'Sem extrato da conta neste mês: o fluxo começa nos gastos. Importe o extrato para ver a renda.'} · clique numa categoria para ver os lançamentos</p></div>
      ${legend([{ label: 'Fixos', color: 'var(--s7)' }, { label: 'Essenciais', color: 'var(--s1)' }, { label: 'Estilo de vida', color: 'var(--s4)' }, ...(k.has_income ? [{ label: k.income >= k.expense ? 'Guardado' : 'Além da renda', color: k.income >= k.expense ? 'var(--income)' : 'var(--expense)' }] : [])])}</div>
    <div class="chart-scroll"><div class="chart" data-chart="sankey"></div></div>
  </article>

  <section class="grid cols-main mt">
    <article class="card">
      <div class="card-head"><div><h2>Para onde foi o dinheiro</h2><p>Gasto por categoria${d.baseline_months.length ? ` · o traço marca a média de ${d.baseline_months.length === 1 ? 'mês anterior' : d.baseline_months.length + ' meses anteriores'}` : ''}</p></div>
        ${d.baseline_months.length ? legend([{ label: 'Este mês', color: 'var(--bar)' }, { label: 'Média', tick: true }]) : ''}</div>
      <div class="cat-list">${categoryRows(d)}</div>
    </article>
    <div class="stack">
      <article class="card">
        <div class="card-head"><div><h2>Quem gastou</h2><p>Divisão das despesas do mês</p></div></div>
        <div class="chart" data-chart="people-strip"></div>
        <div class="mt">${people.map(([p, v]) => `<div class="list-row"><i class="dot" style="background:${PEOPLE_COLORS[p]}"></i><div class="grow"><b>${p}</b></div><div class="end">${money(v)}<small>${pct(v / Math.max(1, k.expense) * 100)}</small></div></div>`).join('') || '<p class="muted">Sem despesas.</p>'}</div>
      </article>
      <article class="card">
        <div class="card-head"><div><h2>Fixos e essenciais</h2><p>Quanto do mês é difícil de cortar</p></div></div>
        ${fixedBlock(k)}
      </article>
    </div>
  </section>

  <section class="grid cols-main mt">
    <article class="card">
      <div class="card-head"><div><h2>Tendência das maiores categorias</h2><p>Últimos meses, cada uma na sua escala</p></div></div>
      <div class="multiples">${d.category_trend.series.map((s, i) => `<div class="multiple"><h4>${esc(s.category)}<small>${money0(s.values[s.values.length - 1] || 0)}</small></h4><div class="chart" data-multiple="${i}"></div></div>`).join('')}</div>
    </article>
    <article class="card">
      <div class="card-head"><div><h2>Maiores gastos</h2><p>As compras mais caras do mês</p></div></div>
      ${d.largest.map(r => `<div class="list-row"><div class="grow"><b title="${esc(r.description)}">${esc(prettyName(r.description))}</b><small>${dateShort(r.date)} · ${esc(r.category)} · ${esc(r.person)}${r.installment ? ' · parcela ' + esc(r.installment) : ''}</small></div><div class="end">${money(r.cents)}</div></div>`).join('')}
    </article>
  </section>

  <section class="grid cols-main mt">
    <article class="card">
      <div class="card-head"><div><h2>Ritmo de gastos</h2><p>Por data da compra, últimos meses · mais escuro = dia mais caro</p></div></div>
      <div class="chart" data-chart="calendar"></div>
      <div class="chart mt" data-chart="weekday"></div>
    </article>
    <article class="card">
      <div class="card-head"><div><h2>Onde mais compraram</h2><p>Estabelecimentos do mês</p></div></div>
      ${d.merchants.slice(0, 8).map(m => `<a class="list-row" style="text-decoration:none;color:inherit" href="/lancamentos?m=${d.month}&q=${encodeURIComponent(m.description)}" data-link><div class="grow"><b>${esc(prettyName(m.description))}</b><small>${m.count} ${m.count === 1 ? 'compra' : 'compras'} · ${esc(m.category)}</small></div><div class="end">${money(m.cents)}</div></a>`).join('')}
    </article>
  </section>`;

  draw($('[data-spark]', app), w => sparkline(w, flow.map(f => f.available ? f.expense : null), { color: '#fff' }));
  draw($('[data-chart="cashflow"]', app), w => columns(w, {
    labels: flow.map(f => monthShort(f.month)), highlight: currentIndex, valueLabels: 'highlight',
    series: [
      { label: 'Ganhos', color: 'var(--income)', values: flow.map(f => f.has_income ? f.income : null) },
      { label: 'Gastos', color: 'var(--expense)', values: flow.map(f => f.available ? f.expense : null) },
    ],
    extraTip: i => flow[i].result != null ? tipRow('', 'Resultado', money(flow[i].result)) : '',
    onClick: true,
  }));
  $$('[data-chart="cashflow"]', app).forEach(el => el.addEventListener('click', e => {
    const g = e.target.closest('[data-click]');
    if (g) { store.month = flow[+g.dataset.click].month; navigate('/', { m: store.month, ...(store.person ? { p: store.person } : {}) }); }
  }));
  draw($('[data-chart="sankey"]', app), w => sankey(w, flowData(d)));
  $('[data-chart="sankey"]', app).addEventListener('click', e => {
    const target = e.target.closest('[data-href]');
    if (target) { history.pushState({}, '', target.dataset.href); window.dispatchEvent(new PopStateEvent('popstate')); window.scrollTo({ top: 0 }); }
  });
  draw($('[data-chart="people-strip"]', app), w => strip(w, people.map(([p, v]) => ({ label: p, value: v, color: PEOPLE_COLORS[p] }))));
  d.category_trend.series.forEach((s, i) => draw($(`[data-multiple="${i}"]`, app), w => line(w, {
    values: s.values, labels: d.category_trend.months.map(monthShort), title: s.category, height: 70, color: 'var(--bar)',
  })));
  draw($('[data-chart="calendar"]', app), w => calendar(w, d.daily));
  draw($('[data-chart="weekday"]', app), w => columns(w, {
    labels: d.weekday.map(x => x.day), height: 150, valueLabels: 'none',
    series: [{ label: 'Gasto no dia da semana', color: 'var(--bar)', values: d.weekday.map(x => x.cents) }],
    extraTip: i => tipRow('', 'Compras', d.weekday[i].count),
  }));
}

function categoryRows(d) {
  const expenses = d.categories.filter(c => c.cents > 0 || c.avg > 0);
  const max = Math.max(1, ...expenses.map(c => Math.max(c.cents, c.avg)));
  return expenses.slice(0, 12).map(c => {
    const diff = c.avg ? (c.compare - c.avg) / c.avg * 100 : null;
    const tip = `<div class="tt-title">${esc(c.category)}</div>${tipRow('var(--bar)', 'Este mês', money(c.cents))}${c.avg ? tipRow('', 'Média', money(c.avg)) : ''}${tipRow('', 'Lançamentos', c.count)}`;
    return `<a class="cat-row" href="${actionHref({ page: 'transactions', category: c.category })}" data-link ${tipAttr(tip)} style="text-decoration:none;color:inherit">
      <span class="name">${esc(c.category)}<small>${pct(c.share)} do mês</small></span>
      <span class="meter"><i style="width:${Math.max(0, c.cents) / max * 100}%"></i>${c.avg ? `<b style="left:${c.avg / max * 100}%"></b>` : ''}</span>
      <span class="amount">${money(c.cents)}</span>
      <span class="vs">${diff == null || Math.abs(diff) < 1 ? '' : `<span class="delta ${diff > 0 ? 'up-bad' : 'down-good'}">${diff > 0 ? '▲' : '▼'} ${pct(Math.abs(diff))}</span>`}</span>
    </a>`;
  }).join('') || '<p class="muted">Sem gastos neste mês.</p>';
}

function fixedBlock(k) {
  const variable = Math.max(0, k.expense - k.essential);
  const parts = [
    { label: 'Fixos (moradia, financiamentos, seguros, educação, assinaturas)', short: 'Fixos', value: k.fixed, color: 'var(--s7)' },
    { label: 'Outros essenciais (mercado, saúde, transporte, taxas)', short: 'Essenciais', value: Math.max(0, k.essential - k.fixed), color: 'var(--s1)' },
    { label: 'Estilo de vida (o que dá para ajustar)', short: 'Ajustáveis', value: variable, color: 'var(--s4)' },
  ];
  // Drawn at a fixed width; the strip has no text, so scaling it is harmless.
  return `<div class="chart">${strip(600, parts.map(p => ({ label: p.short, value: p.value, color: p.color })), { height: 12 })}</div>` +
    parts.map(p => `<div class="list-row"><i class="swatch" style="background:${p.color}"></i><div class="grow"><b>${p.short}</b><small>${esc(p.label)}</small></div><div class="end">${money(p.value)}<small>${pct(p.value / Math.max(1, k.expense) * 100)}</small></div></div>`).join('');
}

/** Income -> groups -> categories. Small categories fold into one node per group so labels stay readable. */
export function flowData(d) {
  const k = d.kpis;
  const spending = d.categories.filter(c => c.cents > 0);
  const spent = spending.reduce((s, c) => s + c.cents, 0);
  const groupDefs = [
    { label: 'Fixos', color: 'var(--s7)', test: c => c.fixed },
    { label: 'Essenciais', color: 'var(--s1)', test: c => c.essential && !c.fixed },
    { label: 'Estilo de vida', color: 'var(--s4)', test: c => !c.essential },
  ];
  const groups = groupDefs.map(g => {
    const items = spending.filter(g.test).sort((a, b) => b.cents - a.cents);
    const big = items.filter(c => c.cents >= spent * 0.015), small = items.filter(c => c.cents < spent * 0.015);
    const children = big.map(c => ({ label: c.category, value: c.cents, href: actionHref({ page: 'transactions', category: c.category }) }));
    if (small.length) children.push({ label: small.length === 1 ? small[0].category : `Outras (${small.length})`, value: small.reduce((s, c) => s + c.cents, 0), href: small.length === 1 ? actionHref({ page: 'transactions', category: small[0].category }) : '' });
    return { label: g.label, color: g.color, value: items.reduce((s, c) => s + c.cents, 0), children };
  }).filter(g => g.value > 0);
  if (!k.has_income) return { center: { label: 'Gastos do mês' }, groups };
  // Tiny sources (e.g. R$ 1 of yield) would only crowd the labels: fold them together.
  const incomeTotal = d.income_sources.reduce((t, i) => t + i.cents, 0);
  const sources = [];
  d.income_sources.forEach(i => {
    if (i.cents >= incomeTotal * 0.02 || !sources.length) return sources.push({ label: i.category, value: i.cents, color: 'var(--income)' });
    const other = sources.find(x => x.label === 'Outras receitas' || x.label === 'Outras fontes') || sources[sources.length - 1];
    other.value += i.cents;
    if (other.label !== 'Outras receitas') other.label = 'Outras fontes';
  });
  const income = sources.reduce((s, x) => s + x.value, 0);
  if (income >= spent) groups.push({ label: 'Guardado', color: 'var(--income)', value: income - spent, children: [] });
  else sources.push({ label: 'Além da renda', value: spent - income, color: 'var(--expense)' });
  return { sources, center: { label: income >= spent ? 'Renda' : 'Gastos do mês' }, groups };
}
