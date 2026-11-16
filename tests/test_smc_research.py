"""Offline regression tests for H4 POIs, real-history integrity and Pine export."""
from __future__ import annotations
import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from lumavun.smc_history import normalize, read_csv, write_csv, coverage, _timestamp
from lumavun.smc_htf import context


def h4_fixture():
    start=1_500_000_000
    bars=[]
    for i in range(45):
        b={"time":start+i*14400,"open":100.0,"high":101.0,
           "low":99.0,"close":100.3}
        if i==34:
            b.update({"high":105.0})
        if i==43:
            b.update({"open":100.5,"close":100.1})
        if i==44:
            b.update({"open":103.0,"low":102.0,"high":107.0,"close":106.0})
        bars.append(b)
    return bars


def ltf_fixture(htf, length=40):
    first=htf[-1]["time"]+14400
    return [{"time":first+i*900,"open":104.2,"high":104.5,
             "low":104.0,"close":104.3} for i in range(length)]


class H4POITest(unittest.TestCase):
    def test_confirmed_h4_ob_after_bos(self):
        htf=h4_fixture()
        ltf=ltf_fixture(htf)
        result=context(htf,ltf,ltf[-1]["time"])
        self.assertEqual(result.bias,1)
        self.assertIsNotNone(result.poi)
        self.assertEqual(result.poi.kind,"OB")
        self.assertEqual(result.poi.bottom,99.0)
        self.assertEqual(result.poi.top,101.0)
        self.assertIsNone(result.invalid_reason)

    def test_ltf_close_invalidates_ob(self):
        htf=h4_fixture()
        ltf=ltf_fixture(htf)
        ltf[-1].update({"open":100.0,"high":100.2,"low":98.0,"close":98.5})
        result=context(htf,ltf,ltf[-1]["time"])
        self.assertIsNone(result.poi)
        self.assertEqual(result.invalid_reason,"CLOSE_BROKEN_OR_CONSUMED")

    def test_wick_does_not_invalidate_if_not_fully_mitigated(self):
        htf=h4_fixture()
        ltf=ltf_fixture(htf)
        ltf[-1].update({"open":104.0,"high":104.5,"low":100.5,"close":103.0})
        result=context(htf,ltf,ltf[-1]["time"])
        self.assertIsNotNone(result.poi)
        self.assertTrue(result.poi_touched_recently)

    def test_future_h4_close_not_visible(self):
        htf=h4_fixture()
        ltf=ltf_fixture(htf)
        at=htf[-1]["time"]+1000
        self.assertIsNone(context(htf,ltf,at).poi)

    def test_fvg_only_wont_substitute_ob(self):
        htf=h4_fixture()
        ltf=ltf_fixture(htf)
        self.assertIsNone(context(htf,ltf,ltf[-1]["time"],"FVG only").poi)


class HistoryTest(unittest.TestCase):
    def test_csv_roundtrip(self):
        bars=[{"time":1_600_000_000+i*900,"open":100.0,"high":102.0,
               "low":99.0,"close":101.0} for i in range(40)]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"fixture.csv"
            write_csv(path,bars)
            self.assertEqual(read_csv(path,"M15"),bars)
        self.assertEqual(coverage(bars,"M15")["bars"],40)

    def test_excludes_unclosed_current_candle(self):
        now=datetime.fromtimestamp(1_600_100_000,timezone.utc)
        bars=[{"time":1_600_000_000+i*900,"open":100.0,"high":102.0,
               "low":99.0,"close":101.0} for i in range(40)]
        bars.append({"time":1_600_099_500,"open":100.0,"high":102.0,
                     "low":99.0,"close":101.0})
        self.assertEqual(len(normalize(bars,"M15",now)),40)

    def test_rejects_unsorted_duplicate_times(self):
        bars=[{"time":1_600_000_000+i*900,"open":100.0,"high":102.0,
               "low":99.0,"close":101.0} for i in range(40)]
        bars[-1]["time"]=bars[-2]["time"]
        with self.assertRaises(ValueError):
            normalize(bars,"M15")

    def test_iso_time_parsing(self):
        self.assertEqual(_timestamp("2020-01-01T00:00:00Z"),1577836800)


if __name__=="__main__":
    unittest.main()
