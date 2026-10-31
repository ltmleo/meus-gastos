import { esc } from './format.js';

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const paths = {
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z',
  spark: 'M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8',
  piggy: 'M5 11a7 6 0 0 1 12.6-3.5L20 7v4l1 1v3h-2.2a7 7 0 0 1-2.8 2.4V20h-3v-2h-3v2H7v-3A6 6 0 0 1 5 11zM15 10h.01',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01',
  list: 'M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01',
  upload: 'M12 15V3M7 8l5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4',
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  alert: 'M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  trend: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  bulb: 'M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
  check: 'M20 6 9 17l-5-5',
  x: 'M18 6 6 18M6 6l12 12',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3',
  plus: 'M12 5v14M5 12h14',
  left: 'M15 18l-6-6 6-6',
  right: 'M9 18l6-6-6-6',
  download: 'M12 3v12M7 10l5 5 5-5M4 19h16',
  share: 'M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 6l-4-4-4 4M12 2v13',
  chat: 'M21 11.5a8.4 8.4 0 0 1-12.3 7.5L3 21l2-5.5A8.4 8.4 0 1 1 21 11.5z',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  repeat: 'M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3',
  card: 'M2 7a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2zM2 10h20',
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6',
  trash: 'M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6',
  edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  lock: 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4',
  calendar: 'M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM16 2v4M8 2v4M3 10h18',
};
export const icon = (name, extra = '') => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}><path d="${paths[name] || paths.info}"/></svg>`;

export function toast(message, type = 'ok') {
  const el = document.createElement('div');
  el.className = 'toast' + (type === 'error' ? ' error' : '');
  el.textContent = message;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), type === 'error' ? 6500 : 3200);
}

export async function guard(task, success) {
  try {
    const result = await task();
    if (success) toast(success);
    return result;
  } catch (error) {
    toast(error.message, 'error');
    return undefined;
  }
}

export function options(values, selected, placeholder) {
  const list = values.map(v => typeof v === 'string' ? [v, v] : v);
  return (placeholder !== undefined ? `<option value="">${esc(placeholder)}</option>` : '') +
    list.map(([value, label]) => `<option value="${esc(value)}" ${String(value) === String(selected ?? '') ? 'selected' : ''}>${esc(label)}</option>`).join('');
}

export function segmented(name, values, selected) {
  return `<div class="segmented" role="group" data-seg="${name}">${values.map(([value, label, extra = '']) =>
    `<button type="button" data-value="${esc(value)}" class="${String(value) === String(selected) ? 'on' : ''}" aria-pressed="${String(value) === String(selected)}">${extra}${esc(label)}</button>`).join('')}</div>`;
}

/** Simple modal built on <dialog>; resolves with the submitted FormData or null. */
export function modal(html, { onOpen } = {}) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog');
    dialog.innerHTML = html;
    document.body.append(dialog);
    const close = value => { dialog.close(); dialog.remove(); resolve(value); };
    dialog.addEventListener('cancel', e => { e.preventDefault(); close(null); });
    dialog.addEventListener('click', e => {
      if (e.target === dialog || e.target.closest('[data-close]')) close(null);
    });
    const form = dialog.querySelector('form');
    form?.addEventListener('submit', e => {
      e.preventDefault();
      close({ data: new FormData(form), submitter: e.submitter?.value, form });
    });
    dialog.showModal();
    onOpen?.(dialog, close);
  });
}

export async function confirmDialog(title, body, action = 'Confirmar', danger = false) {
  const result = await modal(`<form><div class="dialog-head"><h2>${esc(title)}</h2></div><p>${body}</p>
    <div class="dialog-foot"><button type="button" class="btn" data-close>Cancelar</button><button class="btn ${danger ? 'danger' : 'primary'}" value="ok">${esc(action)}</button></div></form>`);
  return Boolean(result);
}

// Shared tooltip for every chart: marks carry data-tip with prepared HTML.
const tip = () => $('#tooltip');
export function showTip(html, x, y) {
  const el = tip();
  el.innerHTML = html;
  el.hidden = false;
  const { width, height } = el.getBoundingClientRect();
  const left = Math.min(window.innerWidth - width - 12, Math.max(12, x + 14));
  const top = y + height + 24 > window.innerHeight ? y - height - 14 : y + 16;
  el.style.left = left + 'px';
  el.style.top = top + 'px';
}
export const hideTip = () => { tip().hidden = true; };
document.addEventListener('pointermove', e => {
  const target = e.target.closest?.('[data-tip]');
  document.querySelectorAll('.chart g.hover').forEach(g => { if (!g.contains(e.target)) g.classList.remove('hover'); });
  if (!target) return hideTip();
  target.closest('g[data-group]')?.classList.add('hover');
  showTip(decodeURIComponent(target.dataset.tip), e.clientX, e.clientY);
});
document.addEventListener('focusin', e => {
  const target = e.target.closest?.('[data-tip]');
  if (!target) return;
  const box = target.getBoundingClientRect();
  showTip(decodeURIComponent(target.dataset.tip), box.left + box.width / 2, box.top);
});
document.addEventListener('focusout', hideTip);
document.addEventListener('scroll', hideTip, true);
