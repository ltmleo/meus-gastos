import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import make_handler, open_server, port_file, running_instance
from finance.domain import check_people, validate
from finance.insights import dashboard
from finance.repository import Repository
from finance.service import FinanceService


def tx(**changes):
    row = dict(date='2026-09-10', month='2026-09', description='MERCADO', cents=1000, person='Eu', category='Mercado')
    row.update(changes)
    return row


class PeopleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'db.sqlite3'

    def test_new_database_waits_for_the_welcome_wizard(self):
        house = Repository(self.path).household()
        self.assertFalse(house['configured'])

    def test_existing_database_keeps_original_names(self):
        repo = Repository(self.path)
        repo.save([tx(), tx(person='Esposa')])
        db = sqlite3.connect(self.path)
        db.execute("DELETE FROM settings")
        db.commit()
        db.close()
        house = Repository(self.path).household()  # migration on open
        self.assertEqual((house['members'], house['shared'], house['configured']), (['Eu', 'Esposa'], 'Compartilhado', True))

    def test_rename_moves_transactions_and_holders(self):
        repo = Repository(self.path)
        repo.save([tx(), tx(person='Esposa'), tx(person='Compartilhado')], holder_rules={'ANA SOUZA': 'Esposa'})
        repo.set_household(['Bruno', 'Ana'], 'Casa', {'Eu': 'Bruno', 'Esposa': 'Ana', 'Compartilhado': 'Casa'})
        self.assertEqual(sorted(r['person'] for r in repo.list()['transactions']), ['Ana', 'Bruno', 'Casa'])
        self.assertEqual(repo.rules()['holders'], {'ANA SOUZA': 'Ana'})
        self.assertEqual(repo.people(), ['Bruno', 'Ana', 'Casa'])
        with self.assertRaises(ValueError):
            validate(tx(person='Eu'), repo.people())
        with self.assertRaises(ValueError):  # Ana still has a transaction
            repo.set_household(['Bruno'], '')

    def test_single_person_without_shared_group(self):
        repo = Repository(self.path)
        repo.set_household(['Carla'], '')
        self.assertEqual(repo.people(), ['Carla'])
        service = FinanceService(repo)
        service.save_manual(tx(person='Carla'))
        result = dashboard(repo.list()['transactions'], {}, '2026-09', people=repo.people())
        self.assertEqual(result['kpis']['people'], {'Carla': 1000})

    def test_name_rules(self):
        self.assertEqual(check_people([' Ana ', 'Bia'], ' Nós '), (['Ana', 'Bia'], 'Nós'))
        for members, shared in (([], ''), (['Ana', 'ana'], ''), (['Ana'], 'Ana'), (['x'] * 7, ''), (['A' * 31], ''), ([''], '')):
            with self.assertRaises(ValueError):
                check_people(members, shared)

    def test_first_holder_maps_to_first_person(self):
        from unittest.mock import patch
        from finance.importers.santander import SantanderImporter
        repo = Repository(self.path)
        repo.set_household(['Bruno', 'Ana'], 'Casa')
        text = '''Total a Pagar R$ 30,00 Vencimento 10/09/2026
        BRUNO LIMA - 5228 XXXX XXXX 1111 Despesas
        01/09 MERCADO 10,00 VALOR TOTAL 10,00 0,00
        ANA LIMA - 5228 XXXX XXXX 2222 Despesas
        02/09 FARMACIA 20,00 VALOR TOTAL 20,00 0,00'''
        with patch.object(SantanderImporter, 'parse', side_effect=lambda *a: SantanderImporter().parse_text(text, '2026-09')):
            preview = FinanceService(repo).preview(b'pdf', 'fatura.pdf', 'santander', '2026-09')
        self.assertEqual([r['person'] for r in preview['rows']], ['Bruno', 'Ana'])


class PeopleEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name) / 'db.sqlite3')
        self.server = open_server(make_handler(self.repo), 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None):
        request = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'} if body is not None else {})
        with urlopen(request) as response:
            return json.loads(response.read())

    def test_configure_people(self):
        self.assertFalse(self.call('/api/data')['household']['configured'])
        self.call('/api/people', {'members': ['Ana'], 'shared': ''})
        data = self.call('/api/data')
        self.assertEqual((data['people'], data['household']['configured']), (['Ana'], True))
        with self.assertRaises(HTTPError):
            self.call('/api/people', {'members': ['Ana', 'Ana']})
        status = self.call('/api/security/status')
        self.assertEqual(status['app'], 'meusgastos')
        self.assertRegex(status['version'], r'^\d+\.\d+\.\d+$')


    def test_second_launch_finds_the_running_app(self):
        db = Path(self.tmp.name) / 'db.sqlite3'
        self.assertIsNone(running_instance(db))  # no port file yet
        port_file(db).write_text(str(self.server.server_port))
        self.assertEqual(running_instance(db), self.server.server_port)
        self.assertIsNone(running_instance(Path(self.tmp.name) / 'outro' / 'db.sqlite3'))
        other = Path(self.tmp.name) / 'outro.sqlite3'
        port_file(other).write_text(str(self.server.server_port))  # same folder, other database
        self.assertIsNone(running_instance(other))


if __name__ == '__main__':
    unittest.main()
