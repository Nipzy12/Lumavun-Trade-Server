"""LUMAVUN AI Trading Office: a visual trading workstation, not a simulated account.

Role badges represent *real* application workflow states. The performance desk
reads actual MetaTrader account/deal history or displays 'unavailable'.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from collections import defaultdict
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView, QSizePolicy
)

from .config import Settings
from .performance import make_snapshot

INK = "#eaf0ff"
MUTED = "#9aa9c8"
POSITIVE = "#44d6a4"
NEGATIVE = "#f37e91"
GOLD = "#dbb779"
VIOLET = "#ad96ff"
INDIGO = "#111a32"

def _money(v, currency="USD", signed=False):
    if v is None:
        return "—"
    try:
        value = float(v)
    except (ValueError, TypeError):
        return "—"
    if not math.isfinite(value):
        return "—"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:,.2f} {currency}"

def _tint(value):
    if value is None:
        return MUTED
    return POSITIVE if value > 0 else NEGATIVE if value < 0 else INK

def _label(text, color=INK, size=12, bold=False):
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{700 if bold else 400};")
    lbl.setWordWrap(True)
    return lbl

def _panel():
    frame = QFrame()
    frame.setObjectName("officePanel")
    frame.setStyleSheet(
        "QFrame#officePanel{background:#111a31;border:1px solid #2d3553;"
        "border-radius:13px;}"
    )
    return frame

class MetricCard(QFrame):
    def __init__(self, label, caption):
        super().__init__()
        self.setMinimumHeight(98)
        self.setStyleSheet("MetricCard{background:#141e37;border:1px solid #303a5c;border-radius:12px;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 12, 12)
        layout.setSpacing(4)
        layout.addWidget(_label(label.upper(), MUTED, 10, True))
        self.value = _label("—", INK, 21, True)
        layout.addWidget(self.value)
        layout.addWidget(_label(caption, "#8799bd", 10))
    def set_value(self, value, color=INK):
        self.value.setText(value)
        self.value.setStyleSheet(f"color:{color};font-size:21px;font-weight:700;")

class OfficeScene(QWidget):
    """A lightweight drawn office with desks and human-like AI worker silhouettes."""
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(295)
        self._state = [
            ("AI ANALYST", "Ready", VIOLET),
            ("RISK MANAGER", "Guard active", GOLD),
            ("TRADE EXECUTOR", "Disarmed", NEGATIVE),
            ("PERFORMANCE", "Awaiting data", POSITIVE),
        ]
    def update_states(self, analyst, risk, executor, performance):
        self._state = [
            ("AI ANALYST", analyst, VIOLET),
            ("RISK MANAGER", risk, GOLD),
            ("TRADE EXECUTOR", executor, NEGATIVE),
            ("PERFORMANCE", performance, POSITIVE),
        ]
        self.update()

    @staticmethod
    def _round(p, x, y, w, h, color, r=10):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(x, y, w, h), r, r)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = max(1, self.width())
        p.scale(width / 960.0, self.height() / 300.0)
        self._round(p, 0, 0, 960, 300, "#11192e", 13)
        # Room architecture: skyline windows and floor perspective.
        self._round(p, 17, 18, 926, 83, "#202941", 12)
        for index in range(13):
            x = 31 + index * 70
            self._round(p, x, 29, 58, 61, "#15253a", 3)
            self._round(p, x + 7, 35, 43, 45, "#1c3550", 2)
            p.setPen(QPen(QColor("#2c4661"), 1))
            p.drawLine(int(x + 29), 35, int(x + 29), 79)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#192239"))
        p.drawPolygon(QPolygonF([
            QPointF(0, 110), QPointF(960, 110), QPointF(960, 300), QPointF(0, 300)]))
        p.setBrush(QColor("#222d48"))
        p.drawPolygon(QPolygonF([
            QPointF(80, 105), QPointF(880, 105), QPointF(955, 294), QPointF(4, 294)]))
        p.setPen(QPen(QColor("#303c57"), 1))
        for y in (150, 193, 242):
            p.drawLine(0, y, 960, y)
        # Furnish four workstations with monitors, AI figures and status LEDs.
        for i, (name, status, accent) in enumerate(self._state):
            x = 44 + i * 231
            self._round(p, x, 122, 203, 145, "#101a31", 12)
            self._round(p, x + 7, 129, 189, 130, "#192540", 10)
            # Face and torso of a stylized employee, no fake real-person identity.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(accent))
            p.drawEllipse(QRectF(x + 21, 148, 32, 32))
            self._round(p, x + 16, 181, 42, 27, accent, 13)
            # Desk monitor
            self._round(p, x + 79, 142, 103, 63, "#080f20", 6)
            self._round(p, x + 85, 148, 90, 46, "#243c56", 4)
            p.setPen(QPen(QColor(accent), 3))
            p.drawLine(int(x + 92), 177, int(x + 112), 166)
            p.drawLine(int(x + 112), 166, int(x + 130), 175)
            p.drawLine(int(x + 130), 175, int(x + 158), 155)
            self._round(p, x + 124, 203, 12, 12, "#52607a", 1)
            self._round(p, x + 102, 216, 58, 5, "#4d5a79", 2)
            self._round(p, x + 13, 224, 176, 3, "#485875", 1)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            p.setPen(QColor(INK))
            p.drawText(QRectF(x + 12, 231, 182, 16), Qt.AlignmentFlag.AlignLeft, name)
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor(accent))
            p.drawText(QRectF(x + 12, 245, 182, 17), Qt.AlignmentFlag.AlignLeft, status[:32])
        p.end()

class PnLChart(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(180)
        self.deals = []
    def set_deals(self, deals):
        self.deals = list(deals)
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        p.fillRect(rect, QColor("#111a31"))
        w, h = rect.width(), rect.height()
        left, right, top, bottom = 48, 24, 20, 31
        plot_w, plot_h = max(10, w-left-right), max(10, h-top-bottom)
        for n in range(4):
            y = top + n * plot_h / 3
            p.setPen(QPen(QColor("#33425c"), 1))
            p.drawLine(int(left), int(y), int(w-right), int(y))
        if not self.deals:
            p.setPen(QColor(MUTED))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                       "Belum ada histori trading untuk membuat grafik")
            p.end()
            return
        daily = defaultdict(float)
        for d in self.deals:
            date = datetime.fromtimestamp(d["time"], tz=timezone.utc).date()
            daily[date] += d["net"]
        values = [0.0]
        for date in sorted(daily):
            values.append(values[-1] + daily[date])
        low, high = min(0, *values), max(0, *values)
        if abs(high-low) < 0.001:
            high += 1
            low -= 1
        def xy(i, value):
            return QPointF(left + i/(len(values)-1) * plot_w,
                           top + (high-value)/(high-low) * plot_h)
        points = [xy(i, val) for i, val in enumerate(values)]
        color = QColor(POSITIVE if values[-1] >= 0 else NEGATIVE)
        p.setPen(QPen(QColor("#7181a3"), 1))
        zero = xy(0, 0).y()
        p.drawLine(int(left), int(zero), int(w-right), int(zero))
        p.setPen(QPen(color, 2.8))
        for a, b in zip(points, points[1:]):
            p.drawLine(a,b)
        p.setBrush(color)
        p.drawEllipse(points[-1], 4, 4)
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(4, 4, 72, 18), Qt.AlignmentFlag.AlignLeft, f"{high:+,.2f}")
        p.drawText(QRectF(4, h-55, 72, 18), Qt.AlignmentFlag.AlignLeft, f"{low:+,.2f}")
        p.drawText(QRectF(left, h-25, plot_w, 20), Qt.AlignmentFlag.AlignLeft,
                   "UTC  •  Akumulasi realized net P&L (trading deals)")
        p.end()

class SnapshotWorker(QThread):
    ready = Signal(object)
    error = Signal(str)
    def __init__(self, cfg, days, parent=None):
        super().__init__(parent)
        self.cfg, self.days = cfg, days
    def run(self):
        try:
            self.ready.emit(make_snapshot(self.cfg, self.days))
        except Exception as exc:
            self.error.emit(type(exc).__name__ + ": " + str(exc))

class OfficeView(QWidget):
    analyze_requested = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.cfg = Settings.load()
        self.snapshot = None
        self._build()
        self.update_roles()
        if os.environ.get("LUMAVUN_OFFICE_SMOKE") != "1":
            QTimer.singleShot(500, self.refresh)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{border:none;background:#0c1121;}")
        contents = QWidget()
        contents.setStyleSheet("background:#0c1121;")
        v = QVBoxLayout(contents)
        v.setContentsMargins(18, 19, 18, 24)
        v.setSpacing(15)

        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.addWidget(_label("LUMAVUN  /  AI TRADING OFFICE", INK, 24, True))
        headings.addWidget(_label("A workspace for signals, risk decisions and real MT5 performance.",
                                  MUTED, 11))
        header.addLayout(headings, 1)
        self.time_range = QComboBox()
        for txt, n in (("Hari ini (UTC)", 1), ("7 hari (UTC)", 7), ("30 hari (UTC)", 30),
                       ("90 hari (UTC)", 90)):
            self.time_range.addItem(txt, n)
        self.time_range.setCurrentIndex(2)
        self.time_range.currentIndexChanged.connect(lambda *_: self.refresh())
        header.addWidget(self.time_range)
        refresh = QPushButton("↻ Refresh MT5")
        refresh.setObjectName("muted")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        v.addLayout(header)

        self.sync = _label("Data akun belum dimuat • Semua nilai tetap kosong sampai MT5 terhubung.", GOLD, 11)
        v.addWidget(self.sync)
        metrics = QGridLayout()
        metrics.setSpacing(10)
        specs = [
            ("balance", "Account balance", "Dana akun"),
            ("equity", "Account equity", "Balance + floating & adjustments"),
            ("floating", "Floating P&L", "Posisi terbuka"),
            ("realized", "Realized net P&L", "Setelah biaya perdagangan"),
            ("wins", "Profit / loss deals", "Jumlah deal exit untung / rugi"),
            ("win_rate", "Win rate", "Deal exit pada periode"),
        ]
        self.cards = {}
        for i,(key,name,caption) in enumerate(specs):
            card = MetricCard(name,caption)
            metrics.addWidget(card,i//3,i%3)
            self.cards[key]=card
        v.addLayout(metrics)

        office_heading = QHBoxLayout()
        office_heading.addWidget(_label("THE TRADING FLOOR", INK, 15, True))
        office_heading.addStretch()
        office_heading.addWidget(_label("Peran visual mengikuti status nyata aplikasi", MUTED, 10))
        v.addLayout(office_heading)

        middle = QHBoxLayout()
        middle.setSpacing(12)
        scene_panel = _panel()
        scene_layout = QVBoxLayout(scene_panel)
        scene_layout.setContentsMargins(9,9,9,9)
        self.scene=OfficeScene()
        scene_layout.addWidget(self.scene)
        middle.addWidget(scene_panel, 3)

        goals = _panel()
        gl = QVBoxLayout(goals)
        gl.setContentsMargins(17,15,17,17)
        gl.setSpacing(8)
        gl.addWidget(_label("PROFIT TARGET", GOLD, 13, True))
        gl.addWidget(_label("Monitoring profit yang sudah terealisasi, bukan janji hasil.", MUTED, 10))
        self.target_amount=QDoubleSpinBox()
        self.target_amount.setRange(0, 1000000000)
        self.target_amount.setDecimals(2)
        self.target_amount.setSingleStep(1)
        self.target_amount.setValue(self.cfg.profit_target_amount)
        gl.addWidget(_label("Target (mata uang akun)", MUTED, 10))
        gl.addWidget(self.target_amount)
        self.target_period=QComboBox()
        for name, data in (("Harian / UTC", "day"), ("Mingguan / UTC", "week"), ("Bulanan / UTC", "month")):
            self.target_period.addItem(name, data)
        self.target_period.setCurrentIndex(max(0,self.target_period.findData(self.cfg.profit_target_period)))
        gl.addWidget(self.target_period)
        self.pause_target=QCheckBox("Stop auto trading saat target tercapai")
        self.pause_target.setChecked(self.cfg.pause_at_profit_target)
        gl.addWidget(self.pause_target)
        save=QPushButton("Save Target")
        save.clicked.connect(self.save_target)
        gl.addWidget(save)
        self.target_status=_label("Menunggu data history broker", MUTED, 11)
        gl.addWidget(self.target_status)
        self.progress=QProgressBar()
        self.progress.setRange(0,100)
        self.progress.setTextVisible(True)
        self.progress.setValue(0)
        self.progress.setFormat("Belum tersedia")
        self.progress.setStyleSheet(
            "QProgressBar{background:#283149;color:#edf1fb;border:0;border-radius:6px;"
            "text-align:center;height:16px;}"
            "QProgressBar::chunk{background:#9777e9;border-radius:6px;}")
        gl.addWidget(self.progress)
        gl.addStretch()
        middle.addWidget(goals, 1)
        v.addLayout(middle)

        activity = _panel()
        av=QVBoxLayout(activity)
        av.setContentsMargins(15,14,15,14)
        self.agent_status=_label("AI Analyst: idle  •  Risk Guard: on  •  Executor: disarmed",MUTED,11)
        av.addWidget(self.agent_status)
        actions=QHBoxLayout()
        btn=QPushButton("Ask AI Analyst • Analyze")
        btn.clicked.connect(self.analyze_requested.emit)
        actions.addWidget(btn)
        actions.addWidget(_label("Risk check + human authorization before any order", MUTED, 10))
        actions.addStretch()
        av.addLayout(actions)
        v.addWidget(activity)

        ch=_panel()
        cv=QVBoxLayout(ch)
        cv.setContentsMargins(15,14,15,13)
        cv.addWidget(_label("PERFORMANCE DESK  /  NET P&L CURVE",INK,14,True))
        self.chart=PnLChart()
        cv.addWidget(self.chart)
        v.addWidget(ch)

        hist=_panel()
        hv=QVBoxLayout(hist)
        hv.setContentsMargins(15,13,15,16)
        hv.addWidget(_label("TRADE JOURNAL  /  HISTORI PROFIT & LOSS",INK,14,True))
        self.history_note=_label(
            "Belum ada histori. Semua angka diambil dari transaksi MT5, tanpa data simulasi.",MUTED,10)
        hv.addWidget(self.history_note)
        self.table=QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(
            ["Time (UTC)", "Deal", "Symbol", "Side", "Event", "Volume", "Net P&L"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(285)
        self.table.setStyleSheet(
            "QTableWidget{background:#10192b;alternate-background-color:#172139;"
            "gridline-color:#24314b;border:1px solid #263450;border-radius:6px;}"
            "QHeaderView::section{background:#242d46;color:#b8c4df;border:0;"
            "padding:8px;font-weight:bold;}")
        hv.addWidget(self.table)
        v.addWidget(hist)
        scroll.setWidget(contents)
        root.addWidget(scroll)

    def update_roles(self, analyst="Ready", performance=None):
        cfg=Settings.load()
        if cfg.mt5_mode == "mt5_native":
            executor="Native MCP: read only"
        elif not cfg.execution_enabled:
            executor="Disarmed"
        else:
            executor="LIVE authorized" if cfg.live_allowed else "Demo armed"
        risk="Limits on"
        perf=performance or ("Synced" if self.snapshot is not None else "Awaiting MT5")
        self.scene.update_states(analyst,risk,executor,perf)
        self.agent_status.setText(
            f"AI Analyst: {analyst}    •    Risk Guard: {risk}"
            f"    •    Trade Executor: {executor}    •    Performance: {perf}"
        )

    def save_target(self):
        cfg=Settings.load()
        cfg.profit_target_amount=self.target_amount.value()
        cfg.profit_target_period=self.target_period.currentData()
        cfg.pause_at_profit_target=self.pause_target.isChecked()
        cfg.save()
        self.cfg=cfg
        self.target_status.setText("Target disimpan. Refresh untuk menghitung capaian.")
        self.refresh()

    def refresh(self):
        if self.worker is not None and self.worker.isRunning():
            return
        cfg=Settings.load()
        self.cfg=cfg
        self.sync.setText("Mengambil balance, equity, posisi dan histori broker...")
        self.update_roles(performance="Syncing")
        worker=SnapshotWorker(cfg,self.time_range.currentData(),self)
        self.worker=worker
        worker.ready.connect(self._show_snapshot)
        worker.error.connect(self._show_error)
        worker.finished.connect(self._cleanup)
        worker.start()

    def _cleanup(self):
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker=None

    def _show_error(self, error):
        self.snapshot=None
        self.sync.setText("MT5 belum tersinkron: " + error[:220])
        for card in self.cards.values():
            card.set_value("—",MUTED)
        self.table.setRowCount(0)
        self.chart.set_deals([])
        self.progress.setValue(0)
        self.progress.setFormat("Belum tersedia")
        self.target_status.setText("Tidak dapat menghitung target tanpa histori broker.")
        self.update_roles(performance="Connection error")

    def _show_snapshot(self, data):
        self.snapshot=data
        acct=data["account"]
        curr=str(acct.get("currency") or "")
        self.sync.setText(
            "Broker: " + str(acct.get("server") or "unknown")
            + "  •  Account: " + str(acct.get("login") or "unknown")
            + "  •  Mode: " + ("DEMO" if acct.get("demo") is True else
                              "LIVE" if acct.get("demo") is False else "UNKNOWN")
            + "  •  Refreshed: " + data["updated_at"][:19].replace("T"," ") + " UTC"
        )
        self.cards["balance"].set_value(_money(acct.get("balance"),curr))
        self.cards["equity"].set_value(_money(acct.get("equity"),curr))
        floating=data["floating"]
        self.cards["floating"].set_value(_money(floating,curr,True),_tint(floating))
        hist=data["history"]
        realized=hist["realized"]
        self.cards["realized"].set_value(_money(realized,curr,True),_tint(realized))
        counts=("—" if hist["wins"] is None else
                f"{hist['wins']} profit  /  {hist['losses']} loss")
        self.cards["wins"].set_value(counts)
        wr=hist["win_rate"]
        self.cards["win_rate"].set_value(f"{wr:.1f}%" if wr is not None else "—")
        if data["history_available"]:
            deals=hist["deals"]
            self.chart.set_deals(deals)
            self._set_table(deals,curr)
            self.history_note.setText(
                f"{len(deals)} trading deals pada {data['window_days']} hari terakhir (UTC). "
                "Net P&L termasuk profit, komisi, swap dan fee; transaksi deposit/withdrawal dikecualikan."
            )
            self._show_target(data,curr)
        else:
            self.chart.set_deals([])
            self.table.setRowCount(0)
            self.history_note.setText("Histori tidak tersedia: " + str(data["history_error"] or "Unknown"))
            self.progress.setValue(0)
            self.progress.setFormat("No history")
            self.target_status.setText("Tidak dapat menghitung target profit tanpa data history.")
        self.update_roles(performance="Synced")

    def _show_target(self,data,currency):
        goal=data["target_amount"]
        if goal<=0:
            self.progress.setValue(0)
            self.progress.setFormat("Target not set")
            self.target_status.setText("Isi target profit di atas, lalu Save Target.")
            return
        achieved=data["target_realized"]
        progress=data["progress"]
        self.progress.setValue(int(progress))
        self.progress.setFormat(f"{progress:.1f}%")
        remaining=max(0, goal-achieved)
        label="TARGET REACHED" if data["target_reached"] else "Remaining " + _money(remaining,currency)
        self.target_status.setText(
            _money(achieved,currency,True) + " / " + _money(goal,currency) + " • " + label
        )

    def _set_table(self,deals,currency):
        recent=list(reversed(deals[-200:]))
        self.table.setRowCount(len(recent))
        for i, d in enumerate(recent):
            ts=datetime.fromtimestamp(d["time"],timezone.utc).strftime("%Y-%m-%d %H:%M")
            parts=[ts,d["ticket"],d["symbol"],d["side"],
                   "EXIT" if d["is_exit"] else "ENTRY",f"{d['volume']:g}",
                   _money(d["net"],currency,True)]
            for j,value in enumerate(parts):
                cell=QTableWidgetItem(str(value))
                if j==6:
                    cell.setForeground(QColor(_tint(d["net"])))
                self.table.setItem(i,j,cell)
