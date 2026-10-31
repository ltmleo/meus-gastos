from datetime import date, timedelta
from finance.domain import PEOPLE, PAYMENT_CHANNELS, payment_channel
from finance.classification import merchant_key


def period_scope(rows, month='', start='', end=''):
    if bool(start) != bool(end):
        raise ValueError('Informe a data inicial e a data final.')
    if start:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first.isoformat() != start or last.isoformat() != end:
            raise ValueError('Use datas no formato AAAA-MM-DD.')
        if first > last:
            raise ValueError('A data inicial deve ser anterior ou igual à data final.')
        if (last-first).days > 3660:
            raise ValueError('Selecione um período de até dez anos.')
        selected = [r for r in rows if start <= r['date'] <= end]
        days = (last-first).days + 1
        try:
            previous_end = first - timedelta(days=1)
            previous_start = first - timedelta(days=days)
            previous = [r for r in rows if previous_start.isoformat() <= r['date'] <= previous_end.isoformat()]
        except OverflowError:
            previous = []
        months, current = [], start[:7]
        while current <= end[:7]:
            months.append(current)
            if current == end[:7]:
                break
            current = month_offset(current, 1)
        return selected, previous, selected, months, end[:7], 'date'
    if month:
        date.fromisoformat(month+'-01')
    anchor = month or max((r['month'] for r in rows), default=date.today().isoformat()[:7])
    return ([r for r in rows if not month or r['month']==month],
            [r for r in rows if r['month']==month_offset(anchor,-1)], rows,
            [month_offset(anchor, offset) for offset in range(-5,1)], anchor, 'month')


def spending_channels(rows):
    expenses = [r for r in rows if r.get('kind', 'expense') == 'expense']
    return {channel: dict(
        expenses=sum(max(r['cents'], 0) for r in expenses if payment_channel(r) == channel),
        credits=-sum(min(r['cents'], 0) for r in expenses if payment_channel(r) == channel),
        net=sum(r['cents'] for r in expenses if payment_channel(r) == channel)
    ) for channel in PAYMENT_CHANNELS}


def spending_methods(rows):
    groups = {}
    for row in rows:
        if row.get('kind', 'expense') != 'expense':
            continue
        bank, channel = row.get('bank', 'unspecified'), payment_channel(row)
        key = channel + '_' + bank
        group = groups.setdefault(key, dict(bank=bank, channel=channel, expenses=0, credits=0, net=0, count=0))
        group['expenses'] += max(row['cents'], 0)
        group['credits'] -= min(row['cents'], 0)
        group['net'] += row['cents']
        group['count'] += 1
    return sorted(groups.values(), key=lambda g:g['expenses'], reverse=True)


def pending_expenses(rows):
    groups = {}
    for row in rows:
        if row.get('kind', 'expense') != 'expense' or row['category'] != 'Outros':
            continue
        key = merchant_key(row['description'])
        group = groups.setdefault(key, dict(merchant=key, cents=0, count=0, ids=[]))
        group['cents'] += row['cents']
        group['count'] += 1
        if 'id' in row:
            group['ids'].append(row['id'])
    return sorted(groups.values(), key=lambda r:abs(r['cents']), reverse=True)


def insights(rows, month, person='', channel='', start='', end=''):
    """Observed monthly results, not bank balances or forecasts."""
    filtered = [r for r in rows if (not person or r['person'] == person) and (not channel or payment_channel(r) == channel)]
    selected, previous_rows, history_rows, months, anchor, basis = period_scope(filtered, month, start, end)

    def totals(items):
        income = -sum(r['cents'] for r in items if r.get('kind') == 'income')
        expense = sum(r['cents'] for r in items if r.get('kind', 'expense') == 'expense')
        return dict(income=income, net=expense, result=income-expense,
                    available=bool(items), has_income=any(r.get('kind') == 'income' for r in items),
                    margin=(income-expense)/income*100 if income > 0 else None)

    def groups(items):
        result = {}
        for r in items:
            result[r['category']] = result.get(r['category'], 0) + r['cents']
        return result

    series = [dict(month=m, **totals([r for r in history_rows if r[basis][:7] == m])) for m in months]
    expenses = [r for r in selected if r.get('kind', 'expense') == 'expense']
    income_rows = [r for r in selected if r.get('kind') == 'income']
    income_categories = {k:-v for k,v in groups(income_rows).items()}
    before = groups([r for r in previous_rows if r.get('kind', 'expense') == 'expense'])
    current = groups(expenses)
    changes = sorted((dict(category=k, current=current.get(k, 0), previous=before.get(k, 0),
                           difference=current.get(k, 0)-before.get(k, 0)) for k in current.keys() | before.keys()),
                     key=lambda r: abs(r['difference']), reverse=True) if previous_rows and (month or start) else []
    # Repetition is an observation, not a contractual recurring commitment.
    repeats = {}
    for r in history_rows:
        if (start or month_offset(anchor, -5) <= r['month'] <= anchor) and r.get('kind', 'expense') == 'expense' and r['cents'] > 0:
            key = merchant_key(r['description'])
            repeats.setdefault(key, {}).setdefault(r[basis][:7], []).append(r)
    recurring = []
    for key, months in repeats.items():
        if len(months) >= 2 and (start or anchor in months):
            items = [r for values in months.values() for r in values]
            recurring.append(dict(merchant=key, months=len(months), current=sum(r['cents'] for r in (items if start else months[anchor])),
                                  average=round(sum(r['cents'] for r in items)/len(months)),
                                  installment=any(r.get('installment') for r in items)))
    recurring.sort(key=lambda r:r['current'], reverse=True)
    unknown = [r for r in selected if r['category'] in ('Outros', 'Outras receitas') or r.get('category_source') == 'unknown']
    transfers = [r for r in selected if r.get('kind') == 'transfer']
    return dict(**totals(selected), series=series, payment_channels=spending_channels(selected), payment_methods=spending_methods(selected), pending_groups=pending_expenses(selected),
                income_categories=dict(sorted(income_categories.items(), key=lambda p:p[1], reverse=True)),
                changes=changes, comparison_available=bool(previous_rows) and bool(month or start), recurring=recurring,
                recurring_month=anchor, unknown_count=len(unknown), unknown_volume=sum(abs(r['cents']) for r in unknown),
                transfer_in=-sum(min(r['cents'], 0) for r in transfers),
                transfer_out=sum(max(r['cents'], 0) for r in transfers),
                largest=sorted([r for r in expenses if r['cents'] > 0], key=lambda r:r['cents'], reverse=True)[:8])

def month_offset(month, offset):
    year, mon = map(int, month.split('-'))
    index = year * 12 + mon - 1 + offset
    return f'{index // 12:04d}-{index % 12 + 1:02d}'

def summarize(rows, month, person='', channel='', start='', end=''):
    rows = [r for r in rows if not channel or payment_channel(r) == channel]
    rows = [r for r in rows if not person or r['person']==person]
    selected, previous_all, history_rows, months, anchor, basis = period_scope(rows, month, start, end)
    count = len(selected)
    channels = spending_channels(selected)
    income = -sum(r['cents'] for r in selected if r.get('kind') == 'income')
    transfers = sum(abs(r['cents']) for r in selected if r.get('kind') == 'transfer')
    selected = [r for r in selected if r.get('kind', 'expense') == 'expense']
    rows = [r for r in rows if r.get('kind', 'expense') == 'expense']
    expenses = sum(max(r['cents'], 0) for r in selected)
    credits = -sum(min(r['cents'], 0) for r in selected)
    def group(items, key):
        result = {}
        for r in items:
            result[r[key]] = result.get(r[key], 0) + r['cents']
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
    filtered = [r for r in rows if not person or r['person'] == person]
    history = {}
    history_people = []
    for current in months:
        items = [r for r in history_rows if r[basis][:7] == current and r.get('kind','expense')=='expense']
        if items:
            history[current] = sum(r['cents'] for r in items)
        history_people.append(dict(month=current, available=bool(items), people={p:sum(r['cents'] for r in items if r['person']==p) for p in PEOPLE}))
    positive = [r for r in selected if r['cents'] > 0]
    merchants = {}
    for r in positive:
        key = merchant_key(r['description'])
        merchants[key] = merchants.get(key, 0) + r['cents']
    category_people = {}
    for r in positive:
        category_people.setdefault(r['category'], {p:0 for p in PEOPLE})[r['person']] += r['cents']
    previous_rows = [r for r in previous_all if r.get('kind','expense')=='expense']
    previous = sum(r['cents'] for r in previous_rows) if previous_rows else None
    return dict(expenses=expenses, credits=credits, net=expenses-credits, count=count, income=income, transfers=transfers, result=income-expenses+credits, payment_channels=channels, payment_methods=spending_methods(selected),
                classified_categories=group([r for r in selected if r['category']!='Outros'], 'category'), pending_groups=pending_expenses(selected),
                categories=group(selected, 'category'), people=group(selected, 'person'), history=history,
                people_expenses=group(positive,'person'), history_people=history_people,
                merchants=dict(sorted(merchants.items(), key=lambda x:x[1], reverse=True)[:8]),
                category_people=dict(sorted(category_people.items(), key=lambda x:sum(x[1].values()), reverse=True)),
                installments={'Parceladas':sum(r['cents'] for r in positive if r.get('installment')),
                              'Sem parcela indicada':sum(r['cents'] for r in positive if not r.get('installment'))},
                previous=previous, difference=(expenses-credits-previous) if previous is not None else None,
                review_count=sum(r['category']=='Outros' for r in selected))
