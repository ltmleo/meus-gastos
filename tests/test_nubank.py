import tempfile
import unittest
from pathlib import Path
from finance.importers.auto import parse_auto
from finance.repository import Repository
from finance.service import FinanceService


class NubankTests(unittest.TestCase):
    def test_invoice_detection_refunds_installments_and_month(self):
        content=('date,title,amount\n2026-06-28,Loja - Parcela 2/3,"123,45"\n'
                 '2026-07-01,IOF de volta de Loja,"- 3,45"\n'
                 '2026-06-23,Pagamento recebido,"- 1.234,00"\n').encode()
        rows,w,m=parse_auto(content,'Nubank_2026-07-23.csv','2026-09')
        self.assertEqual([r['cents'] for r in rows],[12345,-345])
        self.assertEqual(rows[0]['installment'],'2/3')
        self.assertEqual(rows[0]['description'],'Loja')
        self.assertTrue(all(r['month']=='2026-07' and r['payment_channel']=='credit' for r in rows))
        self.assertEqual(m['excluded_payment_cents'],-123400)
        self.assertEqual(m['parsed_total_cents']+m['excluded_payment_cents'],m['source_total_cents'])
        renamed, warnings, meta=parse_auto(content,'renomeado.csv','2026-08')
        self.assertEqual(renamed[0]['month'],'2026-08')
        self.assertTrue(any('não informa o vencimento' in item for item in warnings))

    def test_statement_signs_own_accounts_and_payment(self):
        content=('Data,Valor,Identificador,Descrição\n'
                 '01/08/2026,100.00,a,Transferência Recebida - PESSOA TESTE - •••.111.111-•• - BANCO\n'
                 '02/08/2026,-20.00,b,Transferência enviada pelo Pix - NOME EXATO - •••.222.222-•• - BANCO\n'
                 '01/09/2026,-30.00,c,Pagamento de fatura\n').encode()
        with tempfile.TemporaryDirectory() as folder:
            repo=Repository(Path(folder)/'db.sqlite3');repo.remember_own_account('NOME EXATO')
            service=FinanceService(repo)
            preview=service.preview(content,'qualquer.csv',month='2026-10')
            rows=preview['rows']
            self.assertEqual([r['cents'] for r in rows],[-10000,2000,3000])
            self.assertEqual([r['kind'] for r in rows],['income','transfer','transfer'])
            self.assertEqual(rows[1]['description'],'PIX ENVIADO NOME EXATO')
            self.assertEqual(rows[2]['category'],'Pagamento de cartão')
            self.assertEqual(rows[2]['month'],'2026-09')
            self.assertNotIn('closing_cents',preview['metadata'])
            self.assertEqual(repo.list()['transactions'],[])
            service.confirm(preview['token'],rows)
            self.assertEqual(len(repo.list()['transactions']),3)
            with self.assertRaises(ValueError):service.preview(content,'outro.csv',month='2026-10')

    def test_encodings_delimiters_and_quoted_newlines(self):
        content='\ufeffdate;title;amount\r\n2026-07-01;"Loja, exemplo\nCentro";"10,00"\r\n'.encode()
        rows,_,_=parse_auto(content,'rename.csv','2026-07')
        self.assertEqual(rows[0]['cents'],1000)
        content='Data;Valor;Identificador;Descrição\n01/08/2026;-2.50;a;Débito em conta\n'.encode('cp1252')
        rows,_,_=parse_auto(content,'rename.csv','2026-08')
        self.assertEqual(rows[0]['cents'],250)

    def test_rejects_malformed_unknown_or_partial_files(self):
        for content in (b'foo,bar\n1,2\n', b'date,title,amount\n2026-07-01,Loja\n',
                        b'date,title,amount\n2026-07-01,Loja,10.00\n2026-02-30,Loja,5.00\n',
                        b'date,title,amount\n2026-07-01,Loja,NaN\n',
                        b'date,title,amount\n2026-07-01,Pagamento recebido,100.00\n',
                        'Data,Valor,Identificador,Descrição\n01/08/2026,-10,a,Loja\n02/08/2026,-20,a,Loja\n'.encode()):
            with self.assertRaises(ValueError):parse_auto(content,'arquivo.csv','2026-07')
