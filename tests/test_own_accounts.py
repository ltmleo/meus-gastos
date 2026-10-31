import tempfile
import unittest
from pathlib import Path
from finance.repository import Repository
from finance.service import FinanceService
from finance.analytics import summarize
from test_insights import row


class OwnAccountTests(unittest.TestCase):
    def test_confirmed_exact_pix_only_and_future_imports(self):
        with tempfile.TemporaryDirectory() as folder:
            repo=Repository(Path(folder)/'db.sqlite3')
            repo.save([row(description='PIX ENVIADO MARIA TESTE',cents=600000,payment_channel='account'),
                       row(description='03/08 PIX RECEBIDO MARIA TESTE',cents=-100000,kind='income',payment_channel='account'),
                       row(description='PIX ENVIADO MARIA TESTE JUNIOR',payment_channel='account'),
                       row(description='MARIA TESTE',payment_channel='credit')])
            self.assertEqual(repo.remember_own_account('Maria Teste'),[1,2])
            summary=summarize(repo.list()['transactions'],'2026-08')
            self.assertEqual(summary['net'],20000)
            self.assertEqual(summary['income'],0)
            self.assertEqual(summary['transfers'],700000)
            service=FinanceService(Repository(repo.path))
            preview=service.preview(b'data;descricao;valor\n02/08/2026;PIX ENVIADO MARIA TESTE;30,00\n','new.csv','santander','2026-08')
            self.assertEqual(preview['rows'][0]['kind'],'transfer')
            self.assertEqual(preview['rows'][0]['category'],'Transferências')
