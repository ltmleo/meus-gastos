"""Encrypted file that holds the whole SQLite database.

Layout: MAGIC | 4-byte header length | JSON header | AES-256-GCM ciphertext.

A random 256-bit data key (DEK) encrypts the database. The DEK itself is stored
twice, wrapped by keys derived with scrypt from (1) the user's password and
(2) a recovery code shown once. Changing the password only rewraps the DEK.
The header is authenticated as associated data, so it cannot be swapped or edited.
"""
import base64
import hashlib
import json
import os
import secrets
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b'MEUSGASTOS-COFRE\x01'
# Vaults written while the project was called "Entre nós" still open; the next save upgrades them.
LEGACY_MAGICS = (b'ENTRENOS-COFRE\x01',)


def _magic(raw):
    return next((m for m in (MAGIC, *LEGACY_MAGICS) if raw.startswith(m)), None)
KDF = dict(name='scrypt', n=2 ** 17, r=8, p=1)
RECOVERY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O, 1/I
MIN_PASSWORD = 8


class WrongSecret(ValueError):
    pass


def _b64(data):
    return base64.b64encode(data).decode()


def _unb64(text):
    return base64.b64decode(text)


def _derive(secret, salt, kdf):
    return hashlib.scrypt(secret.encode('utf-8'), salt=salt, n=kdf['n'], r=kdf['r'], p=kdf['p'],
                          maxmem=256 * 1024 * 1024, dklen=32)


def _wrap(dek, secret, kdf):
    salt, nonce = os.urandom(16), os.urandom(12)
    wrapped = AESGCM(_derive(secret, salt, kdf)).encrypt(nonce, dek, b'meusgastos-dek')
    return dict(salt=_b64(salt), nonce=_b64(nonce), wrapped=_b64(wrapped))


def _unwrap(slot, secret, kdf):
    try:
        return AESGCM(_derive(secret, _unb64(slot['salt']), kdf)).decrypt(_unb64(slot['nonce']), _unb64(slot['wrapped']), b'meusgastos-dek')
    except InvalidTag:
        raise WrongSecret('Senha ou chave incorreta.') from None


def normalize_recovery(code):
    return ''.join(c for c in code.upper() if c in RECOVERY_ALPHABET)


def new_recovery_code():
    raw = ''.join(secrets.choice(RECOVERY_ALPHABET) for _ in range(25))  # 125 bits
    return '-'.join(raw[i:i + 5] for i in range(0, 25, 5))


def check_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ValueError(f'Use uma senha com pelo menos {MIN_PASSWORD} caracteres.')
    if len(password) > 256:
        raise ValueError('Senha muito longa.')
    if len(set(password)) < 4:
        raise ValueError('Senha muito fraca: use letras, números e símbolos variados.')


class Vault:
    """In-memory view of an encrypted file: the DEK and header after a successful unlock."""

    def __init__(self, path, dek, header):
        self.path, self.dek, self.header = Path(path), dek, header

    @staticmethod
    def exists(path):
        path = Path(path)
        return path.is_file() and _magic(path.read_bytes()[:64]) is not None

    @classmethod
    def create(cls, path, password, data, settings=None):
        check_password(password)
        dek, recovery = AESGCM.generate_key(256), new_recovery_code()
        header = dict(version=1, cipher='AES-256-GCM', kdf=KDF, settings=settings or {},
                      password=_wrap(dek, password, KDF), recovery=_wrap(dek, normalize_recovery(recovery), KDF))
        vault = cls(path, dek, header)
        vault.save(data)
        return vault, recovery

    @staticmethod
    def _read(path):
        raw = Path(path).read_bytes()
        magic = _magic(raw)
        if not magic:
            raise ValueError('Arquivo não é um cofre do Meus Gastos.')
        size = struct.unpack('>I', raw[len(magic):len(magic) + 4])[0]
        start = len(magic) + 4
        header_bytes = raw[start:start + size]
        return json.loads(header_bytes), header_bytes, raw[start + size:], magic

    @classmethod
    def open(cls, path, password=None, recovery=None):
        """Returns (vault, plaintext database bytes)."""
        header, header_bytes, body, magic = cls._read(path)
        slot, secret = (header['recovery'], normalize_recovery(recovery or '')) if recovery else (header['password'], password or '')
        dek = _unwrap(slot, secret, header['kdf'])
        try:
            data = AESGCM(dek).decrypt(_unb64(header['nonce']), body, magic + header_bytes)
        except InvalidTag:
            raise ValueError('Cofre corrompido ou alterado: o conteúdo não confere.') from None
        return cls(path, dek, header), data

    def save(self, data):
        """Encrypt with a fresh nonce and replace the file atomically."""
        self.header['nonce'] = _b64(os.urandom(12))
        header_bytes = json.dumps(self.header, sort_keys=True).encode()
        body = AESGCM(self.dek).encrypt(_unb64(self.header['nonce']), data, MAGIC + header_bytes)
        temporary = self.path.with_name(self.path.name + '.tmp')
        with open(temporary, 'wb') as handle:
            handle.write(MAGIC + struct.pack('>I', len(header_bytes)) + header_bytes + body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def change_password(self, new_password, data):
        check_password(new_password)
        self.header['password'] = _wrap(self.dek, new_password, self.header['kdf'])
        self.save(data)

    def new_recovery(self, data):
        recovery = new_recovery_code()
        self.header['recovery'] = _wrap(self.dek, normalize_recovery(recovery), self.header['kdf'])
        self.save(data)
        return recovery

    def export(self):
        return self.path.read_bytes()


def wipe(path):
    """Best effort: overwrite with random bytes before deleting.

    On SSDs and some file systems old blocks may survive; full-disk encryption
    (BitLocker) is what really protects deleted data.
    """
    path = Path(path)
    if not path.is_file():
        return False
    size = path.stat().st_size
    with open(path, 'r+b') as handle:
        remaining = size
        while remaining > 0:
            chunk = min(remaining, 1024 * 1024)
            handle.write(os.urandom(chunk))
            remaining -= chunk
        handle.flush()
        os.fsync(handle.fileno())
    path.unlink()
    return True
