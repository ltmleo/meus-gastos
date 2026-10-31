const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const brl0 = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const MONTHS_LONG = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

export const money = cents => brl.format((cents || 0) / 100);
export const money0 = cents => brl0.format(Math.round((cents || 0) / 100));
export function compact(cents) {
  const v = Math.abs(cents / 100), sign = cents < 0 ? '-' : '';
  if (v >= 1e6) return `${sign}${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`;
  if (v >= 1e3) return `${sign}${(v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: v >= 1e4 ? 0 : 1 })} mil`;
  return sign + Math.round(v).toLocaleString('pt-BR');
}
export const pct = (n, digits = 0) => n == null || !isFinite(n) ? '—' : `${n.toLocaleString('pt-BR', { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;
export const monthShort = m => m ? `${MONTHS[+m.slice(5) - 1]}/${m.slice(2, 4)}` : '';
export const monthLong = m => m ? `${MONTHS_LONG[+m.slice(5) - 1]} de ${m.slice(0, 4)}` : '';
export const monthName = m => m ? MONTHS_LONG[+m.slice(5) - 1] : '';
export const dateShort = d => d ? `${d.slice(8, 10)}/${d.slice(5, 7)}` : '';
export const dateBR = d => d ? d.split('-').reverse().join('/') : '';
export function monthOffset(m, offset) {
  const index = +m.slice(0, 4) * 12 + +m.slice(5) - 1 + offset;
  return `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, '0')}`;
}
export const today = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };

export function parseMoney(text) {
  let t = String(text).trim().replace(/R\$|\s/g, '');
  if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
  if (!/^-?\d+(\.\d{1,2})?$/.test(t)) return null;
  return Math.round(parseFloat(t) * 100);
}
export const centsInput = cents => ((cents || 0) / 100).toFixed(2).replace('.', ',');

const SMALL = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'em', 'a', 'o']);
const KEEP = /^(PIX|IOF|CDB|LTDA|S\.?A\.?|ME|EPP|BR|SP|MG|RJ|II|III)$/i;
/** Bank descriptions are SHOUTED; make them readable without losing the original. */
export function prettyName(text = '') {
  let t = String(text).replace(/^\s*\d{2}\/\d{2}(?:\/\d{2,4})?\s+/, '').replace(/\s{2,}/g, ' ').trim();
  if (t !== t.toUpperCase()) return t;
  return t.toLowerCase().split(' ').map((w, i) => {
    if (KEEP.test(w)) return w.toUpperCase();
    if (i > 0 && SMALL.has(w)) return w;
    return w.replace(/(^|[*\-./])(\p{L})/gu, (_, a, b) => a + b.toUpperCase());
  }).join(' ');
}

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
