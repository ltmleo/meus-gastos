import tempfile
import unittest
from pathlib import Path
from finance.analytics import insights
from finance.classification import suggest, merchant_key
from finance.service import FinanceService
from finance.repository import Repository


def row(month='2026-08', **changes):
    return dict(dict(date=month+'-01', month=month, description='MERCADO TESTE', cents=10000,
                     person='Eu', category='Mercado', category_source='suggested', kind='expense'), **changes)


class InsightsTests(unittest.TestCase):
    def test_context_and_ambiguous_pix(self):
        self.assertEqual(suggest('LIQUIDO DE VENCIMENTO EMPRESA EXEMPLO S/A', kind='income')['category'], 'Salário')
        self.assertEqual(suggest('JUROS POUPANCA', kind='income')['category'], 'Rendimentos')
        self.assertEqual(suggest('JUROS CARTAO')['category'], 'Taxas e encargos')
        self.assertEqual(suggest('PIX RECEBIDO MARIA', kind='income')['category'], 'Outras receitas')
        self.assertEqual(suggest('PIX ENVIADO MARIA')['category'], 'Outros')
        self.assertEqual(suggest('PIX ENVIADO PJBANK PAGAMENTOS S A')['category'], 'Outros')
        self.assertEqual(suggest('10/08 PIX ENVIADO Loja de Moveis Exemplo')['category'], 'Casa e decoração')
        self.assertEqual(suggest('AMAZONMKTPLC*LOJA')['category'], 'Compras')
        self.assertEqual(merchant_key('10/08 PIX ENVIADO EMPRESA'), 'EMPRESA')

    def test_scoped_learning_and_review_preserves_manual(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder)/'db.sqlite3')
            service = FinanceService(repo)
            service.save_manual(row(description='PIX ENVIADO MARIA', category='Moradia'), remember=True)
            learned = repo.rules()['categories']
            self.assertEqual(suggest('PIX ENVIADO MARIA', learned)['category'], 'Moradia')
            self.assertEqual(suggest('PIX RECEBIDO MARIA', learned, 'income')['category'], 'Outras receitas')
            repo.save([row(description='PAGAMENTO CARTAO CREDITO BCE', category='Outros'),
                       row(description='GOL LINHAS', category='Outros', category_source='manual')])
            changes = service.review_categories()
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]['kind'], 'transfer')
            repo.apply_suggestions(changes)
            self.assertEqual(insights(repo.list()['transactions'], '2026-08')['net'], 20000)

    def test_results_transfers_missing_months_and_filters(self):
        rows = [row(cents=20000), row(cents=-1000), row(kind='income', cents=-100000, category='Salário'),
                row(kind='transfer', cents=50000), row(kind='transfer', cents=-20000),
                row(person='Esposa', cents=900000), row('2026-07', cents=10000)]
        result = insights(rows, '2026-08', 'Eu')
        self.assertEqual((result['income'], result['net'], result['result']), (100000, 19000, 81000))
        self.assertEqual(result['margin'], 81)
        self.assertEqual((result['transfer_in'], result['transfer_out']), (20000, 50000))
        self.assertFalse(result['series'][0]['available'])
        self.assertEqual(result['changes'][0]['difference'], 9000)
        self.assertEqual(result['recurring'][0]['average'], 15000)
        self.assertEqual(len(result['largest']), 1)
        self.assertIsNone(insights([], '2026-08')['margin'])
        self.assertFalse(insights([], '2026-08')['comparison_available'])

    def test_income_only_anchor_and_no_future_recurrence(self):
        rows = [row('2026-06'), row('2026-07', cents=-20000, kind='income'), row('2026-08')]
        result = insights(rows, '2026-07')
        self.assertTrue(result['series'][-1]['available'])
        self.assertEqual(result['recurring'], [])
        self.assertEqual(insights(rows[:2], '')['series'][-1]['month'], '2026-07')
