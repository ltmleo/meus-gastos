import sqlite3
import tempfile
import unittest
from pathlib import Path
from finance.domain import validate
from finance.repository import Repository
from finance.service import FinanceService
from finance.analytics import summarize, insights
from test_insights import row


class PaymentChannelTests(unittest.TestCase):
    def test_origin_is_independent_of_kind_and_editable(self):
        self.assertEqual(validate(row(card='1234'))['payment_channel'], 'credit')
        self.assertEqual(validate(row(description='PIX ENVIADO LOJA'))['payment_channel'], 'account')
        self.assertEqual(validate(row())['payment_channel'], 'unspecified')
        with self.assertRaises(ValueError):
            validate(row(payment_channel='invalid'))
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder)/'test.db')
            service = FinanceService(repo)
            service.save_manual(row(payment_channel='account'))
            saved = repo.list()['transactions'][0]
            service.save_manual({'description':'Nova descrição'}, saved['id'])
            self.assertEqual(repo.list()['transactions'][0]['payment_channel'], 'account')
            service.save_manual({'payment_channel':'credit'}, saved['id'])
            self.assertEqual(repo.list()['transactions'][0]['payment_channel'], 'credit')

    def test_migration_preserves_values_and_runs_once(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.db'
            repo = Repository(path)
            repo.save([row(card='1234'), row(description='PIX ENVIADO LOJA'), row()])
            with sqlite3.connect(path) as db:
                db.execute('ALTER TABLE transactions DROP COLUMN payment_channel')
            db.close()
            repo = Repository(path)
            rows = sorted(repo.list()['transactions'], key=lambda r:r['id'])
            self.assertEqual([r['payment_channel'] for r in rows], ['credit','account','unspecified'])
            self.assertEqual(sum(r['cents'] for r in rows), 30000)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE transactions SET payment_channel='account' WHERE id=1")
            db.close()
            Repository(path)
            self.assertEqual(next(r for r in repo.list()['transactions'] if r['id']==1)['payment_channel'], 'account')

    def test_totals_filters_and_card_payment_not_duplicated(self):
        rows = [row(payment_channel='credit', cents=20000), row(payment_channel='credit', cents=-2000),
                row(payment_channel='account', cents=5000),
                row(payment_channel='account', kind='transfer', cents=18000),
                row(payment_channel='account', kind='income', cents=-50000), row(cents=1000)]
        for aggregate in (summarize, insights):
            data = aggregate(rows, '2026-08')
            self.assertEqual(data['payment_channels']['credit']['net'], 18000)
            self.assertEqual(data['payment_channels']['account']['net'], 5000)
            self.assertEqual(data['net'], 24000)
            credit = aggregate(rows, '2026-08', channel='credit')
            self.assertEqual((credit['net'], credit['income']), (18000, 0))
            account = aggregate(rows, '2026-08', channel='account')
            self.assertEqual((account['net'], account['income']), (5000, 50000))

    def test_pdf_origin(self):
        from finance.importers.santander import SantanderImporter
        from test_statement import TEXT
        records, _, _ = SantanderImporter().parse_text(TEXT, '2026-12')
        self.assertTrue(all(r['payment_channel']=='account' for r in records))
        text='Total a Pagar R$ 10,00 Vencimento 10/09/2026 TESTE - 5228 XXXX XXXX 1111 Despesas 01/09 MERCADO 10,00 VALOR TOTAL 10,00'
        records, _, _ = SantanderImporter().parse_text(text, '2026-09')
        self.assertEqual(records[0]['payment_channel'], 'credit')
