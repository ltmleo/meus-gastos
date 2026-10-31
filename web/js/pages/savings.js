import { store } from '../main.js';
import { draw, columns, sparkline, tipRow } from '../charts.js';
import { $, $$, segmented } from '../ui.js';
import { esc, money, money0, monthShort, monthLong, pct, prettyName } from '../format.js';
import { insightCard, SEVERITY_LABEL } from './common.js';

// Suggested starting cut per category: lifestyle spending flexes more than essentials.
const DEFAULT_CUT = { 'Alimentação': 25, 'Lazer': 25, 'Compras': 30, 'Vestuário': 30, 'Beleza e cuidados': 15, 'Viagens': 20, 'Casa e decoração': 30, 'Transporte': 10, 'Mercado': 10, 'Assinaturas': 30, 'Taxas e encargos': 80, 'Pets': 5, 'Saúde': 0, 'Educação': 0 };
let filter = 'all';

export default function savings(app) {
  const d = store.dash;
  if (!d) return;
  const cuttable = d.categories.filter(c => !c.fixed && c.category !== 'Outros' && Math.max(c.cents, c.avg) >= 5000)
    .map(c => ({ ...c, base: c.avg ? Math.round((c.cents + c.avg * 2) / 3) : c.cents, cut: DEFAULT_CUT[c.category] ?? 10 }))
    .sort((a, b) => b.base - a.base).slice(0, 10);
  const counts = d.insights.reduce((acc, c) => ({ ...acc, [c.severity]: (acc[c.severity] || 0) + 1 }), {});
  const recurring = d.recurring.filter(r => r.active);
  const inst = d.installments;

  app.innerHTML = `
  <section class="grid cols-3">
    <article class="card kpi hero">
      <span class="label">Economia possível identificada</span>
      <span class="big-number">${money0(d.potential_saving)}<small style="font-size:16px;font-weight:500"> /mês</small></span>
      <span class="sub">${money0(d.potential_saving * 12)} em um ano, somando as sugestões de ${esc(monthLong(d.month))}</span>
    </article>
    <article class="card kpi">
      <span class="label">Cobranças recorrentes ativas</span>
      <span class="value">${money(recurring.reduce((s, r) => s + r.average, 0))}<small style="font-size:13px;font-weight:500"> /mês</small></span>
      <span class="sub">${recurring.length} cobranças · ${money0(recurring.reduce((s, r) => s + r.annual, 0))} por ano</span>
    </article>
    <article class="card kpi">
      <span class="label">Parcelas a pagar</span>
      <span class="value">${money(inst.total_remaining)}</span>
      <span class="sub">${money(inst.next_month)} já no próximo mês · ${inst.active.length} compras</span>
    </article>
  </section>

  <section class="grid cols-main mt">
    <div class="stack">
      <article class="card">
        <div class="card-head"><div><h2>Sugestões e alertas</h2><p>Ordenados por urgência e pelo quanto você economiza</p></div></div>
        <div class="insight-filter">${segmented('insights', [['all', `Todos (${d.insights.length})`], ...['alert', 'warning', 'tip', 'info', 'good'].filter(s => counts[s]).map(s => [s, `${SEVERITY_LABEL[s]} (${counts[s]})`])], filter)}</div>
        <div class="insights" id="insight-list"></div>
      </article>
    </div>
    <article class="card" id="simulator">
      <div class="card-head"><div><h2>Simulador de cortes</h2><p>Arraste para ver quanto sobra se reduzir cada categoria. Base: média recente.</p></div></div>
      <div class="spread" style="margin-bottom:10px"><div><small>Economia simulada</small><div class="big-number" style="font-size:32px;color:var(--good)" id="sim-month"></div></div><div style="text-align:right"><small>Em 12 meses</small><div style="font-size:20px;font-weight:650" id="sim-year"></div></div></div>
      ${cuttable.map((c, i) => `<div class="sim-row"><span><b style="font-weight:580">${esc(c.category)}</b><br><small>${money0(c.base)}/mês</small></span>
        <input type="range" min="0" max="60" step="5" value="${c.cut}" data-sim="${i}" aria-label="Corte em ${esc(c.category)}">
        <span class="pct" data-sim-pct="${i}"></span><span class="save" data-sim-save="${i}"></span></div>`).join('') || '<p class="muted">Sem categorias variáveis suficientes.</p>'}
      <div class="row mt"><button class="btn small" id="sim-reset">Sugestão inicial</button><button class="btn small" id="sim-zero">Zerar</button><a class="btn small primary" id="sim-budget" href="/orcamento?m=${d.month}&simulado=1" data-link>Transformar em orçamento →</a></div>
    </article>
  </section>

  <section class="grid cols-2 mt">
    <article class="card" id="recurring">
      <div class="card-head"><div><h2>Assinaturas e contas fixas</h2><p>Cobranças que se repetem com valor parecido. Cancele o que não usa.</p></div></div>
      ${d.recurring.length ? d.recurring.map((r, i) => `<div class="list-row"><div class="grow"><b>${esc(prettyName(r.description))}</b>
        <small>${esc(r.category)} · ${r.months} meses${r.active ? '' : ' · sem cobrança recente'}${r.change_pct && Math.abs(r.change_pct) >= 5 ? ` · <span class="chip ${r.change > 0 ? 'bad' : 'good'}">${r.change > 0 ? '▲' : '▼'} ${pct(Math.abs(r.change_pct))}</span>` : ''}</small></div>
        <div style="width:80px" data-rec="${i}"></div>
        <div class="end">${money(r.average)}<small>${money0(r.annual)}/ano</small></div></div>`).join('') : '<p class="muted">Ainda não há meses suficientes para identificar recorrências (são necessários 3).</p>'}
    </article>
    <article class="card" id="installments">
      <div class="card-head"><div><h2>Parcelas comprometidas</h2><p>Quanto as compras parceladas já tomam dos próximos meses</p></div></div>
      ${inst.projection.length ? '<div class="chart" data-chart="projection"></div>' : '<p class="muted">Nenhuma parcela futura identificada neste mês.</p>'}
      ${inst.active.slice(0, 8).map(a => `<div class="list-row"><div class="grow"><b>${esc(prettyName(a.description))}</b><small>Parcela ${esc(a.installment)} · termina em ${monthShort(a.end_month)} · ${esc(a.person)}</small></div><div class="end">${money(a.cents)}<small>faltam ${money(a.remaining_cents)}</small></div></div>`).join('')}
    </article>
  </section>`;

  const renderInsights = () => {
    $('#insight-list').innerHTML = d.insights.filter(c => filter === 'all' || c.severity === filter).map(insightCard).join('') || '<p class="muted">Nenhum item.</p>';
  };
  renderInsights();
  $$('[data-seg="insights"] button', app).forEach(b => b.addEventListener('click', () => {
    filter = b.dataset.value;
    $$('[data-seg="insights"] button', app).forEach(x => x.classList.toggle('on', x === b));
    renderInsights();
  }));

  const updateSim = () => {
    let total = 0;
    cuttable.forEach((c, i) => {
      const save = Math.round(c.base * c.cut / 100);
      total += save;
      $(`[data-sim-pct="${i}"]`).textContent = `-${c.cut}%`;
      $(`[data-sim-save="${i}"]`).textContent = money0(save);
    });
    $('#sim-month').textContent = money0(total);
    $('#sim-year').textContent = money0(total * 12);
  };
  $$('[data-sim]', app).forEach(input => input.addEventListener('input', () => { cuttable[input.dataset.sim].cut = +input.value; updateSim(); }));
  const setAll = fn => { cuttable.forEach((c, i) => { c.cut = fn(c); $(`[data-sim="${i}"]`).value = c.cut; }); updateSim(); };
  $('#sim-reset')?.addEventListener('click', () => setAll(c => DEFAULT_CUT[c.category] ?? 10));
  $('#sim-zero')?.addEventListener('click', () => setAll(() => 0));
  if (cuttable.length) updateSim();
  $('#sim-budget')?.addEventListener('click', () => {
    const values = Object.fromEntries(cuttable.map(c => [c.category, Math.round(c.base * (1 - c.cut / 100) / 1000) * 1000]));
    try { sessionStorage.setItem('simulatedBudget', JSON.stringify(values)); } catch { /* optional */ }
  }, true);

  d.recurring.forEach((r, i) => draw($(`[data-rec="${i}"]`, app), w => sparkline(w, r.history.map(h => h.cents), { height: 26, color: 'var(--bar)' })));
  draw($('[data-chart="projection"]', app), w => columns(w, {
    labels: inst.projection.map(p => monthShort(p.month)), height: 190, valueLabels: 'all',
    series: [{ label: 'Parcelas', color: 'var(--s7)', values: inst.projection.map(p => p.cents) }],
  }));
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' });
}
