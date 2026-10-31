import base64
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import sqlite3
from http.server import HTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from app import make_handler
from finance.repository import Repository
from finance.service import FinanceService
from finance.domain import money, validate
from finance.analytics import summarize
from finance.importers.santander import SantanderImporter, transaction_date
from finance.classification import suggest, merchant_key
from finance.ownership import canonical_holders

def row(**changes):
    return dict(date='2026-08-12', month='2026-09', description='Mercado', cents=12345, person='Eu', category='Mercado', **changes)

class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name)/'db.sqlite3')
        self.service = FinanceService(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_money_and_validation(self):
        self.assertEqual(money('R$ 1.234,56'), 123456)
        self.assertEqual(money('-0,29'), -29)
        for value in ('NaN', 'inf', '0.001'):
            with self.assertRaises(ValueError): money(value)
        invalid = row(); invalid['cents'] = 1.2
        with self.assertRaises(ValueError): validate(invalid)

    def test_year_boundary(self):
        self.assertEqual(transaction_date('22/12','2026-01'),'2025-12-22')
        self.assertEqual(transaction_date('22/12/2023','2026-01'),'2023-12-22')

    def test_ownership_abbreviations_and_saved_mapping(self):
        names=['RAFAEL TAVARES SILVA','RAFAEL T SILVA','JULIA P SOUZA','RAFAEL T SILV']
        aliases=canonical_holders(names)
        self.assertEqual(aliases[names[-1]],names[0])
        self.assertNotEqual(aliases[names[2]],names[0])
        text='''Total a Pagar R$ 30,00 Vencimento 10/09/2026
        RAFAEL TAVARES SILVA - 5228 XXXX XXXX 1111 Despesas
        01/09 MERCADO 10,00 VALOR TOTAL 10,00 0,00
        JULIA P SOUZA - 5228 XXXX XXXX 2222 Despesas
        02/09 FARMACIA 20,00 VALOR TOTAL 20,00 0,00
        RAFAEL T SILV - 5228 XXXX XXXX 3333 Despesas'''
        def parsed(*args):return SantanderImporter().parse_text(text,'2026-09')
        with patch.object(SantanderImporter,'parse',side_effect=parsed):
            preview=self.service.preview(b'first','first.pdf','santander','2026-09')
            self.assertEqual([r['person'] for r in preview['rows']],['Eu','Esposa'])
            self.assertEqual(preview['rows'][1]['holder'],'JULIA P SOUZA')
            mapping={names[0]:'Esposa',names[2]:'Eu'}
            for r in preview['rows']:r['person']=mapping[r['holder']]
            self.service.confirm(preview['token'],preview['rows'],mapping)
            next_preview=self.service.preview(b'next','next.pdf','santander','2026-10')
            self.assertEqual([r['person'] for r in next_preview['rows']],['Esposa','Eu'])

    def test_smart_categories_and_learning(self):
        self.assertEqual(suggest('MERCADOLIVRE*MERCADO')['category'],'Compras')
        self.assertEqual(suggest('FARMÁCIA CENTRAL')['category'],'Saúde')
        self.assertEqual(suggest('SUPERMERCADOS SAO VICENTE')['category'],'Mercado')
        self.assertEqual(suggest('PREPLY')['category'],'Educação')
        self.assertEqual(suggest('IOF · PREPLY')['category'],'Taxas e encargos')
        self.assertEqual(suggest('NOME DESCONHECIDO')['category_source'],'unknown')
        custom=dict(row(),description='MP *COMERCIO XYZ',category='Pets')
        self.service.save_manual(custom,remember=True)
        learned=self.repo.rules()['categories']
        self.assertEqual(suggest('COMERCIO XYZ',learned)['category'],'Pets')
        self.assertEqual(suggest('COMERCIO XYZ OUTRO',learned)['category'],'Outros')
        self.assertEqual(self.service.review_categories(),[])
        self.repo.save([dict(row(),description='MERCADOLIVRE',category='Mercado',category_source='legacy')])
        changes=self.service.review_categories()
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]['category'],'Compras')
        self.repo.apply_suggestions(changes)
        self.assertEqual(self.service.review_categories(),[])

    def test_analytics_credits_filters_and_calendar(self):
        rows=[dict(row(),cents=10000,person='Eu',installment='02/03'),
              dict(row(),cents=5000,person='Esposa'),dict(row(),cents=-1000,person='Esposa'),
              dict(row(),month='2026-07',cents=3000),dict(row(),month='2026-10',cents=9999)]
        summary=summarize(rows,'2026-09')
        self.assertEqual(summary['net'],14000)
        self.assertEqual(summary['people_expenses']['Esposa'],5000)
        self.assertEqual(summary['installments']['Parceladas'],10000)
        self.assertEqual(summary['installments']['Sem parcela indicada'],5000)
        self.assertIsNone(summary['previous'])
        self.assertNotIn('2026-10',summary['history'])
        self.assertEqual(summary['history_people'][0]['month'],'2026-04')
        self.assertEqual(sum(summary['merchants'].values()),15000)
        filtered=summarize(rows,'2026-09','Esposa')
        self.assertEqual(filtered['net'],4000)
        self.assertEqual(filtered['people_expenses'],{'Esposa':5000})
        self.assertEqual(filtered['category_people']['Mercado']['Eu'],0)

    def test_migrates_old_database_without_changing_rows(self):
        path=Path(self.tmp.name)/'legacy.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY,import_id INTEGER,date TEXT,month TEXT,description TEXT,cents INTEGER,person TEXT,category TEXT,card TEXT,installment TEXT)')
            db.execute("INSERT INTO transactions VALUES (1,NULL,'2026-08-12','2026-09','Minha compra',123,'Eu','Outros','','')")
        db.close()
        repository=Repository(path)
        rows=repository.list()['transactions']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['cents'],123)
        self.assertEqual(rows[0]['holder'],'')
        self.assertEqual(rows[0]['category_source'],'legacy')

    def test_continuous_pdf_sections_credits_usd_and_fees(self):
        text = '''Total a Pagar R$ 227,45 Vencimento 10/09/2026
        PESSOA - 5228 XXXX XXXX 1234 Pagamento e Demais Créditos
        Compra Data Descrição Parcela R$ US$ 10/08 DEB AUTOM DE FATURA EM C/ -900,00
        Despesas Compra Data Descrição Parcela R$ US$ 02/09 ANUIDADE 08/12 0,00
        Parcelamentos Compra Data Descrição Parcela R$ US$ 3 15/06 MERCADO 03/03 123,45
        Despesas Compra Data Descrição Parcela R$ US$ 04/08 CURSO 90,00 16,80
        COTAÇÃO DOLAR R$ 5,3763 IOF DESPESA NO EXTERIOR 3,00
        05/08 LOJA -9,00 VALOR TOTAL 207,45 16,80
        PESSOA DOIS - 5480 XXXX XXXX 5678 Despesas Compra Data Descrição Parcela R$ US$
        3 06/08 PADARIA 20,00 VALOR TOTAL 20,00 0,00'''
        rows, warnings, meta = SantanderImporter().parse_text(text, '2026-09')
        self.assertEqual(len(rows),5)
        self.assertEqual(sum(r['cents'] for r in rows),meta['total_cents'])
        self.assertEqual(rows[0]['installment'],'03/03')
        self.assertEqual(rows[-1]['card'],'5678')
        self.assertEqual(rows[1]['cents'],9000)
        self.assertEqual(rows[2]['cents'],300)

    def test_review_duplicate_protection_and_rollback(self):
        data=b'data;descricao;valor\n02/09/2026;Mercado;123,45\n02/09/2026;Mercado;123,45\n'
        preview=self.service.preview(data,'sample.csv','santander','2026-09')
        self.assertEqual(self.repo.list()['transactions'],[])
        invalid=[dict(preview['rows'][0], person='invalid')]
        with self.assertRaises(ValueError): self.service.confirm(preview['token'],invalid)
        self.assertEqual(self.repo.list()['imports'],[])
        self.service.confirm(preview['token'],preview['rows'])
        self.assertEqual(len(self.repo.list()['transactions']),2)  # Identical real purchases remain distinct.
        with self.assertRaises(ValueError): self.service.preview(data,'renamed.csv','santander','2026-10')
        self.repo.delete('imports',self.repo.list()['imports'][0]['id'])
        self.assertEqual(self.repo.list()['transactions'],[])
        self.service.preview(data,'sample.csv','santander','2026-09')

    def test_persistence_edit_analytics(self):
        rows=[row(),dict(row(),person='Esposa',cents=5000),dict(row(),person='Compartilhado',cents=-1000)]
        self.repo.save(rows)
        persisted=Repository(Path(self.tmp.name)/'db.sqlite3').list()['transactions']
        self.assertEqual(summarize(persisted,'2026-09')['net'],16345)
        self.assertEqual(summarize(persisted,'2026-09','Esposa')['net'],5000)
        self.assertEqual(summarize(persisted,'2026-08')['count'],0)
        self.repo.update(persisted[0]['id'],dict(row(),person='Esposa',cents=100))
        self.assertEqual(len(self.repo.list()['transactions']),3)

    def test_http_workflow_backup_and_origin_protection(self):
        server=HTTPServer(('127.0.0.1',0),make_handler(self.repo))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        root=f'http://127.0.0.1:{server.server_port}'
        def post(path,payload,origin=None):
            headers={'Content-Type':'application/json'}
            if origin: headers['Origin']=origin
            with urlopen(Request(root+path,data=json.dumps(payload).encode(),headers=headers)) as response:
                return json.load(response)
        try:
            preview=post('/api/preview',dict(filename='sample.csv',provider='santander',month='2026-09',content=base64.b64encode(b'data;descricao;valor\n01/09/2026;Loja;10,00\n').decode()))
            post('/api/confirm',dict(token=preview['token'],rows=preview['rows']))
            classification = post('/api/classify',dict(description='IOF EASYHOTEL',kind='expense'))
            self.assertEqual(classification['category'],'Taxas e encargos')
            self.assertEqual(classification['confidence'],'high')
            with urlopen(root+'/api/data') as response: self.assertEqual(len(json.load(response)['transactions']),1)
            with urlopen(root+'/api/insights?month=2026-09&channel=credit') as response:
                self.assertEqual(json.load(response)['net'],0)
            with urlopen(root+'/api/data') as response: self.assertEqual(json.load(response)['app_version'],12)
            auto=post('/api/preview',dict(filename='Nubank_2026-07-23.csv',month='2026-09',content=base64.b64encode(b'date,title,amount\n2026-07-01,Loja,10.00\n').decode()))
            self.assertEqual(auto['metadata']['detected_format'],'Nubank · Fatura CSV')
            self.assertEqual(auto['rows'][0]['month'],'2026-07')
            with urlopen(root+'/api/summary?start=2026-09-01&end=2026-09-01') as response:
                self.assertEqual(json.load(response)['count'],1)
            with self.assertRaises(HTTPError) as error:
                urlopen(root+'/api/insights?start=2026-09-30&end=2026-09-01')
            self.assertEqual(error.exception.code,400)
            with urlopen(root+'/') as response:
                html = response.read().decode()
                self.assertIn('/js/main.js', html)
            with urlopen(root+'/js/main.js?v=4') as response: self.assertEqual(response.status,200)
            with urlopen(root+'/api/backup') as response: self.assertTrue(response.read().startswith(b'SQLite format 3'))
            with self.assertRaises(HTTPError) as error: post('/api/save',{'row':row()},'https://untrusted.example')
            self.assertEqual(error.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__': unittest.main()
