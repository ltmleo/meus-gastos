import tempfile
import unittest
from pathlib import Path
from finance.importers.santander import SantanderImporter
from finance.repository import Repository
from finance.service import FinanceService
from finance.analytics import summarize


TEXT = '''EXTRATO CONSOLIDADO INTELIGENTE
dezembro/2026
(+) Total de Créditos 1.020,00
(-) Total de Débitos 150,00
Conta Corrente
Movimentação
SALDO EM 30/11 100,00
01/12 LIQUIDO DE VENCIMENTO EMPRESA 123456 1.000,00 1.100,00
 PIX ENVIADO
COMERCIO TESTE
- 50,00- 1.050,00
EXTRATO CONSOLIDADO INTELIGENTE
dezembro/2026
Extrato_PF_A4_Inteligente - 27/11/2024
BALP_TESTE
Pagina: 3/9
Data Descrição Nº Documento Movimento (R$) Saldo (R$)
02/12 DEBITO AUT. FAT.CARTAO MASTER CARD
FINAL 1111
- 100,00-
 VENCIMENTO CDB/RDB - 20,00 970,00
SALDO EM 31/12 970,00
Comprovantes de Pagamento
01/12 PIX ENVIADO COMERCIO TESTE - 50,00
Poupança
31/12 JUROS - 100,00
'''


class StatementTests(unittest.TestCase):
    def test_wrapped_rows_dates_signs_and_sections(self):
        rows, warnings, meta = SantanderImporter().parse_text(TEXT, '2027-01')
        self.assertEqual(len(rows), 4)
        self.assertEqual([r['cents'] for r in rows], [-100000, 5000, 10000, -2000])
        self.assertEqual(rows[1]['date'], '2026-12-01')
        self.assertEqual([r['kind'] for r in rows], ['income', 'expense', 'transfer', 'transfer'])
        self.assertEqual(meta['closing_cents'], 97000)
        self.assertTrue(warnings)

    def test_incomplete_statement_rejected(self):
        for text in (TEXT.replace('50,00-', '51,00-'), TEXT.replace('1.020,00', '1.030,00'), TEXT.replace('SALDO EM 31/12', 'SALDO FINAL')):
            with self.assertRaises(ValueError):
                SantanderImporter().parse_text(text, '2026-12')

    def test_persistence_and_analytics(self):
        rows, _, _ = SantanderImporter().parse_text(TEXT, '2026-12')
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder)/'test.sqlite3')
            service = FinanceService(repo)
            for row in rows:
                service.save_manual(row)
            saved = repo.list()['transactions']
            summary = summarize(saved, '2026-12')
            self.assertEqual(summary['income'], 100000)
            self.assertEqual(summary['expenses'], 5000)
            self.assertEqual(summary['credits'], 0)
            self.assertEqual(summary['result'], 95000)
            self.assertEqual(summary['transfers'], 12000)
            self.assertEqual(sum(summary['categories'].values()), 5000)
            service.save_manual({'description': 'Descrição corrigida'}, saved[0]['id'])
            self.assertEqual(repo.list()['transactions'][0]['kind'], saved[0]['kind'])
