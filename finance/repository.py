import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from finance.domain import payment_channel


class Locked(Exception):
    """The database is encrypted and has not been unlocked."""


SCHEMA = '''
    CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
        filename TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY, import_id INTEGER REFERENCES imports(id) ON DELETE CASCADE,
        date TEXT NOT NULL, month TEXT NOT NULL, description TEXT NOT NULL,
        cents INTEGER NOT NULL, person TEXT NOT NULL, category TEXT NOT NULL,
        card TEXT NOT NULL DEFAULT '', installment TEXT NOT NULL DEFAULT '');
    CREATE INDEX IF NOT EXISTS transactions_month ON transactions(month);
    CREATE TABLE IF NOT EXISTS category_rules (merchant TEXT PRIMARY KEY, category TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS holder_rules (holder TEXT PRIMARY KEY, person TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS own_accounts (name TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS budgets (category TEXT PRIMARY KEY, cents INTEGER NOT NULL CHECK (cents > 0));
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''


def migrate(db):
    db.executescript(SCHEMA)
    columns = {r['name'] for r in db.execute('PRAGMA table_info(transactions)')}
    for name, default in (('holder', ''), ('category_source', 'legacy'), ('kind', 'expense')):
        if name not in columns:
            db.execute(f"ALTER TABLE transactions ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")
    if 'payment_channel' not in columns:
        db.execute("ALTER TABLE transactions ADD COLUMN payment_channel TEXT NOT NULL DEFAULT 'unspecified'")
        for record in db.execute('SELECT * FROM transactions').fetchall():
            row = dict(record)
            row.pop('payment_channel')
            db.execute('UPDATE transactions SET payment_channel=? WHERE id=?', (payment_channel(row), row['id']))
    if 'bank' not in columns:
        db.execute("ALTER TABLE transactions ADD COLUMN bank TEXT NOT NULL DEFAULT 'unspecified'")
    # Databases from before configurable people keep exactly the names already in use.
    if not db.execute("SELECT 1 FROM settings WHERE key='people'").fetchone() and db.execute('SELECT 1 FROM transactions LIMIT 1').fetchone():
        db.execute("INSERT INTO settings VALUES ('people', ?)", (json.dumps(dict(members=['Eu', 'Esposa'], shared='Compartilhado')),))
    db.execute('PRAGMA user_version=7')


class Repository:
    """SQLite storage. Plain mode uses the file at `path`; encrypted mode keeps the
    database only in memory and hands every committed change to `persist`."""

    def __init__(self, path, locked=False):
        self.path = str(path)
        self._memory = None
        self._persist = None
        self._lock = threading.RLock()
        self.locked = locked
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if not locked:
            with self.connect() as db:
                migrate(db)

    @property
    def encrypted(self):
        return self._memory is not None or self.locked

    def attach(self, data, persist):
        """Switch to an in-memory database built from decrypted bytes."""
        db = sqlite3.connect(':memory:', check_same_thread=False)
        if data:
            db.deserialize(data)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        with self._lock:
            self._memory, self._persist, self.locked = db, persist, False
            with self.connect() as conn:
                migrate(conn)

    def detach(self):
        """Forget the decrypted database (lock)."""
        with self._lock:
            if self._memory is not None:
                self._memory.close()
            self._memory, self._persist, self.locked = None, None, True

    def snapshot(self):
        """Current database as bytes (for encryption, backup or leaving encrypted mode)."""
        with self._lock:
            if self._memory is not None:
                return self._memory.serialize()
            if self.locked:
                raise Locked()
            source = sqlite3.connect(self.path)
            target = sqlite3.connect(':memory:')
            try:
                source.backup(target)
                return target.serialize()
            finally:
                source.close()
                target.close()

    @contextmanager
    def connect(self):
        if self.locked:
            raise Locked()
        if self._memory is not None:
            with self._lock:
                if self._memory is None:
                    raise Locked()
                db = self._memory
                before = db.total_changes
                with db:
                    yield db
                if db.total_changes != before:
                    self._persist(db.serialize())
            return
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            return dict(transactions=[dict(r) for r in db.execute('SELECT * FROM transactions ORDER BY date DESC, id DESC')], imports=[dict(r) for r in db.execute('SELECT * FROM imports ORDER BY id DESC')])

    def save(self, rows, fingerprint=None, filename=None, category_rules=None, holder_rules=None):
        with self.connect() as db:
            import_id = None
            if fingerprint:
                try:
                    import_id = db.execute('INSERT INTO imports(fingerprint,filename) VALUES (?,?)', (fingerprint, filename)).lastrowid
                except sqlite3.IntegrityError:
                    raise ValueError('Este arquivo já foi importado. Exclua a importação anterior para refazer.')
            db.executemany('INSERT INTO transactions(import_id,date,month,description,cents,person,category,card,installment,holder,category_source,kind,payment_channel,bank) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [(import_id, *[(payment_channel(r) if k == 'payment_channel' else r.get(k, 'expense' if k == 'kind' else 'unspecified' if k == 'bank' else '')) for k in ('date', 'month', 'description', 'cents', 'person', 'category', 'card', 'installment', 'holder', 'category_source', 'kind', 'payment_channel', 'bank')]) for r in rows])
            self._rules(db, category_rules, holder_rules)

    def update(self, identifier, row, category_rules=None):
        with self.connect() as db:
            db.execute('UPDATE transactions SET date=?,month=?,description=?,cents=?,person=?,category=?,card=?,installment=?,holder=?,category_source=?,kind=?,payment_channel=?,bank=? WHERE id=?', (*[(payment_channel(row) if k == 'payment_channel' else row.get(k, 'expense' if k == 'kind' else 'unspecified' if k == 'bank' else '')) for k in ('date','month','description','cents','person','category','card','installment','holder','category_source','kind','payment_channel','bank')], identifier))
            self._rules(db, category_rules, None)

    @staticmethod
    def _rules(db, category_rules, holder_rules):
        db.executemany('INSERT OR REPLACE INTO category_rules VALUES (?,?)', list((category_rules or {}).items()))
        db.executemany('INSERT OR REPLACE INTO holder_rules VALUES (?,?)', list((holder_rules or {}).items()))

    def rules(self):
        with self.connect() as db:
            return dict(categories=dict(db.execute('SELECT merchant,category FROM category_rules').fetchall()), holders=dict(db.execute('SELECT holder,person FROM holder_rules').fetchall()), own_accounts=[r[0] for r in db.execute('SELECT name FROM own_accounts')])

    def remember_own_account(self, name):
        from finance.classification import normalized, own_account_pix
        name = normalized(name)
        if not name:
            raise ValueError('Nome da conta obrigatório.')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO own_accounts(name) VALUES (?)', (name,))
            ids = [r['id'] for r in db.execute('SELECT * FROM transactions').fetchall()
                   if r['payment_channel'] != 'credit' and own_account_pix(r['description'], [name])]
            db.executemany("UPDATE transactions SET kind='transfer',category='Transferências',category_source='manual' WHERE id=?", [(i,) for i in ids])
            return ids

    def apply_suggestions(self, changes):
        with self.connect() as db:
            for row in changes:
                db.execute('UPDATE transactions SET category=?,category_source=?,kind=? WHERE id=?', (row['category'],row['category_source'],row.get('kind', 'expense'),row['id']))

    def classify_group(self, rows, rules):
        with self.connect() as db:
            db.executemany("UPDATE transactions SET category=?,category_source='manual',kind=? WHERE id=?",
                           [(r['category'],r['kind'],r['id']) for r in rows])
            self._rules(db, rules, None)

    def household(self):
        """{'members': [...], 'shared': str, 'configured': bool}."""
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='people'").fetchone()
        if not row:  # until the welcome wizard runs, the original household applies
            return dict(members=['Eu', 'Esposa'], shared='Compartilhado', configured=False)
        value = json.loads(row['value'])
        return dict(members=value['members'], shared=value.get('shared', ''), configured=True)

    def people(self):
        house = self.household()
        return house['members'] + ([house['shared']] if house['shared'] else [])

    def set_household(self, members, shared, renames=None):
        """Save names; renames {old: new} move existing transactions and card holders."""
        old_people = self.people()
        new_people = members + ([shared] if shared else [])
        renames = {old: new for old, new in (renames or {}).items() if old != new}
        if any(old not in old_people or new not in new_people for old, new in renames.items()):
            raise ValueError('Renomeação inválida.')
        with self.connect() as db:
            for old, new in renames.items():
                db.execute('UPDATE transactions SET person=? WHERE person=?', (new, old))
                db.execute('UPDATE holder_rules SET person=? WHERE person=?', (new, old))
            removed = [p for p in old_people if p not in new_people and p not in renames]
            for person in removed:
                count = db.execute('SELECT COUNT(*) FROM transactions WHERE person=?', (person,)).fetchone()[0]
                if count:
                    raise ValueError(f'{person} tem {count} lançamentos. Mova-os para outra pessoa antes de remover.')
                db.execute('DELETE FROM holder_rules WHERE person=?', (person,))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('people', ?)", (json.dumps(dict(members=members, shared=shared)),))

    def budgets(self):
        with self.connect() as db:
            return dict(db.execute('SELECT category,cents FROM budgets').fetchall())

    def set_budgets(self, values, replace=False):
        with self.connect() as db:
            if replace:
                db.execute('DELETE FROM budgets')
            for category, cents in values.items():
                if cents:
                    db.execute('INSERT OR REPLACE INTO budgets VALUES (?,?)', (category, cents))
                else:
                    db.execute('DELETE FROM budgets WHERE category=?', (category,))

    def forget_rule(self, merchant):
        with self.connect() as db:
            db.execute('DELETE FROM category_rules WHERE merchant=?', (merchant,))

    def forget_own_account(self, name):
        with self.connect() as db:
            db.execute('DELETE FROM own_accounts WHERE name=?', (name,))

    def delete(self, kind, identifier):
        table = 'imports' if kind == 'imports' else 'transactions'
        with self.connect() as db:
            db.execute(f'DELETE FROM {table} WHERE id=?', (identifier,))
