import { store, render, loadDashboard } from '../main.js';
import { api, query } from '../api.js';
import { $, $$, icon, guard, options } from '../ui.js';
import { esc, money, money0, monthLong, pct, parseMoney, centsInput } from '../format.js';

export default async function budget(app, params) {
  const d = store.dash;
  const { budgets, suggested } = await api('budgets?' + query({ month: store.month, basis: store.basis === 'invoice' ? 'invoice' : '' }));
  const spentBy = Object.fromEntries(d.categories.map(c => [c.category, c]));
  let simulated = null;
  if (params.get('simulado')) {
    try { simulated = JSON.parse(sessionStorage.getItem('simulatedBudget') || 'null'); } catch { simulated = null; }
  }
  // Working copy edited on screen; saved in one go.
  const draft = { ...budgets };
  const expenseCategories = store.categoriesFor('expense').filter(c => c !== 'Outros');

  const draw = () => {
    const names = Object.keys(draft).sort((a, b) => (spentBy[b]?.cents || 0) - (spentBy[a]?.cents || 0));
    const totalLimit = names.reduce((s, n) => s + draft[n], 0);
    const totalSpent = names.reduce((s, n) => s + Math.max(0, spentBy[n]?.cents || 0), 0);
    const unbudgeted = d.categories.filter(c => !draft[c.category] && c.cents > 0 && c.category !== 'Outros');
    const changed = JSON.stringify(Object.entries(draft).sort()) !== JSON.stringify(Object.entries(budgets).sort());
    const status = (spent, limit) => spent > limit ? 'over' : spent >= limit * 0.85 ? 'near' : 'ok';
    app.innerHTML = `
    ${simulated ? `<div class="banner">${icon('info')}<div class="grow">Valores do simulador de cortes prontos para virar orçamento.</div><button class="btn small primary" id="apply-sim">Aplicar simulação</button><button class="ghost small" id="dismiss-sim">Ignorar</button></div>` : ''}
    ${!names.length ? `<div class="banner">${icon('target')}<div class="grow"><b>Comece pelo orçamento sugerido.</b> Usamos a média dos últimos 3 meses de cada categoria, com 5% a menos nas variáveis.</div><button class="btn small primary" id="use-suggested">Usar sugestão</button></div>` : ''}
    ${names.length ? `<section class="grid cols-3">
      <article class="card kpi"><span class="label">Orçado para ${esc(monthLong(d.month))}</span><span class="value">${money(totalLimit)}</span><span class="sub">${names.length} categorias com limite</span></article>
      <article class="card kpi"><span class="label">Gasto nessas categorias</span><span class="value">${money(totalSpent)}</span><span class="sub">${totalLimit ? pct(totalSpent / totalLimit * 100) + ' do orçado' : '—'}</span></article>
      <article class="card kpi"><span class="label">${totalLimit >= totalSpent ? 'Sobrou' : 'Passou'}</span><span class="value" style="color:${totalLimit >= totalSpent ? 'var(--good)' : 'var(--bad)'}">${money(Math.abs(totalLimit - totalSpent))}</span><span class="sub">${names.filter(n => (spentBy[n]?.cents || 0) > draft[n]).length} categorias acima do limite</span></article>
    </section>` : ''}
    <article class="card mt">
      <div class="card-head"><div><h2>Limites mensais por categoria</h2><p>O limite vale para todos os meses. Barra = gasto em ${esc(monthLong(d.month))}; o traço marca a média recente.</p></div>
        <div class="row"><button class="btn small" id="use-suggested-2">Recalcular sugestão</button><button class="btn small primary" id="save" ${changed ? '' : 'disabled'}>Salvar orçamento</button></div></div>
      ${names.map(name => {
        const c = spentBy[name] || { cents: 0, avg: 0 };
        const limit = draft[name], spent = Math.max(0, c.cents), max = Math.max(limit, spent, c.avg) || 1;
        return `<div class="budget-row">
          <div><b style="font-weight:600">${esc(name)}</b><br><small>${c.avg ? 'média ' + money0(c.avg) : 'sem histórico'}</small></div>
          <div><div class="meter ${status(spent, limit)}"><i style="width:${Math.min(100, spent / max * 100)}%"></i>${c.avg ? `<b style="left:${c.avg / max * 100}%"></b>` : ''}</div>
            <small class="${spent > limit ? '' : 'muted'}" style="${spent > limit ? 'color:var(--bad);font-weight:600' : ''}">${spent > limit ? `${money(spent - limit)} acima` : `${money(limit - spent)} disponível`} · ${pct(spent / limit * 100)}</small></div>
          <div class="nums row" style="justify-content:flex-end"><span>${money(spent)} de</span><input data-limit="${esc(name)}" value="${centsInput(limit)}" inputmode="decimal" aria-label="Limite de ${esc(name)}"><button class="icon-btn" data-remove="${esc(name)}" title="Remover limite" aria-label="Remover limite de ${esc(name)}">${icon('x')}</button></div>
        </div>`;
      }).join('') || '<p class="muted">Nenhum limite definido ainda.</p>'}
      <div class="row mt"><select id="add-category">${options(expenseCategories.filter(c => !draft[c]), '', 'Adicionar categoria…')}</select></div>
    </article>
    ${unbudgeted.length ? `<article class="card mt"><div class="card-head"><div><h2>Gastos sem limite</h2><p>Categorias com gastos neste mês que ainda não têm orçamento</p></div></div>
      ${unbudgeted.map(c => `<div class="list-row"><div class="grow"><b>${esc(c.category)}</b><small>${c.avg ? 'média ' + money0(c.avg) : ''}</small></div><div class="end">${money(c.cents)}</div><button class="btn small" data-add="${esc(c.category)}">${icon('plus')}Limitar</button></div>`).join('')}</article>` : ''}`;

    $$('[data-limit]', app).forEach(input => input.addEventListener('change', () => {
      const cents = parseMoney(input.value);
      if (cents && cents > 0) draft[input.dataset.limit] = cents;
      draw();
    }));
    $$('[data-remove]', app).forEach(b => b.addEventListener('click', () => { delete draft[b.dataset.remove]; draw(); }));
    $$('[data-add]', app).forEach(b => b.addEventListener('click', () => { draft[b.dataset.add] = suggested[b.dataset.add] || Math.max(1000, Math.round((spentBy[b.dataset.add]?.avg || spentBy[b.dataset.add]?.cents || 10000) / 1000) * 1000); draw(); }));
    $('#add-category')?.addEventListener('change', e => { const c = e.target.value; if (c) { draft[c] = suggested[c] || 50000; draw(); } });
    const useSuggested = () => { Object.keys(draft).forEach(k => delete draft[k]); Object.assign(draft, suggested); draw(); };
    $('#use-suggested')?.addEventListener('click', useSuggested);
    $('#use-suggested-2')?.addEventListener('click', useSuggested);
    $('#apply-sim')?.addEventListener('click', () => { Object.assign(draft, Object.fromEntries(Object.entries(simulated).filter(([, v]) => v > 0))); simulated = null; draw(); });
    $('#dismiss-sim')?.addEventListener('click', () => { simulated = null; draw(); });
    $('#save')?.addEventListener('click', async () => {
      const ok = await guard(() => api('budgets', { budgets: draft, replace: true }), 'Orçamento salvo.');
      if (ok) { try { sessionStorage.removeItem('simulatedBudget'); } catch { /* optional */ } await render(); }
    });
  };
  draw();
}
