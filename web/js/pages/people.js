import { store, refresh, loadData } from '../main.js';
import { api } from '../api.js';
import { $, $$, icon, guard, segmented } from '../ui.js';
import { esc } from '../format.js';

const MAX = 6;
const SUGGESTIONS = { solo: ['Eu'], couple: ['Eu', 'Parceiro(a)'], family: ['Eu', 'Parceiro(a)', 'Filho(a)'] };

/**
 * Names form shared by the welcome wizard and Ajustes. Inputs keep the position of the
 * current names, so editing one renames it (and its transactions) instead of creating a new person.
 */
export function peopleEditor(target, house, { submitLabel = 'Salvar', onSaved, fresh = false } = {}) {
  // In the welcome wizard the names are suggestions, not existing people: nothing to rename.
  const original = fresh ? [] : [...house.members];
  const originalShared = fresh ? '' : house.shared;
  let members = [...house.members];
  let shared = house.shared;
  let withShared = Boolean(house.shared);

  const draw = () => {
    target.innerHTML = `<form class="people-form">
      <div class="people-list">${members.map((name, i) => `<div class="people-row"><i class="dot" style="background:var(--person-${i + 1})"></i>
        <input name="member" value="${esc(name)}" maxlength="30" required aria-label="Pessoa ${i + 1}" placeholder="Nome">
        ${members.length > 1 ? `<button type="button" class="icon-btn" data-remove="${i}" aria-label="Remover ${esc(name)}">${icon('x')}</button>` : ''}</div>`).join('')}
      </div>
      ${members.length < MAX - (withShared ? 1 : 0) ? `<button type="button" class="btn small" id="add-person">${icon('plus')}Adicionar pessoa</button>` : ''}
      ${members.length > 1 ? `<label class="check-tile" style="cursor:pointer"><input type="checkbox" id="with-shared" ${withShared ? 'checked' : ''}>
        <span><b>Gastos em conjunto</b><br><small>Um grupo para despesas da casa que não são de uma pessoa só (mercado, aluguel…). Não é dividido automaticamente.</small></span></label>
        ${withShared ? `<div class="people-row"><i class="dot" style="background:var(--person-${members.length + 1})"></i><input name="shared" value="${esc(shared || 'Compartilhado')}" maxlength="30" required aria-label="Nome do grupo"></div>` : ''}` : ''}
      <p class="lock-error" role="alert"></p>
      <button class="btn primary">${esc(submitLabel)}</button>
    </form>`;
    const form = $('form', target);
    const read = () => {
      members = $$('[name=member]', form).map(i => i.value);
      if ($('[name=shared]', form)) shared = $('[name=shared]', form).value;
    };
    $$('[data-remove]', form).forEach(b => b.addEventListener('click', () => { read(); members.splice(+b.dataset.remove, 1); original.splice(+b.dataset.remove, 1); draw(); }));
    $('#add-person', form)?.addEventListener('click', () => { read(); members.push(''); draw(); $$('[name=member]', target).at(-1).focus(); });
    $('#with-shared', form)?.addEventListener('change', e => { read(); withShared = e.target.checked; draw(); });
    form.addEventListener('submit', async e => {
      e.preventDefault();
      read();
      const finalShared = members.length > 1 && withShared ? shared.trim() : '';
      // Same position, new text = rename; removed positions are dropped server-side (only if empty).
      const renames = {};
      original.forEach((old, i) => { if (old && members[i] !== undefined && members[i].trim() !== old) renames[old] = members[i].trim(); });
      if (originalShared && finalShared && finalShared !== originalShared) renames[originalShared] = finalShared;
      try {
        await api('people', { members: members.map(m => m.trim()), shared: finalShared, renames });
        await onSaved?.();
      } catch (error) {
        $('.lock-error', form).textContent = error.message;
      }
    });
  };
  draw();
}

/** First run: who uses the app, then a nudge towards the password and the first import. */
export default function welcome(app) {
  let mode = 'couple';
  const draw = () => {
    app.innerHTML = `<div class="lock-wrap"><div class="card lock-card welcome-card">
      <div class="lock-icon">${icon('home')}</div>
      <h1>Bem-vindo ao Meus Gastos</h1>
      <p>Controle de gastos que roda só no seu computador, sem conectar contas bancárias. Para começar: quem vai usar?</p>
      ${segmented('household', [['solo', 'Só eu'], ['couple', 'Casal'], ['family', 'Família']], mode)}
      <div id="people-editor"></div>
      <small>Dá para mudar os nomes depois em Ajustes.</small>
    </div></div>`;
    $$('[data-seg="household"] button', app).forEach(b => b.addEventListener('click', () => { mode = b.dataset.value; draw(); }));
    peopleEditor($('#people-editor', app), { members: SUGGESTIONS[mode], shared: mode === 'solo' ? '' : 'Compartilhado' }, {
      submitLabel: 'Continuar',
      fresh: true,
      onSaved: async () => {
        app.innerHTML = `<div class="lock-wrap"><div class="card lock-card welcome-card">
          <div class="lock-icon">${icon('check')}</div><h1>Tudo pronto</h1>
          <p>Dois passos recomendados:</p>
          <a class="btn" href="/ajustes" data-link>${icon('lock')}Proteger os dados com senha</a>
          <a class="btn primary" href="/importar" data-link>${icon('upload')}Importar a primeira fatura ou extrato</a>
        </div></div>`;
        await loadData().catch(() => {});  // keep this screen; the links render the app
      },
    });
  };
  draw();
}

/** Card for Ajustes. */
export function peopleCard(target) {
  const house = store.data.household;
  target.innerHTML = `<article class="card" style="margin-bottom:16px">
    <div class="card-head"><div><h2>Pessoas</h2><p>Quem aparece nos filtros e em cada lançamento. Mudar um nome atualiza os lançamentos e os titulares de cartão.</p></div></div>
    <div id="people-settings"></div></article>`;
  peopleEditor($('#people-settings', target), house, { submitLabel: 'Salvar pessoas', onSaved: () => guard(refresh, 'Pessoas atualizadas.') });
}
