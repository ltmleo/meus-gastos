"""Nubank CSV exports: credit-card invoice and account statement."""
import csv
import io
import re
from datetime import date
from finance.domain import money, category
from finance.classification import normalized


def read_csv(content):
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = content.decode('cp1252')
    if '\x00' in text:
        raise ValueError('Arquivo não reconhecido como CSV de texto.')
    first = next((line for line in text.splitlines() if line.strip()), '')
    delimiter = max((',', ';', '\t'), key=first.count)
    reader = csv.reader(io.StringIO(text.lstrip('\r\n')), delimiter=delimiter, strict=True)
    try:
        fields = [normalized(v) for v in next(reader, [])]
        if not fields or len(fields) != len(set(fields)):
            raise ValueError('Cabeçalho CSV ausente ou repetido.')
        records = []
        for values in reader:
            if not values or not any(v.strip() for v in values):
                continue
            if len(values) != len(fields):
                raise ValueError(f'CSV inválido na linha {reader.line_num}: quantidade de colunas diferente do cabeçalho.')
            records.append((reader.line_num, dict(zip(fields, values))))
        return fields, records
    except csv.Error as error:
        raise ValueError('CSV malformado: confira aspas e separadores.') from error


def statement_description(description):
    match = re.match(r'Transfer[êe]ncia\s+(enviada|recebida)(?:\s+pelo\s+Pix)?\s*-\s*(.+)', description, re.I | re.S)
    if not match:
        return re.sub(r'\s+', ' ', description).strip()
    # Bank/CPF details are not the merchant: retain the full recipient name.
    name = re.split(r'\s+-\s+(?=[•*\d])', match[2], maxsplit=1)[0]
    name = re.sub(r'\s+', ' ', name).strip()
    return ('PIX ENVIADO ' if match[1].lower() == 'enviada' else 'PIX RECEBIDO ') + name


class NubankImporter:
    def parse(self, content, extension, reference_month, password='', filename=''):
        if extension != '.csv':
            raise ValueError('Use o CSV da fatura ou do extrato Nubank. PDF Nubank ainda não é suportado.')
        fields, records = read_csv(content)
        invoice = set(fields) == {'DATE', 'TITLE', 'AMOUNT'}
        statement = set(fields) == {'DATA', 'VALOR', 'IDENTIFICADOR', 'DESCRICAO'}
        if not invoice and not statement:
            raise ValueError('Cabeçalho Nubank não reconhecido.')
        date.fromisoformat(reference_month+'-01')
        warnings = []
        month = reference_month
        if invoice:
            match = re.fullmatch(r'Nubank_(\d{4}-\d{2}-\d{2})(?:\s*\(\d+\))?\.csv', filename, re.I)
            if match:
                month = date.fromisoformat(match[1]).isoformat()[:7]
                warnings.append('Mês da fatura obtido do nome original do arquivo. Confira o mês antes de salvar.')
            else:
                warnings.append('Este CSV não informa o vencimento. Usamos o mês de referência escolhido; confirme se corresponde à fatura.')
        rows, identifiers, payment_total, payment_count = [], set(), 0, 0
        source_total = 0
        for number, record in records:
            try:
                if invoice:
                    when = date.fromisoformat(record['DATE'].strip()).isoformat()
                    description = record['TITLE'].strip()
                    cents = money(record['AMOUNT'])
                else:
                    from .santander import transaction_date
                    when = transaction_date(record['DATA'], reference_month)
                    description = statement_description(record['DESCRICAO'].strip())
                    cents = -money(record['VALOR'])
                    identifier = record['IDENTIFICADOR'].strip()
                    if not identifier or identifier in identifiers:
                        raise ValueError('Identificador de movimentação ausente ou repetido.')
                    identifiers.add(identifier)
                source_total += cents
                if not description or len(description) > 500:
                    raise ValueError('Descrição ausente ou muito longa.')
                title = normalized(description)
                if invoice and title == 'PAGAMENTO RECEBIDO':
                    if cents >= 0:
                        raise ValueError('Pagamento recebido com sinal inesperado.')
                    payment_count += 1
                    payment_total += cents
                    continue
                kind = 'expense' if invoice or cents >= 0 else 'income'
                if statement and (title == 'PAGAMENTO DE FATURA' or re.match(r'^(?:APLICACAO|RESGATE|TRANSFERENCIA ENTRE CONTAS PROPRIAS)\b', title)):
                    kind = 'transfer'
                installment = ''
                if invoice:
                    match = re.search(r'\s*-\s*Parcela\s+(\d{1,3})/(\d{1,3})\s*$', description, re.I)
                    if match:
                        if not 1 <= int(match[1]) <= int(match[2]):
                            raise ValueError('Parcela inválida.')
                        installment = f'{match[1]}/{match[2]}'
                        description = description[:match.start()].strip()
                rows.append(dict(date=when, month=month if invoice else when[:7], description=description,
                                 cents=cents, person='Eu', kind=kind, category=category(description),
                                 payment_channel='credit' if invoice else 'account', installment=installment))
            except (ValueError, TypeError) as error:
                raise ValueError(f'Não foi possível importar a linha {number}: {error}') from error
        if not rows:
            raise ValueError('Nenhum lançamento importável no arquivo Nubank.')
        if invoice:
            warnings.append(f'{payment_count} pagamento(s) recebido(s) excluído(s), evitando duplicar o pagamento da conta. Estornos e IOF foram preservados. O CSV não informa um total oficial da fatura.')
        else:
            warnings.append('Entradas e saídas são lidas pelo sinal do CSV. Revise a finalidade dos PIX; recebimentos não identificados ficam em Outras receitas. O CSV não contém saldo inicial ou final.')
        metadata = dict(provider='nubank', source_type='invoice' if invoice else 'statement',
                        detected_format='Nubank · Fatura CSV' if invoice else 'Nubank · Extrato CSV',
                        month=month if invoice else max(r['month'] for r in rows),
                        parsed_total_cents=sum(r['cents'] for r in rows), source_total_cents=source_total,
                        excluded_payment_cents=payment_total, excluded_payment_count=payment_count,
                        start_date=min(r['date'] for r in rows), end_date=max(r['date'] for r in rows))
        if statement:
            metadata.update(credits_cents=-sum(min(r['cents'],0) for r in rows),
                            debits_cents=sum(max(r['cents'],0) for r in rows))
        return rows, warnings, metadata
