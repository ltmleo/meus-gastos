export * from './state.js';
import { store, PEOPLE_COLORS, monthOf } from './state.js';
import { api, query, whenLocked } from './api.js';
import { $, $$, icon, toast, options, segmented } from './ui.js';
import { monthShort, monthLong, monthOffset, esc } from './format.js';
import overview from './pages/overview.js';
import savings from './pages/savings.js';
import budget from './pages/budget.js';
import transactions from './pages/transactions.js';
import importer from './pages/importer.js';
import settings from './pages/settings.js';
import report from './pages/report.js';
import lockScreen from './pages/lock.js';
import welcomeScreen from './pages/people.js';

const ROUTES = [
  { path: '/', name: 'Painel', icon: 'home', page: overview, filters: true, desc: 'Como foi o mês, em um olhar' },
  { path: '/economizar', name: 'Economizar', icon: 'piggy', page: savings, filters: true, desc: 'Onde dá para gastar menos' },
  { path: '/orcamento', name: 'Orçamento', icon: 'target', page: budget, filters: true, desc: 'Limites por categoria' },
  { path: '/lancamentos', name: 'Lançamentos', icon: 'list', page: transactions, filters: false, desc: 'Busque, edite e classifique' },
  { path: '/importar', name: 'Importar', icon: 'upload', page: importer, filters: false, desc: 'Fatura ou extrato, sem conectar o banco' },
  { path: '/ajustes', name: 'Ajustes', icon: 'gear', page: settings, filters: false, desc: 'Regras, contas próprias e backup' },
];
// Printable monthly report: no app chrome, always on light "paper".
const REPORT = { path: '/relatorio', name: 'Relatório', page: report, filters: false, desc: '' };

export async function loadData() {
  store.data = await api('data');
  store.pending = store.data.transactions.filter(r => r.category === 'Outros' && r.kind === 'expense').length;
  const months = [...new Set(store.data.transactions.map(monthOf))].sort().reverse();
  store.months = months;
  if (!store.month || !months.includes(store.month)) store.month = store.data.default_months?.[store.basis] || months[0] || '';
  return store.data;
}

export async function loadDashboard() {
  store.dash = await api('dashboard?' + query({ month: store.month, person: store.person, channel: store.channel, basis: store.basis === 'invoice' ? 'invoice' : '' }));
  return store.dash;
}

export function navigate(path, params = {}) {
  const url = path + (Object.keys(params).length ? '?' + query(params) : '');
  history.pushState({}, '', url);
  render();
}

function syncUrlState() {
  const params = new URLSearchParams(location.search);
  if (params.get('m')) store.month = params.get('m');
  if (params.has('p')) store.person = params.get('p');
}

function renderNav(route) {
  const link = r => `<a href="${r.path}" data-link class="nav-item ${r === route ? 'active' : ''}" ${r === route ? 'aria-current="page"' : ''}>${icon(r.icon)}<span>${r.name}</span>${r.path === '/lancamentos' && store.pending ? `<span class="count" title="Sem categoria">${store.pending}</span>` : ''}</a>`;
  $('#nav').innerHTML = ROUTES.slice(0, 3).map(link).join('') + '<div class="nav-section">Dados</div>' + ROUTES.slice(3).map(link).join('');
  $('#tabbar').innerHTML = ROUTES.map(r => `<a href="${r.path}" data-link class="${r === route ? 'active' : ''}">${icon(r.icon)}<span>${r.name}</span></a>`).join('');
}

function renderTopbar(route) {
  const months = store.months || [];
  const index = months.indexOf(store.month);
  const filters = route.filters && months.length ? `
    <div class="month-picker" title="${store.basis === 'invoice' ? 'Mês da fatura/extrato' : 'Mês em que a compra foi feita'} · altere em Ajustes">
      <button class="ghost" data-month-step="1" ${index >= months.length - 1 ? 'disabled' : ''} aria-label="Mês anterior">${icon('left', 'width="16" height="16"')}</button>
      <select id="month-select" aria-label="Mês">${options(months.map(m => [m, monthShort(m)]), store.month)}</select>
      <button class="ghost" data-month-step="-1" ${index <= 0 ? 'disabled' : ''} aria-label="Próximo mês">${icon('right', 'width="16" height="16"')}</button>
    </div>
    ${segmented('person', [['', 'Todos'], ...store.data.people.map(p => [p, p, `<i class="dot" style="background:${PEOPLE_COLORS[p]}"></i>`])], store.person)}
    <select id="channel-select" aria-label="Meio de pagamento">${options([['', 'Cartão e conta'], ['credit', 'Só cartão'], ['account', 'Só conta']], store.channel)}</select>` : '';
  $('#topbar').innerHTML = `<div class="title"><h1>${route.name}</h1><small>${route.filters && store.month ? esc(monthLong(store.month)) + (store.basis === 'invoice' ? ' · por mês da fatura' : ' · por mês da compra') : route.desc}</small></div>${filters}
    ${route.filters && months.length ? `<a class="btn" href="/relatorio?m=${store.month}${store.person ? '&p=' + encodeURIComponent(store.person) : ''}" data-link title="Relatório do mês em PDF" aria-label="Relatório do mês em PDF">${icon('file')}<span class="hide-narrow">Relatório</span></a>` : ''}
    ${route.path !== '/importar' ? `<a class="btn primary" href="/importar" data-link>${icon('upload')}<span>Importar</span></a>` : ''}`;
}

// Encryption: when the database is protected, nothing renders until it is unlocked.
let unlocking = null;
async function ensureUnlocked() {
  if (new URLSearchParams(location.search).get('pt')) return;  // headless PDF run
  store.security = await api('security/status');
  if (!store.security.protected || (!store.security.locked && store.security.session)) return;
  await showLock(store.security);
}
function showLock(status) {
  if (!unlocking) {
    forgetData();
    document.body.classList.add('locked-mode');
    unlocking = lockScreen($('#app'), status).then(async () => {
      document.body.classList.remove('locked-mode');
      unlocking = null;
      store.security = await api('security/status');
    });
  }
  return unlocking;
}
function forgetData() {
  store.data = null;
  store.dash = null;
  try { sessionStorage.clear(); } catch { /* optional */ }
}
whenLocked(async () => { await showLock(await api('security/status').catch(() => ({ protected: true, locked: true }))); render(); });

/** Stop the local server (there is no console window in the packaged app). */
export async function quitApp() {
  await api('shutdown', {}).catch(() => {});
  forgetData();
  document.body.classList.add('locked-mode');
  $('#app').innerHTML = `<div class="lock-wrap"><div class="card lock-card"><div class="lock-icon">${icon('check')}</div>
    <h1>Meus Gastos foi encerrado</h1><p>Os dados ficaram salvos${store.security?.protected ? ' e criptografados' : ''}. Pode fechar esta aba. Para voltar, abra o aplicativo de novo.</p></div></div>`;
}

export async function lockNow() {
  await api('security/lock', {});
  await showLock({ ...store.security, locked: true });
  render();
}

let renderToken = 0;
export async function render() {
  const token = ++renderToken;
  try { await ensureUnlocked(); } catch { /* status is public; failures surface below */ }
  if (token !== renderToken) return;
  syncUrlState();
  const route = location.pathname === REPORT.path ? REPORT : ROUTES.find(r => r.path === location.pathname) || ROUTES[0];
  setReportMode(route === REPORT);
  document.title = `${route.name} · Meus Gastos`;
  try {
    if (!store.data) await loadData();
  } catch (error) {
    $('#app').innerHTML = `<div class="card empty-state">${icon('alert')}<h2>Não foi possível carregar</h2><p>${esc(error.message)}</p></div>`;
    return;
  }
  if (!store.data.household?.configured && !store.data.transactions.length && route !== REPORT) {
    document.body.classList.add('locked-mode');  // first run: just the wizard, no app chrome
    return welcomeScreen($('#app'));
  }
  document.body.classList.remove('locked-mode');
  renderNav(route);
  renderTopbar(route);
  $('#lock-now').hidden = !store.security?.protected;
  if (route === REPORT) return route.page(document.getElementById('app'), new URLSearchParams(location.search));
  if (route.filters && !store.data.transactions.length) {
    $('#app').innerHTML = welcome();
    return;
  }
  if (route.filters) {
    $('#app').innerHTML = '<div class="grid cols-4">' + '<div class="skeleton"></div>'.repeat(4) + '</div><div class="skeleton mt" style="min-height:300px"></div>';
    try { await loadDashboard(); } catch (error) { toast(error.message, 'error'); }
    if (token !== renderToken) return;
  }
  await route.page(document.getElementById('app'), new URLSearchParams(location.search));
}

let themeBeforeReport = null;
function setReportMode(on) {
  const root = document.documentElement;
  if (on === document.body.classList.contains('report-mode')) return;
  document.body.classList.toggle('report-mode', on);
  if (on) { themeBeforeReport = root.dataset.theme || ''; root.dataset.theme = 'light'; }
  else if (themeBeforeReport !== null) { if (themeBeforeReport) root.dataset.theme = themeBeforeReport; else delete root.dataset.theme; themeBeforeReport = null; }
}

function welcome() {
  return `<div class="card empty-state" style="padding:72px 24px">${icon('lock')}<h2>Suas finanças, sem conectar o banco</h2>
    <p>Importe a fatura do cartão (PDF Santander, CSV Nubank ou CSV simples de qualquer banco) ou o extrato da conta. Tudo é lido e guardado só neste computador.</p>
    <a class="btn primary" href="/importar" data-link>${icon('upload')}Importar primeiro arquivo</a></div>`;
}

export async function refresh() {
  await loadData();
  await render();
}

// Global events
document.addEventListener('click', e => {
  const link = e.target.closest('a[data-link]');
  if (link && !e.metaKey && !e.ctrlKey && link.origin === location.origin) {
    e.preventDefault();
    history.pushState({}, '', link.pathname + link.search);
    render();
    $('#app').focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
    return;
  }
  const step = e.target.closest('[data-month-step]');
  if (step) {
    const months = store.months, i = months.indexOf(store.month) + Number(step.dataset.monthStep);
    if (months[i]) { store.month = months[i]; replaceParams(); render(); }
  }
  const seg = e.target.closest('#topbar [data-seg="person"] button');
  if (seg) { store.person = seg.dataset.value; replaceParams(); render(); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'month-select') { store.month = e.target.value; replaceParams(); render(); }
  if (e.target.id === 'channel-select') { store.channel = e.target.value; render(); }
});
function replaceParams() {
  const params = new URLSearchParams(location.search);
  params.set('m', store.month);
  store.person ? params.set('p', store.person) : params.delete('p');
  history.replaceState({}, '', location.pathname + '?' + params);
}
window.addEventListener('popstate', render);

// Theme: follows the system until the user picks one.
const savedTheme = (() => { try { return localStorage.getItem('theme'); } catch { return null; } })();
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$('#theme-toggle').innerHTML = icon('moon', 'width="15" height="15"') + ' Alternar tema';
$('#lock-now').innerHTML = icon('lock', 'width="15" height="15"') + ' Bloquear agora';
$('#lock-now').addEventListener('click', lockNow);
$('#quit-app').innerHTML = icon('x', 'width="15" height="15"') + ' Encerrar app';
$('#quit-app').addEventListener('click', quitApp);
$('#theme-toggle').addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('theme', document.documentElement.dataset.theme); } catch { /* optional */ }
  render();
});

render();
