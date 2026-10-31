"""Local, explainable suggestions. User rules take precedence over keywords."""
import re
import unicodedata
from difflib import SequenceMatcher

def normalized(value):
    plain = ''.join(c for c in unicodedata.normalize('NFD', value.upper()) if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', plain).strip()

def merchant_key(description):
    text = normalized(description)
    text = re.sub(r'^\d{2} \d{2}(?: \d{4})? ', '', text)
    text = re.sub(r'^(?:PIX (?:ENVIADO|RECEBIDO)|PAGAMENTO DE BOLETO(?: OUTROS BANCOS)?|COMPRA CARTAO DEB MC \d{2} \d{2})\s+', '', text)
    return re.sub(r'^(?:MP|DL|HNA|PAG|PAGSEGURO)\s+', '', text)


def own_account_pix(description, names):
    text = re.sub(r'^\d{2} \d{2}(?: \d{4})? ', '', normalized(description))
    match = re.fullmatch(r'PIX (?:ENVIADO|RECEBIDO) (.+)', text)
    return bool(match and match[1] in names)


def suggested_kind(description, kind='expense', own_accounts=None, channel='account'):
    if channel != 'credit' and own_account_pix(description, own_accounts or []):
        return 'transfer'
    text = normalized(description)
    if re.search(r'PAGAMENTO CARTAO CREDITO|DEBITO AUT FAT CARTAO|VENCIMENTO CDB RDB|RESGATE P C C', text):
        return 'transfer'
    return kind

def legacy_category(description):
    """Original defaults, only to distinguish old suggestions from user edits."""
    text = description.lower()
    for name, words in {'Mercado': ('mercado', 'supermerc', 'atacada'), 'Alimentação': ('restaurante', 'ifood', 'padaria'), 'Transporte': ('uber', 'posto', '99app'), 'Saúde': ('farmacia', 'drogaria'), 'Lazer': ('netflix', 'spotify', 'cinema')}.items():
        if any(word in text for word in words):
            return name
    return 'Outros'

# Specific merchants before broad words; Mercado Livre is shopping, not groceries.
RULES = (
    ('Transporte', ('BORRACH',)),
    ('Mercado', ('ADEGA', 'BEBIDAS', 'EMPORIO')),
    ('Viagens', ('GOL LINHAS', 'LATAM', 'AZUL LINHAS', 'EASYHOTEL', 'AIRBNB', 'BOOKING', 'HOTEL', 'POUSADA')),
    ('Casa e decoração', ('COLCHOES', 'MOVEIS', 'DECORACAO', 'TOK STOK', 'LEROY MERLIN')),
    ('Financiamentos', ('FINANCIAMENTO', 'BANCO RCI', 'BV FINANCEIRA', 'AYMORE', 'CREDITAS', 'CAIXA HABITACAO', 'CONSORCIO')),
    ('Doações', ('DOACAO', 'PAROQUIA')),
    ('Compras', ('AMAZONMKTPLC',)),
    ('Pets', ('AGROPET',)),
    ('Transporte', ('PARKING', 'BORRACHARIA')),
    ('Vestuário', ('TNG', 'VESTUA')),
    ('Mercado', ('CASA DE CARNES', 'ACOUGUE', 'QUEIJOS')),
    ('Alimentação', ('IFD', 'PANIFICADORA', 'PASTELARIA', 'PATISSERIE', 'LANCHES', 'CANTINAS', 'RESTAUR', 'PUB')),
    ('Taxas e encargos', ('IOF', 'ANUIDADE', 'JUROS', 'ENCARGOS', 'TARIFA')),
    ('Compras', ('MERCADOLIVRE', 'MERCADO LIVRE', 'AMAZON', 'SHOPEE', 'TIKTOK SHOP', 'HAVAN', 'MAGALU', 'MAGAZINE LUIZA', 'CASAS BAHIA', 'ALIEXPRESS')),
    ('Beleza e cuidados', ('OBOTICARIO', 'BOTICARIO', 'EPOCA COSMETICOS', 'SEPHORA', 'SALAO', 'BARBEARIA', 'COSMETICOS', 'ESMALTERIA')),
    ('Bebê e crianças', ('BABY', 'BEBE', 'FRALDAS')),
    ('Pets', ('PETSHOP', 'PET SHOP', 'PETZ', 'COBASI', 'VETERINAR')),
    ('Seguros', ('SEGURO', 'SEGURADORA', 'PORTO SEGURO')),
    ('Saúde', ('DROGARIA', 'DROGASIL', 'DROGA RAIA', 'FARMACIA', 'DENTAL', 'DENTISTA', 'CLINICA', 'HOSPITAL', 'LABORATORIO', 'WELLHUB', 'ACADEMIA')),
    ('Transporte', ('UBER', '99APP', 'POSTO', 'SHELL', 'IPIRANGA', 'PETROBRAS', 'ABASTECE', 'SEM PARAR', 'ZUL', 'ESTACIONAMENTO', 'PEDAGIO')),
    ('Educação', ('PREPLY', 'UDEMY', 'COURSERA', 'ESCOLA', 'CURSO', 'FACULDADE', 'LIVRARIA')),
    ('Assinaturas', ('NETFLIX', 'SPOTIFY', 'YOUTUBE', 'OPENAI', 'CHATGPT', 'DISNEY', 'ICLOUD', 'GOOGLE ONE')),
    ('Vestuário', ('BERSHKA', 'PLIE', 'RENNER', 'RIACHUELO', 'ZARA', 'SHEIN', 'CALCADOS', 'VANS')),
    ('Mercado', ('MERCADO', 'SUPERMERCADO', 'SUPERMERCADOS', 'SUPERMERC', 'ATACADAO', 'ASSAI', 'CARREFOUR', 'SONDA', 'OXXO', 'BANCA DE FRUTAS', 'HORTIFRUTI', 'SAMS CLUB', 'CONVENIENCIA')),
    ('Alimentação', ('RESTAURANTE', 'IFOOD', 'PADARIA', 'CAFE', 'SALGADARIA', 'PIZZARIA', 'LANCHONETE', 'BAR', 'BURGER', 'SUSHI', 'CHURRASCARIA', 'PICANHA', 'BRASEIRO', 'SORVETERIA', 'MACARRONADA', 'CULINARIA', 'MILKY MOO')),
    ('Moradia', ('ALUGUEL', 'CONDOMINIO', 'ENERGIA', 'CPFL', 'ENEL', 'CEMIG', 'LIGHT SA', 'COPEL', 'CELESC', 'EQUATORIAL', 'NEOENERGIA', 'COELBA', 'SABESP', 'COPASA', 'SANEPAR', 'CEDAE', 'EMBASA', 'COMGAS', 'NATURGY', 'INTERNET', 'CONTA VIVO', 'CLARO', 'TIM ', 'OI FIBRA')),
    ('Lazer', ('CINEMA', 'TEATRO', 'INGRESSO', 'PARQUE', 'STEAM', 'PLAYSTATION', 'XBOX')),
)

def _rule_suggestion(description, learned=None, kind='expense'):
    key = merchant_key(description)
    # Keep legacy rules working while new rules distinguish income and expenses.
    learned_key = kind + ':' + key
    legacy_key = re.sub(r'^(?:MP|DL|HNA|PAG|PAGSEGURO)\s+', '', normalized(description))
    match = next((k for k in (learned_key, legacy_key, key) if learned and k in learned), None)
    if match is not None:
        return dict(category=learned[match], category_source='learned', category_reason='Sua regra para este estabelecimento')
    text = ' ' + normalized(description) + ' '
    if kind == 'income':
        if re.search(r'LIQUIDO DE VENCIMENTO|SALARIO|PROVENTOS', text):
            name, reason = 'Salário', 'Crédito identificado como salário ou proventos'
        elif re.search(r'REMUNERACAO|RENDIMENTO|JUROS', text):
            name, reason = 'Rendimentos', 'Remuneração creditada; não inclui o principal de resgates'
        else:
            return dict(category='Outras receitas', category_source='unknown', category_reason='Origem da entrada a confirmar; PIX pode ser reembolso ou transferência própria')
        return dict(category=name, category_source='suggested', category_reason=reason)
    if kind == 'transfer':
        name = 'Pagamento de cartão' if re.search(r'FAT CARTAO|PAGAMENTO CARTAO|PAGAMENTO DE FATURA', text) else 'Investimentos' if re.search(r'CDB|RDB|RESGATE|APLICACAO', text) else 'Transferências'
        return dict(category=name, category_source='suggested', category_reason='Movimentação fora dos totais de gastos e ganhos')
    # A fee retains its nature even when its description contains a merchant.
    if re.search(r'\b(?:IOF|ANUIDADE|JUROS|ENCARGOS|TARIFA)\b', text):
        return dict(category='Taxas e encargos', category_source='suggested', category_reason='Encargo identificado antes do nome do estabelecimento')
    for category, words in RULES:
        for word in words:
            if ' '+word+' ' in text:
                return dict(category=category, category_source='suggested', category_reason='Reconhecido: '+word.title())
    return dict(category='Outros', category_source='unknown', category_reason='Estabelecimento não reconhecido; revise a categoria')


def suggest(description, learned=None, kind='expense', history=None):
    """Explainable local classifier; similarity never authorizes bulk changes."""
    result = _rule_suggestion(description, learned, kind)
    key = merchant_key(description)
    examples = {}
    for row in history or []:
        if row.get('category_source') == 'manual' and row.get('kind', 'expense') == kind:
            examples.setdefault(merchant_key(row['description']), set()).add(row['category'])
    if result['category_source'] != 'learned' and key in examples:
        categories = examples[key]
        if len(categories) == 1:
            result = dict(category=next(iter(categories)), category_source='learned',
                          category_reason='Mesma descrição de um lançamento que você classificou')
        else:
            return dict(category='Outras receitas' if kind == 'income' else 'Outros', category_source='unknown',
                        category_reason='Há classificações manuais diferentes para este estabelecimento; escolha a categoria',
                        confidence='low', alternatives=sorted(categories), needs_review=True)
    confidence = 'low' if result['category_source'] == 'unknown' else 'high'
    # Do not extrapolate between people or payment intermediaries.
    ambiguous = re.search(r'\b(?:PIX|PJBANK|WISE|PAGAMENTO DE BOLETO)\b', normalized(description))
    alternatives = []
    if confidence == 'low' and kind == 'expense' and not ambiguous:
        candidates = []
        generic = {'DE', 'DA', 'DO', 'LTDA', 'COMERCIO', 'LOJA', 'SA', 'E'}
        tokens = set(key.split()) - generic
        for merchant, categories in examples.items():
            shared = tokens & (set(merchant.split()) - generic)
            score = SequenceMatcher(None, key, merchant).ratio()
            if len(categories) == 1 and len(shared) >= 2 and score >= .88:
                candidates.append((score, merchant, next(iter(categories))))
        if candidates:
            candidates.sort(reverse=True)
            alternatives = sorted({c[2] for c in candidates})
            if len(alternatives) == 1:
                result = dict(category=candidates[0][2], category_source='suggested',
                              category_reason='Descrição semelhante a '+candidates[0][1]+'. Confira antes de usar.')
                confidence = 'medium'
    return dict(**result, confidence=confidence, alternatives=alternatives, needs_review=confidence!='high')
