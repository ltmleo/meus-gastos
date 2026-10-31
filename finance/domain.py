from datetime import date
from decimal import Decimal, InvalidOperation

# Default household for databases created before people became configurable.
PEOPLE = ('Eu', 'Esposa', 'Compartilhado')
MAX_PEOPLE = 6
BANKS = ('santander', 'nubank', 'unspecified')
PAYMENT_CHANNELS = ('credit', 'account', 'unspecified')


def payment_channel(row):
    if row.get('payment_channel'):
        return row['payment_channel']
    if row.get('card'):
        return 'credit'
    from finance.classification import normalized
    import re
    if re.search(r'\b(?:PIX ENVIADO|PIX RECEBIDO|PAGAMENTO DE BOLETO|COMPRA CARTAO DEB|LIQUIDO DE VENCIMENTO|REMUNERACAO APLICACAO|VENCIMENTO CDB|PAGAMENTO CARTAO CREDITO|DEBITO AUT)\b', normalized(row.get('description', ''))):
        return 'account'
    return 'unspecified'
CATEGORIES = ('Alimentação', 'Mercado', 'Transporte', 'Moradia', 'Saúde', 'Lazer', 'Compras', 'Educação', 'Assinaturas', 'Beleza e cuidados', 'Vestuário', 'Bebê e crianças', 'Pets', 'Seguros', 'Taxas e encargos', 'Viagens', 'Casa e decoração', 'Financiamentos', 'Doações', 'Salário', 'Rendimentos', 'Outras receitas', 'Pagamento de cartão', 'Investimentos', 'Transferências', 'Outros')

def money(value):
    text = str(value).strip().replace('R$', '').replace(' ', '')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        amount = Decimal(text)
        if not amount.is_finite() or amount != amount.quantize(Decimal('.01')):
            raise ValueError('Valor deve ter no máximo duas casas decimais.')
        return int(amount * 100)
    except (InvalidOperation, OverflowError):
        raise ValueError('Valor inválido.')

def category(description):
    from finance.classification import suggest
    return suggest(description)['category']

def validate(row, people=None):
    date.fromisoformat(row['date'])
    date.fromisoformat(row['month'] + '-01')
    if row['person'] not in (people or PEOPLE) or row['category'] not in CATEGORIES:
        raise ValueError('Pessoa ou categoria inválida.')
    if not isinstance(row['cents'], int) or isinstance(row['cents'], bool) or abs(row['cents']) > 10**12:
        raise ValueError('Valor inválido.')
    if not isinstance(row['description'], str) or not row['description'].strip() or len(row['description']) > 500:
        raise ValueError('Descrição obrigatória (até 500 caracteres).')
    result = {key: row[key] for key in ('date', 'month', 'description', 'cents', 'person', 'category')}
    for key in ('card', 'installment'):
        value = row.get(key, '')
        if not isinstance(value, str) or len(value) > 20:
            raise ValueError('Cartão ou parcela inválida.')
        result[key] = value
    holder = row.get('holder', '')
    if not isinstance(holder, str) or len(holder) > 120:
        raise ValueError('Titular inválido.')
    result['holder'] = holder
    source = row.get('category_source', 'manual')
    if source not in ('manual', 'learned', 'suggested', 'unknown', 'legacy'):
        raise ValueError('Origem da categoria inválida.')
    result['category_source'] = source
    kind = row.get('kind', 'expense')
    if kind not in ('expense', 'income', 'transfer'):
        raise ValueError('Tipo de lançamento inválido.')
    if kind == 'income' and row['cents'] > 0:
        raise ValueError('Ganhos devem ter valor negativo (entrada).')
    result['kind'] = kind
    channel = payment_channel(row)
    if channel not in PAYMENT_CHANNELS:
        raise ValueError('Origem do pagamento inválida.')
    result['payment_channel'] = channel
    bank = row.get('bank', 'unspecified')
    if bank not in BANKS:
        raise ValueError('Banco inválido.')
    result['bank'] = bank
    return result


def check_people(members, shared=''):
    """1-6 distinct names; the optional shared group must not repeat a member."""
    if not isinstance(members, list) or not 1 <= len(members) <= MAX_PEOPLE:
        raise ValueError(f'Cadastre de 1 a {MAX_PEOPLE} pessoas.')
    clean = [m.strip() if isinstance(m, str) else '' for m in members]
    shared = shared.strip() if isinstance(shared, str) else ''
    names = clean + ([shared] if shared else [])
    if any(not n or len(n) > 30 for n in names):
        raise ValueError('Cada nome deve ter de 1 a 30 caracteres.')
    if len({n.casefold() for n in names}) != len(names):
        raise ValueError('Os nomes precisam ser diferentes entre si.')
    return clean, shared
