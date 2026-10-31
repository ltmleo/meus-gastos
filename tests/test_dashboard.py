import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from app import make_handler, open_server
from finance.insights import dashboard, recurring, installments, suggest_budgets, label, competence
from finance.repository import Repository
from finance.service import FinanceService


def tx(month, description, cents, category='Alimentação', date=None, **extra):
    return dict(id=extra.pop('id', None), date=date or month + '-10', month=month, description=description, cents=cents,
                person=extra.pop('person', 'Eu'), category=category, kind=extra.pop('kind', 'expense'),
                payment_channel=extra.pop('payment_channel', 'credit'), card='1234', installment=extra.pop('installment', ''),
                bank='santander', **extra)


class InsightTests(unittest.TestCase):
    def test_spike_and_saving_counted_once_per_category(self):
        rows = [tx(m, 'RESTAURANTE', 20000) for m in ('2026-06', '2026-07', '2026-08')]
        rows += [tx('2026-09', 'RESTAURANTE', 60000)]
        result = dashboard(rows, {'Alimentação': 30000}, '2026-09')
        topics = [c for c in result['insights'] if c['topic'] == 'Alimentação' and c['saving']]
        self.assertGreaterEqual(len(topics), 2)  # over budget and above average
        self.assertEqual(result['potential_saving'], max(c['saving'] for c in topics))
        spike = next(c for c in result['insights'] if c['id'] == 'spike-Alimentação')
        self.assertEqual(spike['saving'], 40000)

    def test_compares_only_sources_present_in_the_month(self):
        rows = [tx('2026-08', 'MERCADO', 50000, 'Mercado'), tx('2026-08', 'PIX ENVIADO JOAO', 90000, 'Mercado', payment_channel='account'),
                tx('2026-09', 'MERCADO', 52000, 'Mercado')]
        result = dashboard(rows, {}, '2026-09')
        mercado = next(c for c in result['categories'] if c['category'] == 'Mercado')
        self.assertEqual(mercado['avg'], 50000)
        self.assertIn('account', result['missing_sources'])
        self.assertFalse(any(c['id'].startswith('drop-') for c in result['insights']))

    def test_recurring_requires_stable_amount(self):
        rows = [tx(m, 'NETFLIX.COM', 5590, 'Lazer') for m in ('2026-06', '2026-07', '2026-08')]
        rows += [tx(m, 'RESTAURANTE', v) for m, v in (('2026-06', 1000), ('2026-07', 9000), ('2026-08', 3000))]
        found = recurring(rows, '2026-08')
        self.assertEqual([r['merchant'] for r in found], ['NETFLIX COM'])
        self.assertEqual(found[0]['annual'], 5590 * 12)

    def test_installment_projection_skips_finished(self):
        rows = [tx('2026-09', 'LOJA', 10000, installment='02/04'), tx('2026-09', 'OUTRA', 5000, installment='03/03')]
        result = installments(rows, '2026-09')
        self.assertEqual(len(result['active']), 1)
        self.assertEqual(result['total_remaining'], 20000)
        self.assertEqual([p['cents'] for p in result['projection']], [10000, 10000])

    def test_duplicate_charge_alert(self):
        rows = [tx('2026-09', 'LOJA X', 4500, date='2026-09-03'), tx('2026-09', 'LOJA X', 4500, date='2026-09-03')]
        result = dashboard(rows, {}, '2026-09')
        self.assertTrue(any(c['id'].startswith('duplicate-') and c['severity'] == 'alert' for c in result['insights']))

    def test_negative_result_and_savings_rate(self):
        rows = [tx('2026-09', 'SALARIO', -100000, 'Salário', kind='income', payment_channel='account'), tx('2026-09', 'LOJA', 150000, 'Compras')]
        result = dashboard(rows, {}, '2026-09')
        self.assertEqual(result['kpis']['result'], -50000)
        self.assertEqual(result['income_sources'], [{'category': 'Salário', 'cents': 100000}])
        self.assertTrue(any(c['id'] == 'savings-rate' and c['severity'] == 'alert' for c in result['insights']))

    def test_spending_counts_in_purchase_month(self):
        # October invoice: September purchases, one from October, and an installment bought in June.
        rows = [tx('2026-10', 'MERCADO', 10000, 'Mercado', date='2026-09-15'),
                tx('2026-10', 'POSTO', 5000, 'Transporte', date='2026-09-20'),
                tx('2026-10', 'PADARIA', 2000, date='2026-10-02'),
                tx('2026-10', 'LOJA', 3000, 'Compras', date='2026-06-15', installment='05/06'),
                tx('2026-09', 'FARMACIA', 4000, 'Saúde', date='2026-08-20')]
        self.assertEqual(competence(rows[3]), '2026-10')
        result = dashboard(rows, {}, '')
        self.assertEqual(result['month'], '2026-09')  # last complete purchase cycle
        self.assertEqual(result['kpis']['expense'], 15000)
        self.assertFalse(result['partial'])
        october = dashboard(rows, {}, '2026-10')
        self.assertEqual(october['kpis']['expense'], 5000)
        self.assertTrue(october['partial'])
        self.assertEqual([c['id'] for c in october['insights'] if c['id'].startswith(('spike', 'drop'))], [])
        by_invoice = dashboard(rows, {}, '2026-10', basis='invoice')
        self.assertEqual(by_invoice['kpis']['expense'], 20000)

    def test_suggested_budgets_and_label(self):
        rows = [tx(m, 'MERCADO', 40000, 'Mercado') for m in ('2026-07', '2026-08', '2026-09')]
        self.assertEqual(suggest_budgets(rows), {'Mercado': 38000})
        self.assertEqual(label('27/08  PIX ENVIADO Maria Silva'), 'Maria Silva')


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name) / 'db.sqlite3')
        self.repo.save([dict(tx('2026-09', 'MERCADO', 12345, 'Outros'), category_source='suggested')])
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

    def test_dashboard_budgets_and_bulk_update(self):
        identifier = self.repo.list()['transactions'][0]['id']
        self.assertEqual(self.call('/api/dashboard?month=2026-09')['kpis']['expense'], 12345)
        data = self.call('/api/data')
        self.assertEqual(data['transactions'][0]['period'], '2026-09')
        self.assertEqual(data['default_months']['purchase'], '2026-09')
        self.call('/api/budgets', {'budgets': {'Mercado': 10000}, 'replace': True})
        self.assertEqual(self.call('/api/budgets')['budgets'], {'Mercado': 10000})
        with self.assertRaises(HTTPError):
            self.call('/api/budgets', {'budgets': {'Inexistente': 100}})
        self.assertEqual(self.call('/api/bulk-update', {'ids': [identifier], 'changes': {'category': 'Mercado', 'person': 'Esposa'}})['updated'], 1)
        saved = self.repo.list()['transactions'][0]
        self.assertEqual((saved['category'], saved['person'], saved['category_source']), ('Mercado', 'Esposa', 'manual'))
        with self.assertRaises(HTTPError):
            self.call('/api/bulk-update', {'ids': [identifier], 'changes': {'cents': 1}})
        budget = self.call('/api/dashboard?month=2026-09')['budgets'][0]
        self.assertEqual(budget['status'], 'over')

    def test_report_pdf_endpoint(self):
        for body, code in (({}, 400), ({'m': '2026-13'}, 400), ({'m': '2026-09', 'p': '<x>'}, 400)):
            with self.assertRaises(HTTPError) as error:
                self.call('/api/report.pdf', body)
            self.assertEqual(error.exception.code, code)
        with patch('finance.pdfexport.find_browser', return_value=None), self.assertRaises(HTTPError) as error:
            self.call('/api/report.pdf', {'m': '2026-09'})
        self.assertEqual(error.exception.code, 503)
        with self.assertRaises(HTTPError) as error:  # PDFs are POST only now
            urlopen(self.base + '/api/report.pdf?m=2026-09')
        self.assertEqual(error.exception.code, 404)
        captured = {}
        def fake(url, timeout=90):
            captured['url'] = url
            return b'%PDF-1.4 fake'
        request = Request(self.base + '/api/report.pdf', data=json.dumps({'m': '2026-09', 'p': 'Esposa', 'x': '1'}).encode(),
                          headers={'Content-Type': 'application/json'})
        with patch('app.render_pdf', side_effect=fake), urlopen(request) as response:
            self.assertEqual(response.headers['Content-Type'], 'application/pdf')
            self.assertIn('relatorio-2026-09.pdf', response.headers['Content-Disposition'])
            self.assertTrue(response.read().startswith(b'%PDF'))
        self.assertTrue(captured['url'].endswith(f':{self.server.server_port}/relatorio?m=2026-09&p=Esposa&print=1'))
        with urlopen(self.base + '/relatorio?m=2026-09') as response:
            self.assertIn(b'/js/main.js', response.read())

    def test_static_files_and_traversal(self):
        with urlopen(self.base + '/js/main.js') as response:
            self.assertIn('javascript', response.headers['Content-Type'])
        with urlopen(self.base + '/lancamentos') as response:
            self.assertIn(b'<!doctype html>', response.read())
        with self.assertRaises(HTTPError):
            urlopen(self.base + '/js/../../app.py')
        with self.assertRaises(HTTPError):
            urlopen(self.base + '/%2e%2e/app.py')


if __name__ == '__main__':
    unittest.main()
