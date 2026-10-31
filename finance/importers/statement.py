"""Santander consolidated statement: current-account movements only."""
import re
from finance.domain import money, category
from finance.classification import suggested_kind
from .santander import transaction_date


def parse_statement(text, reference_month):
    months = 'janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro'.split()
    period = re.search(r'(' + '|'.join(months) + r')/(\d{4})', text, re.I)
    if not period:
        raise ValueError('Mês do extrato não identificado.')
    month = f'{period[2]}-{months.index(period[1].lower())+1:02d}'
    amount = r'[\d.]+,\d{2}'
    balances = list(re.finditer(r'SALDO EM (\d{2}/\d{2})\s+(' + amount + r')(-?)', text))
    if len(balances) < 2:
        raise ValueError('Movimentação da conta corrente não identificada.')
    section = text[balances[0].end():balances[1].start()]
    # Remove repeated page furniture before joining wrapped descriptions.
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    lines = [line for line in lines if not re.match(
        r'EXTRATO CONSOLIDADO|Extrato_PF_|BALP_|Pagina:|Data Descri|(?:' + '|'.join(months) + r')/\d{4}', line, re.I)]
    section = ' '.join(lines)
    pattern = re.compile(r'(?:(\d{2}/\d{2})\s+)?(.+?)\s+(?:\d+|-)\s+(' + amount + r')(-?)(?:\s+(' + amount + r')-?)?(?=\s|$)')
    rows, current_date, end = [], None, 0
    for match in pattern.finditer(section):
        if section[end:match.start()].strip():
            raise ValueError('Trecho da movimentação não reconhecido.')
        day, description, value, debit, _ = match.groups()
        if day:
            current_date = transaction_date(day, month)
        if not current_date:
            raise ValueError('Data da movimentação não identificada.')
        cents = money(value) * (1 if debit else -1)
        kind = 'expense' if debit else 'income'
        if re.search(r'FAT\.?\s*CARTAO|VENCIMENTO CDB/RDB|RESGATE|APLICACAO(?! AUTOMATICA)', description, re.I):
            kind = 'transfer'
        kind = suggested_kind(description, kind)
        rows.append(dict(date=current_date, month=month, description=description.strip(), cents=cents,
                         kind=kind, payment_channel='account', category=category(description), person='Eu'))
        end = match.end()
    if not rows or section[end:].strip():
        raise ValueError('Não foi possível ler toda a movimentação do extrato.')
    credits = -sum(min(r['cents'], 0) for r in rows)
    debits = sum(max(r['cents'], 0) for r in rows)
    opening, closing = [money(m[2]) * (-1 if m[3] else 1) for m in (balances[0], balances[1])]
    # Fail closed: never present a partially read statement as complete.
    totals = re.findall(r'Total de [^\n]+?\s+(' + amount + r')', text)
    if closing != opening + credits - debits or len(totals) < 2 or [credits, debits] != [money(v) for v in totals[:2]]:
        raise ValueError('A movimentação não confere com os totais e saldos do extrato. Layout não suportado.')
    return rows, ['Conta corrente apenas: saldos, comprovantes repetidos, agendamentos e posições de investimentos não são lançamentos. Pagamento de cartão e resgate de CDB são transferências, fora dos gastos e ganhos. Revise os PIX: podem ser transferências entre contas próprias. Entradas usam valor negativo; saídas, positivo.'], dict(
        source_type='statement', month=month, credits_cents=credits, debits_cents=debits,
        opening_cents=opening, closing_cents=closing)
