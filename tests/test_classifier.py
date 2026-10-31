import tempfile
import unittest
from pathlib import Path
from finance.classification import suggest
from finance.repository import Repository
from finance.service import FinanceService
from test_insights import row


class ClassifierTests(unittest.TestCase):
    def test_fees_take_precedence_over_merchant(self):
        for description in ('IOF · EASYHOTEL BERLIN HM','IOF AMAZON','TARIFA GOL LINHAS'):
            result = suggest(description)
            self.assertEqual(result['category'], 'Taxas e encargos')
            self.assertEqual(result['confidence'], 'high')

    def test_only_user_labels_train_classifier(self):
        history = [row(description='ATELIE LARANJA CENTRO', category='Vestuário', category_source='manual')]
        exact = suggest('MP *ATELIE LARANJA CENTRO', history=history)
        self.assertEqual((exact['category'], exact['confidence']), ('Vestuário','high'))
        similar = suggest('ATELIE LARANJA CENTR', history=history)
        self.assertEqual((similar['category'], similar['confidence']), ('Vestuário','medium'))
        history[0]['category_source'] = 'suggested'
        self.assertEqual(suggest('ATELIE LARANJA CENTRO', history=history)['confidence'], 'low')

    def test_conflicts_and_personal_pix_are_not_guessed(self):
        history = [row(description='JOANA MARIA SILVA', category='Saúde', category_source='manual')]
        self.assertEqual(suggest('PIX ENVIADO JOANA MARIA SILV', history=history)['confidence'], 'low')
        history.append(row(description='JOANA MARIA SILVA', category='Educação', category_source='manual'))
        self.assertEqual(suggest('JOANA MARIA SILVA', history=history)['confidence'], 'low')
        self.assertEqual(suggest('JOANA MARIA SILVA', {'expense:JOANA MARIA SILVA':'Pets'}, history=history)['category'], 'Pets')
        self.assertEqual(suggest('JOANA MARIA SILVA', kind='income', history=history)['category'], 'Outras receitas')

    def test_preview_does_not_auto_assign_medium_suggestion(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Repository(Path(folder)/'db.sqlite3')
            service = FinanceService(repo)
            service.save_manual(row(description='ATELIE LARANJA CENTRO', category='Vestuário'))
            preview = service.preview(b'data;descricao;valor\n01/08/2026;ATELIE LARANJA CENTR;10,00\n', 'test.csv','santander','2026-08')
            proposed = preview['rows'][0]
            self.assertEqual(proposed['category'], 'Outros')
            self.assertEqual(proposed['suggested_category'], 'Vestuário')
            self.assertEqual(proposed['confidence'], 'medium')
            self.assertEqual(service.review_categories(), [])
            self.assertEqual(service.classify('ATELIE LARANJA CENTRO')['category'], 'Vestuário')
            with self.assertRaises(ValueError): service.classify('', 'expense')
