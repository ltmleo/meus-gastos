import { icon } from '../ui.js';
import { esc, money, money0, pct } from '../format.js';
import { store } from '../main.js';

const ICONS = { alert: 'alert', warning: 'trend', tip: 'bulb', info: 'info', good: 'check' };
export const SEVERITY_LABEL = { alert: 'Atenção', warning: 'Aumento', tip: 'Dica', info: 'Informação', good: 'Bom sinal' };

export function actionHref(action = {}) {
  const params = new URLSearchParams();
  if (store.month) params.set('m', store.month);
  if (action.category) params.set('categoria', action.category);
  if (action.search) params.set('q', action.search);
  if (action.max_value) params.set('max', action.max_value);
  const path = { transactions: '/lancamentos', insights: '/economizar', import: '/importar', budget: '/orcamento' }[action.page];
  if (!path) return '';
  return path + '?' + params + (action.anchor ? '#' + action.anchor : '');
}

const ACTION_LABEL = { transactions: 'Ver lançamentos', insights: 'Detalhes', import: 'Importar extrato', budget: 'Ajustar orçamento' };

export function insightCard(card) {
  const href = actionHref(card.action);
  return `<article class="insight ${card.severity}">
    <div class="ico" title="${SEVERITY_LABEL[card.severity]}">${icon(ICONS[card.severity])}</div>
    <div><h3>${esc(card.title)}</h3><p>${esc(card.body)}</p>
      ${href ? `<div class="actions"><a class="btn small" href="${href}" data-link>${ACTION_LABEL[card.action.page] || 'Abrir'}</a></div>` : ''}</div>
    ${card.saving ? `<div class="saving">${money0(card.saving)}<small>por mês</small></div>` : '<div></div>'}
  </article>`;
}

/** Signed change vs a reference; for spending, up is bad. */
export function delta(current, reference, { upIsGood = false, label = '' } = {}) {
  if (reference == null || !reference) return '';
  const change = (current - reference) / Math.abs(reference) * 100;
  if (Math.abs(change) < 1) return `<span class="delta flat">≈ ${label}</span>`;
  const up = change > 0, good = up === upIsGood;
  return `<span class="delta ${up ? 'up' : 'down'}-${good ? 'good' : 'bad'}" title="${money(current - reference)}">${up ? '▲' : '▼'} ${pct(Math.abs(change))}</span>${label ? `<span>${esc(label)}</span>` : ''}`;
}

export function emptyCard(title, body, cta = '') {
  return `<div class="card empty-state">${icon('info')}<h2>${esc(title)}</h2><p>${body}</p>${cta}</div>`;
}
