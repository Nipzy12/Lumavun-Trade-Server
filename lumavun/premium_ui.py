"""A single shared glossy hard-surface design system for every desktop tab.

Widgets remain standard accessible PySide6 controls. Layouts can scroll and
reflow; gradients and decorative accents never intercept user input.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout, QFormLayout, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

NAVY = "#080c1b"
INK = "#eff1ff"
MUTED = "#aab6d2"
GOLD = "#e6b868"
VIOLET = "#ae83fa"
GREEN = "#59d2ac"
RED = "#ff8f9d"

STYLESHEET = r"""
* { font-family: "Segoe UI", "Inter", sans-serif; outline: none; }
QWidget { background: #090f21; color: #eef0fc; font-size: 13px; }
QMainWindow { background: #090e1e; }
QWidget#central { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #080d1e,stop:0.48 #10142a,stop:1 #0a0d1d); }
QWidget#pageCanvas, QWidget#pageScrollViewport { background: transparent; }
QFrame#brandHeader {
  background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 #182344,stop:0.50 #100e2c,stop:0.83 #241341,stop:1 #15102d);
  border: 1px solid #393054; border-bottom: 2px solid #7153a2;
  border-radius: 16px;
}
QLabel#brandTitle { color: #f7d695; font-size: 27px; font-weight: 800; letter-spacing: 2px; background: transparent; }
QLabel#brandSubtitle { color: #c9d0e9; font-size: 12px; background: transparent; }
QFrame#pageHero {
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #201b3a,stop:0.46 #171d3b,stop:1 #2b1945);
  border: 1px solid #695087; border-left: 4px solid #e6b868;
  border-radius: 13px;
}
QLabel#pageTitle { color: #f8d79e; font-size: 21px; font-weight: 750; background: transparent; }
QLabel#pageDescription { color: #bac4df; font-size: 12px; background: transparent; }
QFrame#premiumPanel, QFrame#officePanel {
  background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 #22213f,stop:0.16 #191d38,stop:0.7 #111a30,stop:1 #221735);
  border: 1px solid #51446f;
  border-top: 1px solid #9171a3;
  border-radius: 13px;
}
QFrame#premiumPanel[accent="gold"] { border-top: 2px solid #e7b86b; border-bottom: 1px solid #705176; }
QFrame#premiumPanel[accent="violet"] { border-top: 2px solid #ae84ef; }
QFrame#premiumPanel[accent="danger"] { border-top: 2px solid #d8758f; }
QLabel#panelTitle { color: #f3d39b; font-size: 15px; font-weight: 750; background: transparent; }
QLabel#panelSubtitle { color: #9eafd0; font-size: 11px; background: transparent; }
QLabel#hint { color: #b2bfda; font-size: 12px; background: transparent; }
QLabel#statusBadge {
  border: 1px solid #8d719f;
  border-radius: 10px;
  padding: 7px 13px;
  background: #201735;
  color: #d4bdfd;
  font-weight: 650;
}
QLabel#statusBadge[mode="success"] { color:#76e9bb; background:#163c36; border-color:#427d68; }
QLabel#statusBadge[mode="warning"] { color:#f7d58d; background:#453322; border-color:#8b6a3a; }
QLabel#statusBadge[mode="danger"] { color:#ffa7b5; background:#4b2235; border-color:#92546d; }
QLabel#heading { font-size: 22px; color: #f8d89e; font-weight: 800; }
QLabel#subtitle { color: #b2bfd9; font-size: 12px; }
QTabWidget::pane { border:1px solid #3e365f; background:#0c1225; border-radius:12px; top: -1px; }
QTabBar::tab {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #212442,stop:1 #11172f);
  border: 1px solid #4e466e;
  border-bottom: 1px solid #2b2a4b;
  border-top-left-radius: 10px;
  border-top-right-radius: 10px;
  color:#c8d2e8; margin-right:5px;
  padding:11px 18px; min-width: 102px;
  font-size: 12px; font-weight: 650;
}
QTabBar::tab:selected {
  color:#ffe6b4; border:1px solid #c49b73;
  border-bottom:2px solid #d9ad6b;
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #593e83,stop:0.6 #422d77,stop:1 #241a47);
}
QTabBar::tab:hover:!selected { color:white; background:#30294f; border-color:#716195; }
QTabBar QToolButton { background:#251a3e; border:1px solid #594a7d; border-radius:6px; }
QPushButton {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #704bbb,stop:0.5 #583b91,stop:1 #362566);
  border:1px solid #a57ada; color:#faf4ff;
  border-radius:9px; min-height:21px; padding:10px 17px;
  font-size:12px; font-weight:700;
}
QPushButton:hover { color:#fff; background:#7756c0; border-color:#e4bcff; }
QPushButton:pressed { background:#372359; border-color:#8f6cba; }
QPushButton:disabled { background:#25273c; color:#858ca3; border-color:#4b4760; }
QPushButton#primaryButton {
  color:#20172c;
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffe1a0,stop:0.4 #eec678,stop:1 #b9843e);
  border:1px solid #ffdfa2;
}
QPushButton#primaryButton:hover { background:#ffe6b7; color:#1a1228; }
QPushButton#muted, QPushButton#secondaryButton {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #303558,stop:1 #1c2440);
  border:1px solid #65678e; color:#f2effc;
}
QPushButton#danger {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #a94566,stop:1 #652a45);
  color:#fff1f3; border:1px solid #db7794;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {
  background:#0e1730; color:#f6f3ff;
  border:1px solid #5a5279; border-radius:8px;
  padding:9px 12px; selection-background-color:#6c42bf;
  selection-color:white;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height:21px; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus,
QSpinBox:focus { border:1px solid #d3a76c; background:#111c35; }
QComboBox::drop-down { border:none; width:27px; }
QComboBox QAbstractItemView { background:#171d35; color:white; selection-background-color:#614b93; }
QPlainTextEdit { font-family:"Cascadia Code","Consolas",monospace; font-size:12px; }
QGroupBox {
  background:#151b34;
  border:1px solid #55496c; border-radius:11px; margin-top:17px;
  padding:18px 13px 13px 13px; font-weight:650;
}
QGroupBox::title { subcontrol-origin:margin; left:13px; color:#f5d6aa; padding:0 8px; }
QCheckBox { color:#dbe3f3; spacing:11px; background:transparent; }
QCheckBox::indicator { width:18px; height:18px; border:1px solid #ae8aca;
  border-radius:5px; background:#14172e; }
QCheckBox::indicator:checked { background:#9f77e3; border:1px solid #e6c78e; }
QScrollArea { background:transparent; border:none; }
QScrollBar:vertical { background:#0d1429; width:10px; margin:3px; }
QScrollBar::handle:vertical { background:#67568e; min-height:28px; border-radius:4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QScrollBar:horizontal { background:#0e1630; height:10px; }
QScrollBar::handle:horizontal { background:#67568e; border-radius:4px; min-width:26px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0px; }
QTableWidget { background:#111a31; alternate-background-color:#18213d;
 border:1px solid #51466d; border-radius:8px; gridline-color:#273453; }
QHeaderView::section { background:#2c254c; color:#f3d8aa;
 font-size:11px; padding:10px 8px; border:0; border-right:1px solid #45405e; }
QTableWidget::item:selected { background:#5c4887; }
QProgressBar { background:#151a34; border:1px solid #6d528d; border-radius:8px;
 text-align:center; color:#fff3db; min-height:17px; font-weight:700; }
QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
 stop:0 #e4aa52, stop:0.6 #c99ef4,stop:1 #8460d6); border-radius:6px; }
QStatusBar { color:#cbd6ec; background:#15112b; border-top:1px solid #664b8a; }
QStatusBar::item { border:none; }
QToolTip { background:#271f3e; color:white; border:1px solid #b495df; padding:6px; }
"""

def resource_path(relative: str) -> str:
    """Works in source checkout and PyInstaller's one-file extraction directory."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(root / relative)

def brand_icon() -> QIcon:
    path = Path(resource_path("assets/lumavun.ico"))
    if not path.is_file():
        path = Path(resource_path("assets/lumavun.png"))
    return QIcon(str(path)) if path.is_file() else QIcon()

def make_badge(text: str, mode="neutral") -> QLabel:
    badge = QLabel(text)
    badge.setObjectName("statusBadge")
    badge.setProperty("mode", mode)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return badge

def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label

def panel_title(title: str, subtitle: str = "") -> QWidget:
    widget = QWidget()
    widget.setObjectName("pageCanvas")
    col = QVBoxLayout(widget)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(4)
    t = QLabel(title)
    t.setObjectName("panelTitle")
    col.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("panelSubtitle")
        s.setWordWrap(True)
        col.addWidget(s)
    return widget

class PremiumPanel(QFrame):
    def __init__(self, title: str, subtitle: str = "", accent="violet", parent=None):
        super().__init__(parent)
        self.setObjectName("premiumPanel")
        self.setProperty("accent", accent)
        self.layout_body = QVBoxLayout(self)
        self.layout_body.setContentsMargins(20, 18, 20, 20)
        self.layout_body.setSpacing(14)
        self.layout_body.addWidget(panel_title(title, subtitle))

class PageScroll(QScrollArea):
    """All pages scroll vertically instead of clipping fields at 700px heights."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setObjectName("pageScroll")
        self.canvas = QWidget()
        self.canvas.setObjectName("pageCanvas")
        self.body = QVBoxLayout(self.canvas)
        self.body.setContentsMargins(18, 20, 18, 24)
        self.body.setSpacing(16)
        self.setWidget(self.canvas)

    def add(self, widget: QWidget, stretch: int = 0):
        self.body.addWidget(widget, stretch)

    def end(self):
        self.body.addStretch(1)

def page_hero(title: str, description: str, kicker: str = "") -> QFrame:
    frame = QFrame()
    frame.setObjectName("pageHero")
    box = QVBoxLayout(frame)
    box.setContentsMargins(22, 18, 22, 18)
    box.setSpacing(5)
    h = QLabel(title)
    h.setObjectName("pageTitle")
    box.addWidget(h)
    d = QLabel(description)
    d.setObjectName("pageDescription")
    d.setWordWrap(True)
    box.addWidget(d)
    if kicker:
        box.addWidget(hint(kicker))
    return frame

class ResponsiveRow(QWidget):
    """Switches two-column cards into a stack before desktop layout becomes cramped."""
    def __init__(self, left: QWidget, right: QWidget, left_stretch=3, right_stretch=2):
        super().__init__()
        self.setObjectName("pageCanvas")
        self.left, self.right = left, right
        self.layout_row = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.layout_row.setContentsMargins(0, 0, 0, 0)
        self.layout_row.setSpacing(16)
        self.layout_row.addWidget(left, left_stretch)
        self.layout_row.addWidget(right, right_stretch)
        self.last_mode = "horizontal"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        horizontal = self.width() >= 900
        mode = "horizontal" if horizontal else "vertical"
        if mode != self.last_mode:
            self.layout_row.setDirection(
                QBoxLayout.Direction.LeftToRight if horizontal else QBoxLayout.Direction.TopToBottom
            )
            self.last_mode = mode

def spaced_form(parent: QWidget) -> QFormLayout:
    form = QFormLayout()
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(17)
    form.setVerticalSpacing(13)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return form
