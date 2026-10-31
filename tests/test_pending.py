import tempfile
import unittest
from pathlib import Path
from finance.repository import Repository
from finance.service import FinanceService
from finance.analytics import summarize, insights
from test_insights import row


class PendingTests(unittest.TestCase):
    def test_pending_split_preserves_total_and_groups_merchant(self):
        rows=[row(id=1,description='PIX ENVIADO PESSOA',cents=600000,category='Outros'),
              row(id=2,description='03/08 PIX ENVIADO PESSOA',cents=500000,category='Outros'),
              row(id=3,cents=10000),row(id=4,cents=-2000)]
        result=summarize(rows,'2026-08')
        self.assertEqual(result['net'],1108000)
        self.assertEqual(result['classified_categories'],{'Mercado':8000})
        self.assertEqual(result['pending_groups'][0]['ids'],[1,2])
        self.assertEqual(result['pending_groups'][0]['cents'],1100000)
        self.assertEqual(sum(result['classified_categories'].values())+sum(r['cents'] for r in result['pending_groups']), result['net'])
        self.assertEqual(insights(rows,'2026-08')['pending_groups'],result['pending_groups'])

    def test_group_edit_atomic_scoped_and_learned(self):
        with tempfile.TemporaryDirectory() as folder:
            repo=Repository(Path(folder)/'db.sqlite3');service=FinanceService(repo)
            repo.save([row(description='PIX ENVIADO PESSOA',category='Outros'),row('2026-07',description='PIX ENVIADO PESSOA',category='Outros'),row(description='LOJA OUTRA')])
            service.classify_group([1],'Transferências','transfer',True)
            rows={r['id']:r for r in repo.list()['transactions']}
            self.assertEqual(rows[1]['kind'],'transfer')
            self.assertEqual(rows[2]['category'],'Outros')
            self.assertEqual(rows[1]['cents'],10000)
            self.assertEqual(service.classify('PIX ENVIADO PESSOA','transfer')['category'],'Transferências')
            for ids,category,kind in [([2,3],'Mercado','expense'),([2,999],'Mercado','expense'),([2],'Inválida','expense'),([2],'Salário','income')]:
                with self.assertRaises(ValueError): service.classify_group(ids,category,kind)
            self.assertEqual(repo.list()['transactions'],list(rows.values()))
