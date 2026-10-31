"""Dashboard bundle and savings insights.

Everything here is a pure function of the stored transactions: no network, no
side effects. Months use the reference month (invoice/statement), money is in
cents, expenses are net of refunds unless stated otherwise.
"""
import re
from collections import defaultdict
from datetime import date
from statistics import mean, pstdev

from finance.classification import merchant_key
from finance.domain import PEOPLE, payment_channel

FIXED = {'Moradia', 'Financiamentos', 'Seguros', 'Educação', 'Assinaturas'}
ESSENTIAL = FIXED | {'Mercado', 'Saúde', 'Transporte', 'Taxas e encargos'}
INSTALLMENT = re.compile(r'^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*$')
WEEKDAYS = ('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom')


def label(description):
    """Readable merchant name: no statement date or bank prefixes."""
    text = re.sub(r'^\s*\d{2}/\d{2}(?:/\d{2,4})?\s+', '', description)
    text = re.sub(r'^(?:PIX (?:ENVIADO|RECEBIDO)|PAGAMENTO DE BOLETO(?: OUTROS BANCOS)?|COMPRA CARTAO DEB MC \d{2}/\d{2})\s+', '', text, flags=re.I)
    return text.strip() or description


def month_offset(month, offset):
    year, mon = map(int, month.split('-'))
    index = year * 12 + mon - 1 + offset
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def is_expense(row):
    return row.get('kind', 'expense') == 'expense'


def _sum(rows):
    return sum(r['cents'] for r in rows)


def _by(rows, key):
    result = defaultdict(int)
    for r in rows:
        result[key(r)] += r['cents']
    return result


def baseline_months(months_with_data, anchor, size=3):
    """Up to `size` previous months that actually have expense data."""
    return [m for m in sorted(months_with_data, reverse=True) if m < anchor][:size]


def installment_parts(value):
    match = INSTALLMENT.match(value or '')
    if not match:
        return None
    current, total = map(int, match.groups())
    return (current, total) if 0 < current <= total and total > 1 else None


def competence(row):
    """Month the money was spent: purchase month; each installment in its own following month.

    A card invoice due in October holds mostly September purchases, so the stored
    reference month (invoice/statement) is shifted back to when the spending happened.
    """
    parts = installment_parts(row.get('installment'))
    return month_offset(row['date'][:7], parts[0] - 1) if parts else row['date'][:7]


def apply_basis(rows, basis='purchase'):
    """'purchase' (default) groups by competence; 'invoice' keeps the invoice/statement month."""
    if basis == 'invoice':
        return rows
    return [dict(r, invoice_month=r['month'], month=competence(r)) for r in rows]


def complete_until(rows):
    """Last purchase month fully covered: the month most purchases of the newest card invoice belong to.

    Later months only hold the first days of the next billing cycle, so they are partial.
    """
    credit = [r for r in rows if payment_channel(r) == 'credit']
    if not credit:
        return None
    newest = max(r.get('invoice_month', r['month']) for r in credit)
    months = defaultdict(int)
    for r in credit:
        if r.get('invoice_month', r['month']) == newest and not installment_parts(r.get('installment')):
            months[r['date'][:7]] += 1
    return max(months, key=lambda m: (months[m], m)) if months else month_offset(newest, -1)


def installments(rows, anchor):
    """Remaining charges of installment purchases seen in the anchor month."""
    active, projection = [], defaultdict(int)
    for r in rows:
        parts = installment_parts(r.get('installment'))
        if r['month'] != anchor or not parts or r['cents'] <= 0:
            continue
        current, total = parts
        remaining = total - current
        if not remaining:
            continue
        for step in range(1, remaining + 1):
            projection[month_offset(anchor, step)] += r['cents']
        active.append(dict(description=r['description'], installment=f'{current}/{total}', cents=r['cents'],
                           remaining=remaining, remaining_cents=remaining * r['cents'],
                           end_month=month_offset(anchor, remaining), person=r['person'], category=r['category']))
    active.sort(key=lambda a: a['remaining_cents'], reverse=True)
    horizon = [month_offset(anchor, step) for step in range(1, 13)]
    return dict(active=active, total_remaining=sum(a['remaining_cents'] for a in active),
                next_month=projection.get(horizon[0], 0),
                projection=[dict(month=m, cents=projection.get(m, 0)) for m in horizon if projection.get(m) or m <= max(projection, default='')])


def recurring(rows, anchor, window=6):
    """Charges that repeat with a stable amount: subscriptions and fixed bills.

    An observation from history, not a contract: needs three or more months in
    the window (or two consecutive ones), at most two charges a month and a
    monthly amount that varies less than 25%.
    """
    first = month_offset(anchor, -(window - 1))
    groups = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if is_expense(r) and r['cents'] > 0 and first <= r['month'] <= anchor and not installment_parts(r.get('installment')):
            groups[merchant_key(r['description'])][r['month']].append(r)
    found = []
    for merchant, months in groups.items():
        ordered = sorted(months)
        if any(len(items) > 2 for items in months.values()):
            continue
        totals = [_sum(months[m]) for m in ordered]
        average = mean(totals)
        if average <= 0 or pstdev(totals) / average > 0.25:
            continue
        sample = months[ordered[-1]][0]
        # Two months only count when consecutive, nearly identical and clearly a bill.
        consecutive = len(ordered) == 2 and month_offset(ordered[0], 1) == ordered[1]
        bill = sample['category'] in FIXED | {'Lazer', 'Saúde', 'Pets'} and pstdev(totals) / average < 0.03
        if len(ordered) < 3 and not (consecutive and bill):
            continue
        last, previous = totals[-1], totals[-2]
        found.append(dict(merchant=merchant, description=label(sample['description']), category=sample['category'],
                          person=sample['person'], months=len(ordered), average=round(average), last=last,
                          last_month=ordered[-1], active=ordered[-1] >= month_offset(anchor, -1),
                          annual=round(average * 12), change=last - previous,
                          change_pct=(last - previous) / previous * 100 if previous else None,
                          history=[dict(month=m, cents=t) for m, t in zip(ordered, totals)]))
    found.sort(key=lambda f: f['average'], reverse=True)
    return found


def duplicates(rows):
    seen = defaultdict(list)
    for r in rows:
        if is_expense(r) and r['cents'] > 0 and not r.get('installment'):
            seen[(merchant_key(r['description']), r['cents'], r['date'])].append(r)
    return [dict(description=label(items[0]['description']), cents=items[0]['cents'], date=items[0]['date'],
                 count=len(items), ids=[i.get('id') for i in items])
            for items in seen.values() if len(items) > 1]


def _money(cents):
    text = f'{abs(cents) / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if cents < 0 else '') + 'R$ ' + text


def _insight(kind, severity, title, body, saving=0, action=None, **extra):
    action = action or {}
    return dict(id=kind, severity=severity, title=title, body=body, saving=max(int(saving), 0), action=action,
                topic=action.get('category') or kind, **extra)


def build_insights(ctx):
    """Turn the computed context into short, ranked, actionable cards."""
    cards = []
    month_label = ctx['month']
    categories, baseline = ctx['categories'], ctx['baseline_months']
    if ctx.get('partial'):
        # Purchases still arriving with the next invoice: comparisons would only show false drops.
        baseline = []
        cards.append(_insight('partial', 'info', 'Mês em andamento',
                              'Este mês ainda não está completo: as compras feitas no cartão aparecem quando a próxima fatura '
                              'for importada. Comparações com a média ficam desativadas até lá.', 0))
    if ctx['budgets']:
        for b in ctx['budgets']:
            if b['spent'] > b['limit']:
                cards.append(_insight('budget-' + b['category'], 'alert', f'Orçamento de {b["category"]} estourado',
                                      f'{_money(b["spent"])} gastos para um limite de {_money(b["limit"])} '
                                      f'({b["pct"]:.0f}%). Excesso de {_money(b["spent"] - b["limit"])}.',
                                      0 if b['category'] in FIXED else b['spent'] - b['limit'],
                                      dict(page='transactions', category=b['category'])))
    for dup in ctx['duplicates'][:3]:
        cards.append(_insight('duplicate-' + dup['date'] + dup['description'], 'alert', 'Possível cobrança duplicada',
                              f'{dup["count"]}× {dup["description"]} de {_money(dup["cents"])} em '
                              f'{dup["date"][8:]}/{dup["date"][5:7]}. Confira se não foi cobrado duas vezes.',
                              dup['cents'] * (dup['count'] - 1), dict(page='transactions', search=dup['description'])))
    if baseline:
        for c in categories:
            if c['category'] in ('Outros', 'Taxas e encargos') or c['avg'] <= 0:
                continue
            difference = c['compare'] - c['avg']
            if difference >= 15000 and difference / c['avg'] >= 0.25:
                cards.append(_insight('spike-' + c['category'], 'warning', f'{c["category"]} acima do normal',
                                      f'{_money(c["compare"])} neste mês, {difference / c["avg"] * 100:.0f}% acima da média de '
                                      f'{_money(c["avg"])} ' + ('do mês anterior.' if len(baseline) == 1 else f'dos {len(baseline)} meses anteriores.'),
                                      difference, dict(page='transactions', category=c['category'])))
    fees = next((c for c in categories if c['category'] == 'Taxas e encargos'), None)
    if fees and fees['cents'] > 0:
        cards.append(_insight('fees', 'warning', 'Taxas, juros e IOF',
                              f'{_money(fees["cents"])} em encargos neste mês ({_money(fees["cents"] * 12)} em um ano no mesmo ritmo). '
                              'Compras internacionais, atrasos e anuidade costumam ser negociáveis ou evitáveis.',
                              fees['cents'], dict(page='transactions', category='Taxas e encargos')))
    price_ups = [r for r in ctx['recurring'] if r['active'] and r['change_pct'] and r['change_pct'] >= 5 and r['change'] >= 500]
    for r in price_ups[:2]:
        cards.append(_insight('price-' + r['merchant'], 'warning', f'{r["description"]} ficou mais caro',
                              f'Subiu {r["change_pct"]:.0f}% ({_money(r["change"])}) em relação ao mês anterior. '
                              'Vale conferir reajuste, plano ou consumo.', r['change'],
                              dict(page='transactions', search=r['description'])))
    food = next((c for c in categories if c['category'] == 'Alimentação'), None)
    market = next((c for c in categories if c['category'] == 'Mercado'), None)
    if food and food['cents'] >= 30000 and food['cents'] > (market['cents'] if market else 0) * 1.3:
        cards.append(_insight('eating-out', 'tip', 'Comer fora pesa mais que o mercado',
                              f'Alimentação fora de casa somou {_money(food["cents"])} ({food["count"]} compras), '
                              f'contra {_money(market["cents"] if market else 0)} em mercado. Trocar 30% dessas refeições por '
                              f'comida de casa economiza cerca de {_money(food["cents"] * 0.3)} por mês.',
                              food['cents'] * 0.3, dict(page='transactions', category='Alimentação')))
    small = ctx['small_purchases']
    if small['count'] >= 15 and small['cents'] >= 30000:
        cards.append(_insight('small', 'tip', 'Gastos formiga',
                              f'{small["count"]} compras abaixo de R$ 50 somaram {_money(small["cents"])}. '
                              f'Cortar um terço delas rende {_money(small["cents"] / 3 * 12)} por ano.',
                              small['cents'] / 3, dict(page='transactions', max_value=5000)))
    subs = [r for r in ctx['recurring'] if r['active']]
    if subs:
        monthly = sum(r['average'] for r in subs)
        names = ', '.join(r['description'] for r in subs[:4])
        cards.append(_insight('recurring', 'tip', f'{len(subs)} cobranças recorrentes · {_money(monthly)}/mês',
                              f'Inclui {names}{"…" if len(subs) > 4 else ""}. São {_money(monthly * 12)} por ano: '
                              'revise o que não usa e renegocie planos de telefone, internet e seguros.',
                              0, dict(page='insights', anchor='recurring')))
    weekend = ctx['weekday']
    total_week = sum(w['cents'] for w in weekend)
    weekend_share = (weekend[5]['cents'] + weekend[6]['cents']) / total_week if total_week > 0 else 0
    if total_week >= 50000 and weekend_share >= 0.4:
        cards.append(_insight('weekend', 'tip', 'Fim de semana concentra os gastos',
                              f'{weekend_share * 100:.0f}% das compras dos últimos meses foram em sábados e domingos. '
                              'Planejar passeios e refeições antes ajuda a evitar impulsos.', 0))
    top = ctx['merchants'][:1]
    if top and ctx['kpis']['expense'] > 0 and top[0]['cents'] / ctx['kpis']['expense'] >= 0.12 and top[0]['count'] >= 3:
        m = top[0]
        cards.append(_insight('merchant-' + m['merchant'], 'info', f'{m["description"]} lidera os gastos',
                              f'{m["count"]} compras somando {_money(m["cents"])} '
                              f'({m["cents"] / ctx["kpis"]["expense"] * 100:.0f}% do mês).', 0,
                              dict(page='transactions', search=m['description'])))
    inst = ctx['installments']
    if inst['total_remaining'] > 0:
        cards.append(_insight('installments', 'info', f'{_money(inst["next_month"])} já comprometidos no próximo mês',
                              f'{len(inst["active"])} compras parceladas ainda somam {_money(inst["total_remaining"])} a pagar. '
                              'Evite novos parcelamentos até essas parcelas diminuírem.', 0,
                              dict(page='insights', anchor='installments')))
    kpis = ctx['kpis']
    if kpis['has_income'] and kpis['income'] > 0 and not ctx.get('partial'):
        rate = kpis['savings_rate']
        if rate < 0:
            cards.append(_insight('savings-rate', 'alert', f'Gastos superaram os ganhos em {_money(-kpis["result"])}',
                                  'O mês fechou no vermelho. Veja abaixo onde houve aumento e quais cortes têm mais efeito.', 0))
        elif rate < 10:
            cards.append(_insight('savings-rate', 'warning', f'Taxa de poupança de {rate:.0f}%',
                                  'O recomendado é guardar pelo menos 10% a 20% do que entra. Comece pelas sugestões de corte abaixo.', 0))
        elif rate >= 20:
            cards.append(_insight('savings-rate', 'good', f'Você guardou {rate:.0f}% dos ganhos',
                                  f'Resultado positivo de {_money(kpis["result"])} em {month_label}. Considere separar parte para a reserva de emergência.', 0))
    good = 0
    for c in sorted(categories, key=lambda c: c['compare'] - c['avg']):
        if baseline and c['avg'] >= 20000 and c['compare'] <= c['avg'] * 0.7 and c['category'] != 'Outros' and good < 3:
            good += 1
            cards.append(_insight('drop-' + c['category'], 'good', f'{c["category"]} caiu {(1 - c["compare"] / c["avg"]) * 100:.0f}%',
                                  f'{_money(c["compare"])} contra média de {_money(c["avg"])}. Boa!', 0))
    if 'account' in ctx['missing_sources'] and not ctx.get('partial'):
        cards.append(_insight('missing-statement', 'info', 'Extrato da conta deste mês não importado',
                              'Só a fatura do cartão foi lida. Ganhos, PIX e boletos ficam de fora, e as comparações '
                              'usam apenas o cartão nos meses anteriores. Importe o extrato para ver o resultado do mês.', 0,
                              dict(page='import')))
    if ctx['pending']['count']:
        cards.append(_insight('pending', 'info', f'{ctx["pending"]["count"]} lançamentos sem categoria',
                              f'{_money(ctx["pending"]["cents"])} em Outros. Classificar deixa os insights mais precisos.', 0,
                              dict(page='transactions', category='Outros')))
    order = {'alert': 0, 'warning': 1, 'tip': 2, 'info': 3, 'good': 4}
    cards.sort(key=lambda c: (order[c['severity']], -c['saving']))
    return cards


def dashboard(rows, budgets=None, month='', person='', channel='', basis='purchase', people=PEOPLE):
    budgets = budgets or {}
    rows = apply_basis(rows, basis)
    covered = complete_until(rows) if basis != 'invoice' else None
    rows = [r for r in rows if (not person or r['person'] == person) and (not channel or payment_channel(r) == channel)]
    expense_rows = [r for r in rows if is_expense(r)]
    months_available = sorted({r['month'] for r in rows}, reverse=True)
    if month:
        date.fromisoformat(month + '-01')
    default = covered if covered in months_available else (months_available[0] if months_available else date.today().isoformat()[:7])
    anchor = month or default
    expense_months = {r['month'] for r in expense_rows}
    selected = [r for r in rows if r['month'] == anchor]
    channels_by_month = defaultdict(set)
    for r in rows:
        channels_by_month[r['month']].add(payment_channel(r))
    coverage = channels_by_month[anchor] or {'credit', 'account', 'unspecified'}
    comparable = {m for m in expense_months if channels_by_month[m] >= coverage}
    baseline = baseline_months(comparable, anchor) or baseline_months(expense_months, anchor)
    compare_channels = set(coverage)
    for m in baseline:
        compare_channels &= channels_by_month[m]

    expenses = [r for r in selected if is_expense(r)]
    income_rows = [r for r in selected if r.get('kind') == 'income']
    gross = sum(max(r['cents'], 0) for r in expenses)
    credits = -sum(min(r['cents'], 0) for r in expenses)
    net = gross - credits
    income = -_sum(income_rows)
    # A month imported only from the card invoice must not be compared with
    # months that also include the bank statement: compare the same sources.
    missing = sorted({payment_channel(r) for r in rows if r['month'] in baseline} - coverage)
    by_month_cat = defaultdict(lambda: defaultdict(int))
    for r in expense_rows:
        if payment_channel(r) in compare_channels:
            by_month_cat[r['month']][r['category']] += r['cents']
    previous_net = _sum([r for r in expense_rows if r['month'] == month_offset(anchor, -1) and payment_channel(r) in coverage]) if month_offset(anchor, -1) in expense_months else None
    baseline_total = round(mean(sum(by_month_cat[m].values()) for m in baseline)) if baseline else None

    current = _by(expenses, lambda r: r['category'])
    counts = defaultdict(int)
    for r in expenses:
        counts[r['category']] += 1
    names = set(current) | {c for m in baseline for c in by_month_cat[m]}
    categories = []
    for name in names:
        avg = round(mean(by_month_cat[m].get(name, 0) for m in baseline)) if baseline else 0
        cents = current.get(name, 0)
        if cents == 0 and avg == 0:
            continue
        categories.append(dict(category=name, cents=cents, compare=by_month_cat[anchor].get(name, 0), count=counts.get(name, 0), avg=avg,
                               previous=by_month_cat[month_offset(anchor, -1)].get(name, 0),
                               share=cents / net * 100 if net > 0 else 0,
                               essential=name in ESSENTIAL, fixed=name in FIXED))
    categories.sort(key=lambda c: (c['cents'], c['avg']), reverse=True)

    window = [month_offset(anchor, -i) for i in range(11, -1, -1)]
    first_data = min(expense_months | {r['month'] for r in rows}, default=anchor)
    window = [m for m in window if m >= first_data] or [anchor]
    cashflow = []
    for m in window:
        items = [r for r in rows if r['month'] == m]
        exp = _sum([r for r in items if is_expense(r)])
        inc = -_sum([r for r in items if r.get('kind') == 'income'])
        has_income = any(r.get('kind') == 'income' for r in items)
        cashflow.append(dict(month=m, income=inc, expense=exp, result=inc - exp if has_income else None,
                             has_income=has_income, available=bool(items),
                             people={p: _sum([r for r in items if is_expense(r) and r['person'] == p]) for p in people}))

    trend_months = window[-6:]
    top_names = [c['category'] for c in categories if c['category'] != 'Outros'][:6]
    category_trend = dict(months=trend_months, series=[
        dict(category=name, values=[by_month_cat[m].get(name, 0) if m in expense_months else None for m in trend_months])
        for name in top_names])

    merchants = defaultdict(lambda: dict(cents=0, count=0, description=''))
    for r in expenses:
        if r['cents'] <= 0:
            continue
        m = merchants[merchant_key(r['description'])]
        m['cents'] += r['cents']
        m['count'] += 1
        m['description'] = m['description'] or label(r['description'])
        m['category'] = r['category']
    merchant_list = sorted((dict(merchant=k, **v) for k, v in merchants.items()), key=lambda m: m['cents'], reverse=True)[:12]

    recent = [r for r in expense_rows if r['cents'] > 0 and month_offset(anchor, -5) <= r['month'] <= anchor]
    weekday = [dict(day=WEEKDAYS[i], cents=0, count=0) for i in range(7)]
    daily = defaultdict(int)
    for r in recent:
        d = date.fromisoformat(r['date'])
        weekday[d.weekday()]['cents'] += r['cents']
        weekday[d.weekday()]['count'] += 1
        daily[r['date']] += r['cents']

    small = [r for r in expenses if 0 < r['cents'] < 5000]
    pending = [r for r in expenses if r['category'] == 'Outros']
    budget_rows = []
    for name, limit in sorted(budgets.items()):
        spent = current.get(name, 0)
        avg = next((c['avg'] for c in categories if c['category'] == name), 0)
        budget_rows.append(dict(category=name, limit=limit, spent=spent, avg=avg,
                                pct=spent / limit * 100 if limit else 0,
                                status='over' if spent > limit else 'near' if spent >= limit * 0.85 else 'ok'))
    budget_rows.sort(key=lambda b: b['pct'], reverse=True)

    has_income = bool(income_rows)
    sources = _by(income_rows, lambda r: r['category'])
    income_sources = sorted((dict(category=k, cents=-v) for k, v in sources.items() if v < 0), key=lambda x: x['cents'], reverse=True)
    kpis = dict(expense=net, gross=gross, credits=credits, income=income, has_income=has_income,
                result=income - net if has_income else None,
                savings_rate=(income - net) / income * 100 if has_income and income > 0 else None,
                previous=previous_net, baseline=baseline_total, count=len(expenses),
                fixed=sum(c['cents'] for c in categories if c['fixed']),
                essential=sum(c['cents'] for c in categories if c['essential']),
                people={p: _sum([r for r in expenses if r['person'] == p]) for p in people},
                channels={ch: _sum([r for r in expenses if payment_channel(r) == ch]) for ch in ('credit', 'account', 'unspecified')})

    ctx = dict(month=anchor, months_available=months_available, baseline_months=baseline, kpis=kpis, missing_sources=missing,
               income_sources=income_sources, basis=basis, default_month=default,
               partial=bool(covered and anchor > covered),
               categories=categories, cashflow=cashflow, category_trend=category_trend, merchants=merchant_list,
               weekday=weekday, daily=[dict(date=k, cents=v) for k, v in sorted(daily.items())],
               installments=installments(rows, anchor), recurring=recurring(rows, anchor),
               duplicates=duplicates(expenses), small_purchases=dict(count=len(small), cents=_sum(small)),
               pending=dict(count=len(pending), cents=_sum(pending)), budgets=budget_rows,
               largest=sorted((dict(id=r.get('id'), date=r['date'], description=r['description'], cents=r['cents'],
                                    category=r['category'], person=r['person'], installment=r.get('installment', ''))
                               for r in expenses if r['cents'] > 0), key=lambda r: r['cents'], reverse=True)[:8])
    ctx['insights'] = build_insights(ctx)
    # Several cards can point at the same category (over budget and above average): count it once.
    by_topic = {}
    for c in ctx['insights']:
        if c['severity'] in ('alert', 'warning', 'tip'):
            by_topic[c['topic']] = max(by_topic.get(c['topic'], 0), c['saving'])
    ctx['potential_saving'] = sum(by_topic.values())
    return ctx


def suggest_budgets(rows, anchor=None, margin=0.95, basis='purchase'):
    """A starting point: recent average of each variable expense category, trimmed by 5%."""
    rows = apply_basis(rows, basis)
    covered = complete_until(rows) if basis != 'invoice' else None
    expense_rows = [r for r in rows if is_expense(r) and (not covered or r['month'] <= covered)]
    months = sorted({r['month'] for r in expense_rows}, reverse=True)
    if anchor:
        months = [m for m in months if m <= anchor]
    recent = months[:3]
    if not recent:
        return {}
    totals = defaultdict(int)
    for r in expense_rows:
        if r['month'] in recent:
            totals[r['category']] += r['cents']
    result = {}
    for name, cents in totals.items():
        average = cents / len(recent)
        if name == 'Outros' or average < 5000:
            continue
        factor = 1 if name in FIXED else margin
        result[name] = int(round(average * factor / 1000) * 1000) or 1000
    return result
