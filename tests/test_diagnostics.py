"""Verify that diagnosics report status reliably, without a real MT5 terminal."""
import json
from lumavun import diagnostics, mt5_bridge

def test_mt5_import_smoke_reports_error_without_crash(monkeypatch, tmp_path):
    def fail():
        raise RuntimeError("MetaTrader5 binary/DLL import failed: DLL load failed")
    monkeypatch.setattr(mt5_bridge, "_api", fail)
    output = tmp_path / "report.json"
    assert diagnostics.self_test_mt5(str(output)) == 2
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert "DLL load failed" in data["error"]
