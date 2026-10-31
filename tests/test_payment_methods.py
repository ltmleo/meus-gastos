import tempfile
import unittest
from pathlib import Path
from finance.analytics import summarize, insights
from finance.domain import validate
from finance.repository import Repository
from finance.service import FinanceService
from test_insights import row

class PaymentMethodTests(unittest.TestCase):
    def test_groups_filters_and_transfers(self):
        rows = [row(bank='santander',payment_channel='credit',cents=10000),
                row(bank='santander',payment_channel='credit',cents=-2000),
                row(bank='nubank',payment_channel='credit',cents=4000),
                row(bank='santander',payment_channel='account',cents=3000),
                row(bank='nubank',payment_channel='account',cents=2000),
                row(bank='nubank',payment_channel='account',kind='transfer',cents=80000),
                row(bank='nubank',payment_channel='account',kind='income',cents=-90000),
                row(bank='nubank',payment_channel='account',date='2026-09-01',month='2026-09',cents=999)]
        for aggregate in (summarize, insights):
            result=aggregate(rows,'2026-08')
            groups=result['payment_methods']
            self.assertEqual(len(groups),4)
            self.assertEqual(sum(g['net'] for g in groups),result['net'])
            self.assertEqual(groups[0]['net'],8000)
            self.assertEqual(groups[0]['credits'],2000)
            self.assertEqual(len(aggregate(rows,'2026-08',channel='account')['payment_methods']),2)
            self.assertEqual(aggregate(rows,'',start='2026-09-01',end='2026-09-01')['payment_methods'][0]['net'],999)
            self.assertEqual(aggregate([], '2026-08')['payment_methods'],[])

    def test_persistence_and_automatic_bank(self):
        with tempfile.TemporaryDirectory() as folder:
            repo=Repository(Path(folder)/'test.db')
            service=FinanceService(repo)
            preview=service.preview(b'date,title,amount\n2026-07-01,Loja,10.00\n','Nubank_2026-07-23.csv',month='2026-07')
            self.assertEqual(preview['rows'][0]['bank'],'nubank')
            service.confirm(preview['token'],preview['rows'])
            saved=repo.list()['transactions'][0]
            service.save_manual({'description':'Nova loja'},saved['id'])
            self.assertEqual(repo.list()['transactions'][0]['bank'],'nubank')
            service.save_manual({'bank':'santander'},saved['id'])
            self.assertEqual(repo.list()['transactions'][0]['bank'],'santander')
            generic=service.preview(b'data;descricao;valor\n01/08/2026;Loja;20,00\n','generic.csv',month='2026-08')
            self.assertEqual(generic['rows'][0]['bank'],'unspecified')
            self.assertEqual(validate(row())['bank'],'unspecified')
            with self.assertRaises(ValueError): validate(row(bank='invalid'))
