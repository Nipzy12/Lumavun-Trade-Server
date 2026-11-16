"""Offline tests for conservative SMC replay; no MetaTrader installation required."""
import unittest
from lumavun.smc_engine import evaluate, backtest, compare_models

def bars(n=120, start=1700000000, step=900):
    out=[]
    for i in range(n):
        price=100+i*.01
        out.append({"time":start+i*step,"open":price,"high":price+.15,
                    "low":price-.15,"close":price+.04})
    return out

class SMCResearchTests(unittest.TestCase):
    def test_flat_history_no_trades(self):
        low=bars()
        htf=bars(60, step=14400)
        report=compare_models(low,htf)
        self.assertIsNone(report["best_historical_model"])
        self.assertTrue(all(r["trades"]==0 for r in report["results"]))

    def test_rejects_bad_ordered_data(self):
        low=bars()
        low[30]["time"]=low[29]["time"]
        with self.assertRaises(ValueError):
            backtest(low,bars(60,step=14400))

    def test_spread_rejects_negative(self):
        with self.assertRaises(ValueError):
            backtest(bars(),bars(60,step=14400),spread=-.1)

    def test_no_setup_without_confirmed_h4(self):
        self.assertIsNone(evaluate(bars(),bars(60,start=1800000000,step=14400)))

    def test_empty_history_metrics(self):
        report=backtest(bars(),bars(60,step=14400))
        self.assertEqual(report["trades"],0)
        self.assertIsNone(report["win_rate"])
        self.assertIsNone(report["expectancy_r"])

if __name__=="__main__":
    unittest.main()
