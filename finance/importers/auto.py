import io
from .nubank import NubankImporter, read_csv
from .santander import SantanderImporter


def parse_auto(content, filename, reference_month, password=''):
    if content.lstrip().startswith(b'%PDF-'):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(password):
            raise ValueError('PDF protegido: informe a senha correta.')
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        if 'SANTANDER' not in text.upper() and 'EXTRATO CONSOLIDADO INTELIGENTE' not in text.upper():
            raise ValueError('PDF não reconhecido. Para Nubank, use o CSV exportado da fatura ou da conta.')
        rows, warnings, metadata = SantanderImporter().parse_text(text, reference_month)
        metadata.update(provider='santander', detected_format='Santander · Extrato PDF' if metadata.get('source_type')=='statement' else 'Santander · Fatura PDF')
        return rows, warnings, metadata
    fields, _ = read_csv(content)
    if set(fields) in ({'DATE','TITLE','AMOUNT'}, {'DATA','VALOR','IDENTIFICADOR','DESCRICAO'}):
        return NubankImporter().parse(content, '.csv', reference_month, password, filename)
    if set(fields) == {'DATA','DESCRICAO','VALOR'}:
        rows, warnings, metadata = SantanderImporter().parse(content, '.csv', reference_month)
        metadata.update(provider='generic', detected_format='CSV padrão · data, descrição e valor')
        return rows, warnings, metadata
    raise ValueError('Formato não reconhecido. Use uma fatura/extrato Santander PDF, um CSV Nubank ou o CSV padrão data;descricao;valor.')
