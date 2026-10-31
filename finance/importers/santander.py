import csv
import io
import re
import unicodedata
from datetime import date
from finance.domain import money, category
from finance.ownership import canonical_holders

def transaction_date(value, month):
    value = value.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value).isoformat()
    parts = value.split('/')
    if len(parts) not in (2, 3):
        raise ValueError('Data não reconhecida: ' + value)
    day, mon = map(int, parts[:2])
    year = int(parts[2]) if len(parts) == 3 else int(month[:4]) - (mon > int(month[5:]))
    if year < 100:
        year += 2000
    return date(year, mon, day).isoformat()

class SantanderImporter:
    def parse(self, content, extension, reference_month, password=''):
        date.fromisoformat(reference_month + '-01')
        warnings = []
        records = []
        if extension == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted and not reader.decrypt(password):
                raise ValueError('PDF protegido: informe a senha correta.')
            return self.parse_text('\n'.join(page.extract_text() or '' for page in reader.pages), reference_month)
        elif extension == '.csv':
            try:
                text = content.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = content.decode('cp1252')
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=';,\t')
            except csv.Error:
                raise ValueError('CSV inválido. Use as colunas data, descricao e valor.')
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            def normalize(s):
                return ''.join(c for c in unicodedata.normalize('NFD', s.strip().lower()) if not unicodedata.combining(c))
            for number, row in enumerate(reader, 2):
                clean = {normalize(k): v for k, v in row.items() if k}
                if not all(k in clean for k in ('data', 'descricao', 'valor')):
                    raise ValueError('CSV deve conter as colunas data, descricao e valor.')
                records.append((clean['data'], clean['descricao'], clean['valor']))
        else:
            raise ValueError('Formato suportado: PDF ou CSV.')
        rows = []
        for d, description, amount in records:
            try:
                rows.append(dict(date=transaction_date(d, reference_month), month=reference_month, description=description.strip(), cents=money(amount), person='Eu', category=category(description)))
            except (ValueError, TypeError) as error:
                warnings.append(f'Não importado: {d} {description}: {error}')
        if not rows:
            raise ValueError('Nenhum lançamento reconhecido. Use o CSV modelo ou adapte o importador ao layout da sua fatura.')
        return rows, warnings, {}

    def parse_text(self, text, reference_month):
        if 'EXTRATO CONSOLIDADO INTELIGENTE' in text:
            from .statement import parse_statement
            rows, warnings, metadata = parse_statement(text, reference_month)
            metadata['provider'] = 'santander'
            return rows, warnings, metadata
        # Port of financas/app/src/santander.ts recovered from task history.
        # Text may be continuous: never depend on PDF line breaks.
        normalized = re.sub(r'\s+', ' ', text).strip()
        total = re.search(r'Total a Pagar\s*R\$\s*([\d.]+,\d{2})', normalized, re.I) or re.search(r'Saldo Desta Fatura\s*([\d.]+,\d{2})', normalized, re.I)
        due = re.search(r'Vencimento\s*(\d{2}/\d{2}/\d{4})', normalized, re.I)
        if not total or not due:
            raise ValueError('Não identificamos total e vencimento Santander. PDF digitalizado ou layout não suportado.')
        due_date = transaction_date(due[1], reference_month)
        month = due_date[:7]
        cards = list(re.finditer(r'(?:XXXX\s+XXXX\s+|\*{4}\s+\*{4}\s+)(\d{4})', normalized))
        owners = list(re.finditer(r"([A-ZÀ-Ü][A-ZÀ-Ü '.]{1,80}?)\s*-\s*\d{4}\s+(?:XXXX\s+XXXX|\*{4}\s+\*{4})\s+(\d{4})", normalized))
        aliases = canonical_holders([m[1].strip() for m in owners])
        holders = list(dict.fromkeys(aliases[m[1].strip()] for m in owners))
        # Take the first BRL amount, not the optional USD column; do not swallow
        # section headers while searching for the next date or amount.
        pattern = re.compile(r'(?<!\S)(?:\d+ )?(\d{2})/(\d{2}) ([^,]+?) (?:(\d{2}/\d{2}) )?(-?[\d.]+,\d{2})(?!\d)', re.I)
        rows, warnings = [], []
        for match in pattern.finditer(normalized):
            day, mon, description, installment, value = match.groups()
            if re.search(r'PAGAMENTO|COTAÇÃO|DEB\s+AUTOM\s+DE FATURA', description, re.I):
                continue
            if len(description) > 160 or re.search(r'Vencimento|Saldo Anterior|Total a Pagar|Compra Data|VALOR TOTAL', description, re.I):
                warnings.append('Trecho ambíguo ignorado. Confira a lista com a fatura original.')
                continue
            prior = [card for card in cards if card.start() < match.start()]
            if not prior or money(value) == 0:
                continue
            try:
                preceding_owners = [owner for owner in owners if owner.end() <= match.start()]
                owner = preceding_owners[-1] if preceding_owners else None
                holder = aliases[owner[1].strip()] if owner and owner[2] == prior[-1][1] else ''
                rows.append(dict(date=transaction_date(f'{day}/{mon}', month), month=month, description=description.strip(), cents=money(value), person='Eu', payment_channel='credit', holder=holder, category=category(description), card=prior[-1][1] if prior else '', installment=installment or ''))
                next_date = re.search(r'(?<!\S)(?:\d+ )?\d{2}/\d{2} ', normalized[match.end():])
                end = match.end() + next_date.start() if next_date else len(normalized)
                for fee in re.finditer(r'IOF DESPESA NO EXTERIOR\s+([\d.]+,\d{2})', normalized[match.end():end], re.I):
                    rows.append(dict(rows[-1], description='IOF · '+description.strip(), cents=money(fee[1]), category='Outros', installment=''))
            except ValueError:
                warnings.append('Data não reconhecida em um lançamento; confira a fatura.')
        if not rows:
            raise ValueError('Nenhum lançamento reconhecido no PDF. O layout precisa ser ajustado.')
        warnings.insert(0, 'Revise os lançamentos e responsáveis. A soma pode diferir do total por pagamentos, encargos ou linhas não reconhecidas. A parcela exibida corresponde apenas à cobrança desta fatura.')
        return rows, warnings, dict(provider='santander', total_cents=money(total[1]), due_date=due_date, month=month, holders=holders)
