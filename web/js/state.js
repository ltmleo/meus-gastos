import { options } from './ui.js';

// Color follows the person's position in the household (members, then the shared group).
export const PEOPLE_COLORS = new Proxy({}, { get: (_, name) => `var(--person-${Math.max(0, (store.data?.people || []).indexOf(name)) % 6 + 1})` });
export const GROUPS = { income: ['Salário', 'Rendimentos', 'Outras receitas'], transfer: ['Pagamento de cartão', 'Investimentos', 'Transferências'] };
export const KINDS = [['expense', 'Gasto'], ['income', 'Ganho'], ['transfer', 'Transferência']];
export const CHANNELS = [['credit', 'Crédito'], ['account', 'Conta'], ['unspecified', 'Não informado']];
export const BANKS = [['santander', 'Santander'], ['nubank', 'Nubank'], ['unspecified', 'Outro / não informado']];

const savedBasis = (() => { try { return localStorage.getItem('basis'); } catch { return null; } })();

export const store = {
  data: null,
  dash: null,
  month: '', person: '', channel: '',
  // 'purchase': month the money was spent (default). 'invoice': month of the invoice/statement.
  basis: savedBasis === 'invoice' ? 'invoice' : 'purchase',
  pending: 0,
  categoriesFor(kind) {
    const all = this.data?.categories || [];
    if (kind === 'income') return GROUPS.income;
    if (kind === 'transfer') return GROUPS.transfer;
    return all.filter(c => !GROUPS.income.includes(c) && !GROUPS.transfer.includes(c));
  },
};

/** Month a transaction counts in, following the chosen basis. */
export const monthOf = r => store.basis === 'invoice' ? r.month : (r.period || r.month);

export function setBasis(basis) {
  store.basis = basis === 'invoice' ? 'invoice' : 'purchase';
  try { localStorage.setItem('basis', store.basis); } catch { /* optional */ }
}

export function categoryOptions(kind, selected, placeholder) {
  const list = kind ? store.categoriesFor(kind) : store.data.categories;
  const extra = selected && !list.includes(selected) ? [[selected, selected + ' (revisar tipo)']] : [];
  return options([...list, ...extra], selected, placeholder);
}
