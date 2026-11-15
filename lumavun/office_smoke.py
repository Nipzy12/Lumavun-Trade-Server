"""Smoke test the REAL frozen Windows office UI without an MT5 terminal."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

def self_test_office(report_path: str) -> int:
    os.environ["LUMAVUN_OFFICE_SMOKE"] = "1"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from .gui import Window
    report_file = Path(report_path)
    try:
        app = QApplication.instance() or QApplication([])
        win = Window()
        assert win.tabs.tabText(0) == "Trading Office"
        assert "balance" in win.office.cards
        assert "realized" in win.office.cards
        assert win.office.target_amount.minimum() == 0
        win.resize(1180, 910)
        win.show()
        app.processEvents()
        pixmap = win.office.grab()
        picture = report_file.with_name("trading-office-preview.png")
        if pixmap.isNull() or not pixmap.save(str(picture)):
            raise RuntimeError("Could not render AI Trading Office preview")
        report = {"ok": True, "tabs": win.tabs.count(),
                  "first_tab": win.tabs.tabText(0),
                  "preview": picture.name, "preview_bytes": picture.stat().st_size,
                  "frozen": bool(getattr(sys, "frozen", False))}
        win.close()
        status = 0
    except Exception as exc:
        report = {"ok": False, "error_type": type(exc).__name__,
                  "error": str(exc),
                  "frozen": bool(getattr(sys, "frozen", False))}
        status = 2
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return status
