"""Fills a new database with six months of fictitious data, for screenshots and development.

Usage:
    python scripts/demo_data.py /tmp/demo/financas.sqlite3
    python app.py --db /tmp/demo/financas.sqlite3
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finance.classification import suggest  # noqa: E402
from finance.insights import month_offset  # noqa: E402
from finance.repository import Repository  # noqa: E402

PEOPLE = ['Ana', 'Bruno']
SHARED = 'Casa'
# (description, min, max, times per month, person) — values in reais
VARIABLE = [
    ('SUPERMERCADO BOM PRECO', 180, 420, 3, SHARED), ('HORTIFRUTI DO BAIRRO', 35, 90, 3, SHARED),
    ('IFOOD *RESTAURANTE', 45, 120, 4, 'Bruno'), ('PADARIA PAO QUENTE', 12, 40, 6, SHARED),
    ('POSTO SHELL', 150, 260, 2, 'Bruno'), ('UBER *TRIP', 15, 45, 4, 'Ana'),
    ('DROGARIA SAUDE', 25, 140, 2, 'Ana'), ('MERCADOLIVRE*LOJA', 40, 320, 2, 'Ana'),
    ('CINEMA SHOPPING', 50, 90, 1, SHARED), ('PIZZARIA NAPOLI', 70, 130, 2, SHARED),
    ('RENNER', 80, 260, 1, 'Ana'), ('PETZ', 60, 180, 1, SHARED), ('CAFE CENTRAL', 10, 28, 5, 'Bruno'),
]
FIXED = [  # (description, value, day, person, category)
    ('NETFLIX.COM', 55.90, 5, SHARED, None), ('SPOTIFY', 34.90, 8, 'Bruno', None),
    ('ACADEMIA FORMA', 119.90, 10, 'Ana', None), ('CONTA VIVO', 129.99, 15, SHARED, None),
    ('ENEL DISTRIBUICAO', 0, 18, SHARED, None), ('CONDOMINIO RESIDENCIAL', 680.00, 5, SHARED, None),
    ('PORTO SEGURO AUTO', 212.40, 12, 'Bruno', None),
]


def money(value):
    return int(round(value * 100))


def build(path, months=6, seed=7):
    random.seed(seed)
    repo = Repository(path)
    repo.set_household(PEOPLE, SHARED)
    today = date.today().replace(day=1)
    rows = []
    for back in range(months, 0, -1):
        month = month_offset(today.isoformat()[:7], -back)
        first = date.fromisoformat(month + '-01')
        invoice = month_offset(month, 1)  # card purchases arrive on next month's invoice
        for description, low, high, times, person in VARIABLE:
            for _ in range(times):
                day = first + timedelta(days=random.randint(0, 27))
                rows.append(dict(date=day.isoformat(), month=invoice, description=description,
                                 cents=money(random.uniform(low, high)), person=person, kind='expense',
                                 payment_channel='credit', bank='unspecified', card='1234'))
        for description, value, day, person, _ in FIXED:
            value = value or random.uniform(160, 260)
            rows.append(dict(date=first.replace(day=day).isoformat(), month=invoice, description=description,
                             cents=money(value), person=person, kind='expense', payment_channel='credit',
                             bank='unspecified', card='1234'))
        if back in (3, 2, 1):  # a 3x purchase
            rows.append(dict(date=month_offset(today.isoformat()[:7], -3) + '-20', month=invoice, description='LOJA DE MOVEIS',
                             cents=money(450), person=SHARED, kind='expense', payment_channel='credit', bank='unspecified',
                             card='1234', installment=f'0{4 - back}/03'))
        rows.append(dict(date=first.replace(day=5).isoformat(), month=month, description='SALARIO EMPRESA ALFA',
                         cents=-money(6200), person='Ana', kind='income', payment_channel='account', bank='unspecified'))
        rows.append(dict(date=first.replace(day=6).isoformat(), month=month, description='SALARIO EMPRESA BETA',
                         cents=-money(5400), person='Bruno', kind='income', payment_channel='account', bank='unspecified'))
        rows.append(dict(date=first.replace(day=10).isoformat(), month=month, description='ALUGUEL APTO',
                         cents=money(2300), person=SHARED, kind='expense', payment_channel='account', bank='unspecified'))
    for row in rows:
        suggestion = suggest(row['description'], kind=row['kind'])
        row.update(category=suggestion['category'], category_source='suggested')
    repo.save(rows)
    repo.set_budgets({'Alimentação': 90000, 'Mercado': 160000, 'Transporte': 70000, 'Compras': 50000})
    return len(rows)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    target = Path(sys.argv[1])
    if target.exists():
        sys.exit(f'{target} já existe: use um arquivo novo para não misturar com dados reais.')
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f'{build(target)} lançamentos fictícios em {target}')
