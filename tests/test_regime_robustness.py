import csv
from pathlib import Path
import tempfile
import unittest

from yield_share_anatomy.regimes import analyze, describe_group, get_regime, load_months


class RobustnessTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(get_regime(5.0, 5.0), "Sideways")
        self.assertEqual(get_regime(5.1, 5.0), "Up")
        self.assertEqual(get_regime(-5.0, 5.0), "Sideways")
        self.assertEqual(get_regime(-5.1, 5.0), "Down")

    def test_aggregation(self):
        rows = [
            {"month":"2026-01", "tsla_monthly_pct":10, "ytsl_nav_drip_monthly_pct":12, "ytsl_market_drip_monthly_pct":11, "gap_pp":2, "market_gap_pp":1},
            {"month":"2026-02", "tsla_monthly_pct":2, "ytsl_nav_drip_monthly_pct":3, "ytsl_market_drip_monthly_pct":4, "gap_pp":1, "market_gap_pp":2},
            {"month":"2026-03", "tsla_monthly_pct":-10, "ytsl_nav_drip_monthly_pct":-8, "ytsl_market_drip_monthly_pct":-9, "gap_pp":2, "market_gap_pp":1}
        ]
        report = analyze(rows, (5.0,))
        self.assertEqual(report['month_count'], 3)
        self.assertEqual(report['overall_monthly_nav_win_count'], 3)
        self.assertEqual([g['months'] for g in report['threshold_sensitivity'][0]['regimes']], [1,1,1])

    def test_bad_gap_rejected(self):
        with tempfile.TemporaryDirectory() as tempdir:
            p = Path(tempdir) / 'm.csv'
            p.write_text('month,tsla_monthly_pct,ytsl_nav_drip_monthly_pct,ytsl_market_drip_monthly_pct,gap_pp\n2026-01,10,11,11,5\n')
            with self.assertRaisesRegex(ValueError, 'inconsistent'):
                load_months(p)

    def test_duplicate_month_rejected(self):
        with tempfile.TemporaryDirectory() as tempdir:
            p = Path(tempdir) / 'm.csv'
            p.write_text('month,tsla_monthly_pct,ytsl_nav_drip_monthly_pct,ytsl_market_drip_monthly_pct,gap_pp\n2026-01,10,11,11,1\n2026-01,10,11,11,1\n')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                load_months(p)


if __name__ == '__main__':
    unittest.main()
