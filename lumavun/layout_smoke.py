"""Exercise all premium GUI tabs in a *frozen Windows executable*.

Uses Qt offscreen (no broker/account/API requests) and fails if important
controls become clipped or the premium app icon was not packaged.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

def self_test_premium_ui(report_path: str) -> int:
    os.environ["LUMAVUN_OFFICE_SMOKE"] = "1"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QScrollArea
    from .premium_ui import STYLESHEET, brand_icon, PageScroll
    from .gui import Window
    from .office import OfficeView

    outfile = Path(report_path)
    try:
        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        app.setStyleSheet(STYLESHEET)
        app.setWindowIcon(brand_icon())
        assert not brand_icon().isNull(), "Premium artwork was not bundled"
        win = Window()
        win.resize(1366, 768)
        win.show()
        app.processEvents()
        assert win.tabs.count() == 6, "Expected six application workspaces"
        assert all(
            isinstance(win.tabs.widget(i), (PageScroll, OfficeView))
            for i in range(6)
        ), "Tabs must use scrollable/adaptive pages"
        screenshots = {}
        for idx, short in ((0, "office"), (1, "dashboard"), (2, "providers"),
                           (3, "strategy"), (4, "risk"), (5, "mcp")):
            win.tabs.setCurrentIndex(idx)
            app.processEvents()
            preview = outfile.with_name("premium-" + short + "-preview.png")
            assert win.grab().save(str(preview)), "Cannot render " + short
            assert preview.stat().st_size > 2500, "Blank " + short + " screenshot"
            screenshots[short] = preview.name

        # URL/API-key/connection mode controls must NEVER overlap or collapse.
        win.tabs.setCurrentIndex(5)
        app.processEvents()
        controls = [win.mt5_mode, win.mt5_url, win.mt5_remote_key]
        for control in controls:
            assert control.isVisible(), "Connection field not visible"
            assert control.height() >= 30, "Clipped field: " + str(control.objectName())
            assert control.width() >= 180, "Clipped field width"
        for prev, curr in zip(controls, controls[1:]):
            assert curr.geometry().top() >= prev.geometry().bottom(), (
                "MCP connection controls overlap: " + str(prev.geometry())
                + " / " + str(curr.geometry()))
        mcp_scroll = win.tabs.widget(5)
        assert mcp_scroll.verticalScrollBar().maximum() > 0, (
            "The MCP page should scroll vertically instead of shrinking its fields"
        )

        # The app must be usable at the former cramped resolution, too.
        win.resize(965, 675)
        app.processEvents()
        for control in controls:
            assert control.height() >= 30, "Field collapsed at compact resolution"
        assert win.tabs.widget(5).verticalScrollBar().maximum() > 0

        report = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
                  "tabs": win.tabs.count(), "screenshots": screenshots,
                  "icon_loaded": not brand_icon().isNull(),
                  "mcp_scrollable": True,
                  "mcp_field_min_height": min(x.height() for x in controls)}
        win.close()
        code = 0
    except Exception as exc:
        report = {"ok": False, "error_type": type(exc).__name__,
                  "error": str(exc),
                  "frozen": bool(getattr(sys, "frozen", False))}
        code = 2
    outfile.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return code
