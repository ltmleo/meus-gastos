import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import finance.vault as vault_module
from app import make_handler, open_server, protect_pdf
from finance.security import Security, SESSION_COOKIE
from finance.vault import Vault, WrongSecret, normalize_recovery

FAST_KDF = dict(name='scrypt', n=2 ** 10, r=8, p=1)  # tests only; the app uses 2**17
PASSWORD = 'correto cavalo 42!'


def tx(**changes):
    row = dict(date='2026-09-10', month='2026-09', description='MERCADO', cents=12345, person='Eu', category='Mercado')
    row.update(changes)
    return row


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'cofre.cofre'
        patcher = patch.object(vault_module, 'KDF', FAST_KDF)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_roundtrip_wrong_password_recovery_and_tampering(self):
        vault, recovery = Vault.create(self.path, PASSWORD, b'segredo do banco')
        self.assertNotIn(b'segredo', self.path.read_bytes())
        self.assertEqual(Vault.open(self.path, password=PASSWORD)[1], b'segredo do banco')
        with self.assertRaises(WrongSecret):
            Vault.open(self.path, password='senha errada 123')
        self.assertEqual(Vault.open(self.path, recovery=recovery.lower().replace('-', ' '))[1], b'segredo do banco')
        vault.change_password('outra senha forte 9', b'novo conteudo')
        with self.assertRaises(WrongSecret):
            Vault.open(self.path, password=PASSWORD)
        self.assertEqual(Vault.open(self.path, recovery=recovery)[1], b'novo conteudo')
        raw = bytearray(self.path.read_bytes())
        raw[-5] ^= 1
        self.path.write_bytes(bytes(raw))
        with self.assertRaises(ValueError):
            Vault.open(self.path, password='outra senha forte 9')

    def test_vault_from_previous_name_still_opens(self):
        vault, _ = Vault.create(self.path, PASSWORD, b'dados antigos')
        raw = self.path.read_bytes()
        legacy = vault_module.LEGACY_MAGICS[0]
        # Re-encrypt as the old format did: old magic in the file and in the authenticated data.
        header_size = int.from_bytes(raw[len(vault_module.MAGIC):len(vault_module.MAGIC) + 4], 'big')
        header_bytes = raw[len(vault_module.MAGIC) + 4:len(vault_module.MAGIC) + 4 + header_size]
        import json as _json
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        header = _json.loads(header_bytes)
        body = AESGCM(vault.dek).encrypt(vault_module._unb64(header['nonce']), b'dados antigos', legacy + header_bytes)
        self.path.write_bytes(legacy + raw[len(vault_module.MAGIC):len(vault_module.MAGIC) + 4] + header_bytes + body)
        self.assertTrue(Vault.exists(self.path))
        opened, data = Vault.open(self.path, password=PASSWORD)
        self.assertEqual(data, b'dados antigos')
        opened.save(data)
        self.assertTrue(self.path.read_bytes().startswith(vault_module.MAGIC))

    def test_password_rules(self):
        for weak in ('curta', 'aaaaaaaaaa', ''):
            with self.assertRaises(ValueError):
                Vault.create(self.path, weak, b'x')
        self.assertEqual(normalize_recovery('abcd-0O1i'), 'ABCD')


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'financas.sqlite3'
        patcher = patch.object(vault_module, 'KDF', FAST_KDF)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_enable_encrypts_wipes_plain_file_and_persists_changes(self):
        security = Security(self.db)
        security.repository.save([tx()])
        sid, recovery = security.enable(PASSWORD)
        self.assertFalse(self.db.exists())
        self.assertTrue(security.vault_path.exists())
        self.assertNotIn(b'MERCADO', security.vault_path.read_bytes())
        security.repository.save([tx(description='FARMACIA')])  # written straight to the vault
        security.lock()
        security.close()
        reopened = Security(self.db)
        self.assertTrue(reopened.locked)
        reopened.unlock(recovery=recovery)
        self.assertEqual(sorted(r['description'] for r in reopened.repository.list()['transactions']), ['FARMACIA', 'MERCADO'])
        reopened.disable(PASSWORD)
        self.assertTrue(self.db.exists() and not reopened.vault_path.exists())
        db = sqlite3.connect(self.db)
        self.assertEqual(db.execute('select count(*) from transactions').fetchone()[0], 2)
        db.close()
        reopened.close()

    def test_brute_force_delay(self):
        security = Security(self.db)
        security.enable(PASSWORD)
        security.lock()
        for _ in range(3):
            with self.assertRaises(WrongSecret):
                security.unlock(password='tentativa errada')
        with self.assertRaises(PermissionError):
            security.unlock(password=PASSWORD)  # even the right one waits
        security.close()

    def test_auto_lock_after_idle(self):
        security = Security(self.db)
        sid, _ = security.enable(PASSWORD)
        self.assertFalse(security.check_idle(now=security.last_activity + 14 * 60))
        self.assertTrue(security.check_idle(now=security.last_activity + 16 * 60))
        self.assertTrue(security.locked)
        self.assertFalse(security.valid_session(sid))
        security.unlock(password=PASSWORD)
        security.set_auto_lock(0)  # never
        self.assertFalse(security.check_idle(now=security.last_activity + 10 ** 6))
        with self.assertRaises(ValueError):
            security.set_auto_lock(7)
        security.close()

    def test_protected_pdf(self):
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(100, 100)
        plain = io.BytesIO()
        writer.write(plain)
        reader = PdfReader(io.BytesIO(protect_pdf(plain.getvalue(), 'senha1234')))
        self.assertTrue(reader.is_encrypted)
        self.assertFalse(reader.decrypt('errada'))
        self.assertTrue(reader.decrypt('senha1234'))


class HttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(vault_module, 'KDF', FAST_KDF)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.workspace = Path(self.tmp.name)
        (self.workspace / 'output').mkdir()
        (self.workspace / 'output' / 'relatorio.pdf').write_bytes(b'%PDF dados')
        self.security = Security(self.workspace / 'data' / 'financas.sqlite3')
        self.security.repository.save([tx()])
        self.server = open_server(make_handler(self.security, workspace=self.workspace), 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.security.close()
        self.tmp.cleanup()

    def call(self, path, body=None, cookie=None, headers=None):
        all_headers = dict(headers or {})
        if body is not None:
            all_headers['Content-Type'] = 'application/json'
        if cookie:
            all_headers['Cookie'] = f'{SESSION_COOKIE}={cookie}'
        request = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=all_headers)
        with urlopen(request) as response:
            cookie_header = response.headers.get('Set-Cookie', '')
            return json.loads(response.read() or b'{}'), cookie_header

    def code(self, *args, **kwargs):
        with self.assertRaises(HTTPError) as error:
            self.call(*args, **kwargs)
        return error.exception.code

    def test_session_lock_and_unlock_flow(self):
        self.assertFalse(self.call('/api/security/status')[0]['protected'])
        self.assertEqual(len(self.call('/api/data')[0]['transactions']), 1)  # open while unprotected
        result, cookie_header = self.call('/api/security/enable', {'password': PASSWORD})
        self.assertRegex(result['recovery'], r'^[A-Z2-9]{5}(-[A-Z2-9]{5}){4}$')
        self.assertIn('HttpOnly', cookie_header)
        self.assertIn('SameSite=Strict', cookie_header)
        sid = cookie_header.split(';')[0].split('=', 1)[1]
        self.assertEqual(self.code('/api/data'), 401)  # no cookie
        self.assertEqual(len(self.call('/api/data', cookie=sid)[0]['transactions']), 1)
        self.call('/api/security/lock', {}, cookie=sid)
        self.assertEqual(self.code('/api/data', cookie=sid), 423)
        self.assertTrue(self.call('/api/security/status')[0]['locked'])
        self.assertEqual(self.code('/api/security/unlock', {'password': 'senha errada 1'}), 401)
        _, cookie_header = self.call('/api/security/unlock', {'password': PASSWORD})
        sid = cookie_header.split(';')[0].split('=', 1)[1]
        backup = urlopen(Request(self.base + '/api/backup', headers={'Cookie': f'{SESSION_COOKIE}={sid}'})).read()
        self.assertTrue(backup.startswith(b'MEUSGASTOS-COFRE'))
        self.assertNotIn(b'MERCADO', backup)

    def test_print_token_is_read_only_and_short_lived(self):
        self.call('/api/security/enable', {'password': PASSWORD})
        token = self.security.new_print_token()
        self.assertEqual(len(self.call('/api/data', headers={'X-Print-Token': token})[0]['transactions']), 1)
        self.assertEqual(self.code('/api/delete', {'kind': 'transactions', 'id': 1}, headers={'X-Print-Token': token}), 401)
        self.security.drop_print_token(token)
        self.assertEqual(self.code('/api/data', headers={'X-Print-Token': token}), 401)

    def test_cross_site_requests_are_refused(self):
        self.assertEqual(self.code('/api/data', headers={'Sec-Fetch-Site': 'cross-site'}), 403)
        self.assertEqual(self.code('/api/backup', headers={'Sec-Fetch-Site': 'same-site'}), 403)
        self.assertEqual(len(self.call('/api/data', headers={'Sec-Fetch-Site': 'same-origin'})[0]['transactions']), 1)
        with urlopen(self.base + '/') as response:
            for header in ('Content-Security-Policy', 'X-Frame-Options', 'Referrer-Policy', 'Cross-Origin-Opener-Policy'):
                self.assertIn(header, response.headers)

    def test_exposed_files_listing_and_wipe(self):
        groups = self.call('/api/security/exposed')[0]['groups']
        self.assertEqual([g['key'] for g in groups], ['output'])
        self.assertEqual(self.call('/api/security/wipe', {'group': 'output'})[0]['removed'], 1)
        self.assertFalse((self.workspace / 'output' / 'relatorio.pdf').exists())
        self.assertEqual(self.code('/api/security/wipe', {'group': '../data'}), 400)


if __name__ == '__main__':
    unittest.main()
