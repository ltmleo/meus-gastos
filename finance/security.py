"""Access control and encryption at rest for the local app.

Without a password the app behaves as before (open on 127.0.0.1). With a
password the database lives only in an encrypted vault file; the decrypted copy
exists in memory while unlocked, and every API call needs a session cookie.
"""
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from finance.repository import Repository
from finance.vault import Vault, WrongSecret, check_password, wipe

SESSION_COOKIE = 'meusgastos_sid'
AUTO_LOCK_CHOICES = (0, 5, 15, 30, 60)  # minutes; 0 = never


class Security:
    def __init__(self, db_path, repository=None):
        self.db_path = Path(db_path)
        self.vault_path = self.db_path.with_suffix('.cofre')
        self.vault = None
        self.sessions = {}
        self.print_tokens = {}
        self.failures = 0
        self.blocked_until = 0.0
        self.last_activity = time.time()
        self._lock = threading.RLock()
        protected = Vault.exists(self.vault_path)
        self.repository = repository or Repository(self.db_path, locked=protected)
        self._stop = threading.Event()
        threading.Thread(target=self._watch_idle, daemon=True).start()

    # --- state -----------------------------------------------------------------
    @property
    def protected(self):
        return Vault.exists(self.vault_path)

    @property
    def locked(self):
        return self.repository.locked

    @property
    def auto_lock(self):
        header = self.vault.header if self.vault else None
        return (header or {}).get('settings', {}).get('auto_lock', 15)

    def status(self):
        return dict(protected=self.protected, locked=self.locked, auto_lock=self.auto_lock if self.vault else None,
                    plaintext_leftover=self.protected and self.db_path.is_file(),
                    retry_in=max(0, round(self.blocked_until - time.time())))

    def _persist(self, data):
        with self._lock:
            if self.vault:
                self.vault.save(data)

    # --- sessions ----------------------------------------------------------------
    def new_session(self):
        sid = secrets.token_urlsafe(32)
        self.sessions[sid] = time.time()
        self.touch()
        return sid

    def valid_session(self, sid):
        return bool(sid) and sid in self.sessions and not self.locked

    def touch(self):
        self.last_activity = time.time()

    def new_print_token(self):
        token = secrets.token_urlsafe(24)
        self.print_tokens = {t: exp for t, exp in self.print_tokens.items() if exp > time.time()}
        self.print_tokens[token] = time.time() + 120
        return token

    def valid_print_token(self, token):
        return bool(token) and self.print_tokens.get(token, 0) > time.time() and not self.locked

    def drop_print_token(self, token):
        self.print_tokens.pop(token, None)

    # --- unlock / lock -----------------------------------------------------------
    def unlock(self, password=None, recovery=None):
        with self._lock:
            wait = self.blocked_until - time.time()
            if wait > 0:
                raise PermissionError(f'Muitas tentativas. Aguarde {int(wait) + 1} segundos.')
            try:
                vault, data = Vault.open(self.vault_path, password=password, recovery=recovery)
            except WrongSecret:
                self.failures += 1
                if self.failures >= 3:  # 3rd error onwards: 2, 4, 8 ... up to 5 minutes
                    self.blocked_until = time.time() + min(300, 2 ** (self.failures - 2))
                raise
            self.failures, self.blocked_until = 0, 0.0
            self.vault = vault
            self.repository.attach(data, self._persist)
            return self.new_session()

    def lock(self):
        with self._lock:
            if not self.protected:
                return
            self.repository.detach()
            self.vault = None
            self.sessions.clear()
            self.print_tokens.clear()

    def check_idle(self, now=None):
        minutes = self.auto_lock
        if self.vault and minutes and (now or time.time()) - self.last_activity > minutes * 60:
            self.lock()
            return True
        return False

    def _watch_idle(self):
        while not self._stop.wait(20):
            self.check_idle()

    # --- configuration -------------------------------------------------------------
    def enable(self, password):
        """Encrypt the current database and remove the plain file. Returns (session, recovery code)."""
        with self._lock:
            if self.protected:
                raise ValueError('O banco já está protegido.')
            check_password(password)
            data = self.repository.snapshot()
            self.vault, recovery = Vault.create(self.vault_path, password, data, settings=dict(auto_lock=15))
            Vault.open(self.vault_path, password=password)  # prove it decrypts before deleting anything
            self.repository.attach(data, self._persist)
            for suffix in ('', '-wal', '-shm', '-journal'):
                wipe(Path(str(self.db_path) + suffix))
            self.sessions.clear()
            return self.new_session(), recovery

    def _require_password(self, password):
        if not self.vault:
            raise PermissionError('Desbloqueie o app primeiro.')
        try:
            Vault.open(self.vault_path, password=password)
        except WrongSecret:
            raise WrongSecret('Senha atual incorreta.') from None

    def change_password(self, current, new):
        with self._lock:
            self._require_password(current)
            self.vault.change_password(new, self.repository.snapshot())
            sid = self.new_session()
            self.sessions = {sid: time.time()}  # other sessions must log in again
            return sid

    def new_recovery(self, password):
        with self._lock:
            self._require_password(password)
            return self.vault.new_recovery(self.repository.snapshot())

    def set_auto_lock(self, minutes):
        if minutes not in AUTO_LOCK_CHOICES:
            raise ValueError('Tempo de bloqueio inválido.')
        with self._lock:
            if not self.vault:
                raise PermissionError('Desbloqueie o app primeiro.')
            self.vault.header.setdefault('settings', {})['auto_lock'] = minutes
            self.vault.save(self.repository.snapshot())

    def disable(self, password):
        """Back to a plain SQLite file (keeps the data, removes the protection)."""
        with self._lock:
            self._require_password(password)
            data = self.repository.snapshot()
            temporary = self.db_path.with_name(self.db_path.name + '.tmp')
            # deserialize() only replaces the in-memory image; backup() writes the pages to the file.
            source, target = sqlite3.connect(':memory:'), sqlite3.connect(temporary)
            try:
                source.deserialize(data)
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Falha ao gravar o banco sem criptografia; nada foi alterado.')
            finally:
                source.close()
                target.close()
            temporary.replace(self.db_path)
            self.repository.detach()
            wipe(self.vault_path)
            self.vault = None
            self.sessions.clear()
            self.repository.locked = False

    def backup(self):
        """Encrypted vault bytes when protected (same password/recovery key); plain SQLite otherwise."""
        if self.vault:
            with self._lock:
                self.vault.save(self.repository.snapshot())
                return self.vault.export(), 'financas-backup.cofre'
        return self.repository.snapshot(), 'financas-backup.sqlite3'

    def close(self):
        self._stop.set()
