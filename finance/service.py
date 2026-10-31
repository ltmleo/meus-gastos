import hashlib
import secrets
import time
from pathlib import Path
from finance.domain import validate, payment_channel
from finance.classification import suggest, merchant_key, normalized, legacy_category, suggested_kind
from finance.ownership import same_holder
from finance.importers import IMPORTERS
from finance.importers.auto import parse_auto

class FinanceService:
    def __init__(self, repository):
        self.repository = repository
        self.previews = {}

    def preview(self, content, filename, provider='auto', month='', password=''):
        if provider != 'auto' and provider not in IMPORTERS:
            raise ValueError('Importador desconhecido.')
        fingerprint = hashlib.sha256(content).hexdigest()
        if any(x['fingerprint'] == fingerprint for x in self.repository.list()['imports']):
            raise ValueError('Este arquivo já foi importado.')
        if provider == 'auto':
            rows, warnings, metadata = parse_auto(content, Path(filename).name, month, password)
        elif provider == 'nubank':
            rows, warnings, metadata = IMPORTERS[provider].parse(content, Path(filename).suffix.lower(), month, password, Path(filename).name)
        else:
            rows, warnings, metadata = IMPORTERS[provider].parse(content, Path(filename).suffix.lower(), month, password)
        rules = self.repository.rules()
        history = self.repository.list()['transactions']
        holders = metadata.get('holders', [])
        members = self.repository.household()['members']
        people = self.repository.people()
        mappings = {}
        for index, holder in enumerate(holders):
            saved = rules['holders'].get(normalized(holder))
            if not saved:
                matches = {p for h,p in rules['holders'].items() if same_holder(h, holder)}
                saved = next(iter(matches)) if len(matches) == 1 else None
            # First reading: 1st card holder -> 1st person, 2nd -> 2nd (when the counts match).
            guess = members[index] if len(holders) <= len(members) else ''
            mappings[holder] = saved if saved in people else guess
        for row in rows:
            row['bank'] = metadata.get('provider') if metadata.get('provider') in ('santander', 'nubank') else 'unspecified'
            row['payment_channel'] = payment_channel(row)
            row['kind'] = suggested_kind(row['description'], row.get('kind', 'expense'), rules['own_accounts'], row['payment_channel'])
            suggestion = suggest(row['description'], rules['categories'], row['kind'], history)
            # Uncertain similarity is offered, never silently assigned on import.
            if suggestion['confidence'] == 'medium':
                suggestion['suggested_category'] = suggestion['category']
                suggestion['category'] = 'Outros'
                suggestion['category_source'] = 'unknown'
            row.update(suggestion)
            if row.get('holder'):
                row['person'] = mappings.get(row['holder']) or members[0]
            elif row.get('person') not in people:
                row['person'] = members[0]  # importers default to the first person
        metadata['holder_mapping'] = mappings
        if holders:
            warnings.append('Confira quem é cada titular do cartão: na primeira leitura, a sugestão segue a ordem das pessoas cadastradas. Sua escolha será lembrada nas próximas faturas.')
        self.previews = {k: v for k, v in self.previews.items() if v['expires'] > time.time()}
        token = secrets.token_urlsafe(24)
        self.previews[token] = dict(fingerprint=fingerprint, filename=Path(filename).name, expires=time.time()+3600)
        return dict(token=token, rows=rows, warnings=warnings, metadata=metadata)

    def confirm(self, token, rows, holder_mapping=None):
        preview = self.previews.get(token)
        if not preview or preview['expires'] < time.time():
            raise ValueError('Prévia expirada. Leia o arquivo novamente.')
        if not rows:
            raise ValueError('Selecione pelo menos um lançamento.')
        learned = {}
        for row in rows:
            if row.get('category_source') == 'manual':
                learned[row.get('kind', 'expense') + ':' + merchant_key(row['description'])] = row['category']
        holder_rules = {}
        for holder, person in (holder_mapping or {}).items():
            if person not in self.repository.people() or not isinstance(holder, str) or len(holder) > 120:
                raise ValueError('Associação de titular inválida.')
            holder_rules[normalized(holder)] = person
        people = self.repository.people()
        self.repository.save([validate(r, people) for r in rows], preview['fingerprint'], preview['filename'], learned, holder_rules)
        del self.previews[token]

    def save_manual(self, row, identifier=None, remember=False):
        existing = next((r for r in self.repository.list()['transactions'] if r['id'] == identifier), None)
        if identifier and not existing:
            raise ValueError('Lançamento não encontrado.')
        if existing:
            row = {**existing, **row}
        row = validate(row, self.repository.people())
        if not existing or any(row[k] != existing.get(k, 'expense' if k == 'kind' else '') for k in ('category', 'kind', 'description')):
            row['category_source'] = 'manual'
        rules = {row['kind'] + ':' + merchant_key(row['description']):row['category']} if remember else {}
        if identifier:
            self.repository.update(identifier, row, rules)
        else:
            self.repository.save([row], category_rules=rules)

    def classify(self, description, kind='expense', identifier=None):
        if not isinstance(description, str) or not description.strip() or len(description) > 500:
            raise ValueError('Informe uma descrição de até 500 caracteres.')
        if kind not in ('expense', 'income', 'transfer'):
            raise ValueError('Tipo inválido.')
        history = [r for r in self.repository.list()['transactions'] if r['id'] != identifier]
        return suggest(description, self.repository.rules()['categories'], kind, history)

    def classify_group(self, identifiers, category, kind, remember=False):
        if not isinstance(identifiers, list) or not identifiers or any(type(i) is not int for i in identifiers):
            raise ValueError('Selecione os lançamentos para classificar.')
        rows = [r for r in self.repository.list()['transactions'] if r['id'] in set(identifiers)]
        if len(rows) != len(set(identifiers)):
            raise ValueError('Um lançamento não está mais disponível. Atualize a página.')
        if len({merchant_key(r['description']) for r in rows}) != 1:
            raise ValueError('Classifique um destinatário ou estabelecimento por vez.')
        changes = [dict(validate(dict(r, category=category, kind=kind, category_source='manual'), self.repository.people()), id=r['id']) for r in rows]
        rules = {kind+':'+merchant_key(r['description']):category for r in rows} if remember else {}
        self.repository.classify_group(changes, rules)

    def review_categories(self):
        rules = self.repository.rules()
        learned = rules['categories']
        history = self.repository.list()['transactions']
        changes = []
        for row in history:
            if row['category_source'] == 'manual':
                continue
            if row['category_source'] == 'legacy' and row['category'] != legacy_category(row['description']):
                continue
            kind = suggested_kind(row['description'], row.get('kind', 'expense'), rules['own_accounts'], payment_channel(row))
            suggestion = suggest(row['description'], learned, kind, history)
            if suggestion['category'] != row['category'] or kind != row.get('kind', 'expense'):
                changes.append({**row, **suggestion, 'kind':kind, 'previous_kind':row.get('kind', 'expense'), 'previous_category':row['category']})
        return changes

    def bulk_update(self, identifiers, changes):
        allowed = {'category', 'person', 'kind', 'payment_channel', 'month'}
        if not isinstance(identifiers, list) or not identifiers or any(type(i) is not int for i in identifiers):
            raise ValueError('Selecione os lançamentos.')
        if not isinstance(changes, dict) or not changes or set(changes) - allowed:
            raise ValueError('Alteração inválida.')
        wanted = set(identifiers)
        rows = [r for r in self.repository.list()['transactions'] if r['id'] in wanted]
        if len(rows) != len(wanted):
            raise ValueError('Um lançamento não está mais disponível. Atualize a página.')
        updated = []
        for row in rows:
            merged = validate({**row, **changes}, self.repository.people())
            if 'category' in changes or 'kind' in changes:
                merged['category_source'] = 'manual'
            updated.append((row['id'], merged))
        for identifier, merged in updated:
            self.repository.update(identifier, merged)
        return len(updated)
