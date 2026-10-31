import unittest
from finance.analytics import summarize, insights, period_scope
from test_insights import row


class PeriodTests(unittest.TestCase):
    def test_inclusive_dates_not_invoice_month(self):
        rows = [row('2026-09',date='2026-08-10',cents=100),
                row('2026-09',date='2026-08-20',cents=200),
                row('2026-08',date='2026-08-09',cents=400),
                row('2026-08',date='2026-08-21',cents=800)]
        for aggregate in (summarize,insights):
            result=aggregate(rows,'2026-09',start='2026-08-10',end='2026-08-20')
            self.assertEqual(result['net'],300)
            self.assertEqual(aggregate(rows,'2026-08')['net'],1200)
        summary=summarize(rows,'',start='2026-08-10',end='2026-08-20')
        self.assertEqual(summary['history'],{'2026-08':300})
        self.assertEqual(summary['previous'],400)

    def test_cross_year_filters_and_previous_equal_duration(self):
        rows=[row('2027-02',date='2026-12-31',cents=100,payment_channel='account'),
              row('2027-02',date='2027-01-01',cents=200,payment_channel='account'),
              row('2027-02',date='2026-12-30',cents=40,payment_channel='account'),
              row('2027-02',date='2026-12-29',cents=60,payment_channel='account'),
              row('2027-02',date='2026-12-28',cents=9999,payment_channel='account'),
              row('2027-02',date='2027-01-01',cents=9999,person='Esposa',payment_channel='account'),
              row('2027-02',date='2027-01-01',cents=9999,payment_channel='credit')]
        data=insights(rows,'','Eu','account','2026-12-31','2027-01-01')
        self.assertEqual(data['net'],300)
        self.assertEqual([s['month'] for s in data['series']],['2026-12','2027-01'])
        self.assertEqual(data['changes'][0]['previous'],100)
        self.assertEqual(data['recurring'][0]['current'],300)
        self.assertEqual(data['recurring'][0]['months'],2)

    def test_single_day_leap_day_empty_period_and_validation(self):
        rows=[row(date='2024-02-29',cents=123)]
        self.assertEqual(summarize(rows,'',start='2024-02-29',end='2024-02-29')['net'],123)
        empty=insights([], '',start='2026-07-31',end='2026-08-01')
        self.assertFalse(empty['comparison_available'])
        self.assertEqual(len(empty['series']),2)
        self.assertFalse(any(s['available'] for s in empty['series']))
        for start,end in [('2026-02-30','2026-03-01'),('2026-09-01','2026-08-01'),('2026-01-01',''),('','2026-01-01'),('2000-01-01','2026-01-01')]:
            with self.assertRaises(ValueError): period_scope([],start=start,end=end)
        self.assertEqual(len(period_scope([],start='9999-12-01',end='9999-12-31')[3]),1)
