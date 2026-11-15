"""LUMAVUN Trade Server desktop UI (PySide6)."""
from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)
from .config import Settings, PROVIDER_URLS, put_api_key
from .gateway_auth import save_remote_key, save_native_api_key, validate_endpoint
from .mt5_access import gateway_call
from .native_mt5 import inspect_connection
from .ai import discover_models
from .engine import run_strategy_once
from .mt5_access import account_status, list_positions

STYLESHEET = """
QWidget { background:#0c1121; color:#e7e8f5; font-family:'Segoe UI'; font-size:13px; }
QMainWindow { background:#0c1121; }
QLabel#heading { color:#faf8ff; font-size:24px; font-weight:700; }
QLabel#subtitle { color:#a6adc5; font-size:12px; }
QGroupBox { border:1px solid #323752; border-radius:9px; margin-top:12px;
            padding:14px 12px 10px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 7px; color:#cfc2ff; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
  background:#151c30; border:1px solid #3e4563; border-radius:6px;
  padding:7px; selection-background-color:#6352b9; }
QPushButton { background:#5142a3; color:#fff; font-weight:600;
              border:1px solid #6654ba; border-radius:7px; padding:9px 14px; }
QPushButton:hover { background:#6757c0; }
QPushButton:disabled { color:#9ca0b0; background:#2b3046; }
QPushButton#danger { background:#88314f; border-color:#aa4264; }
QPushButton#muted { background:#222b41; border-color:#394760; }
QTabWidget::pane { border:1px solid #303751; border-radius:8px; }
QTabBar::tab { background:#151b30; border:1px solid #303751; padding:11px 17px; }
QTabBar::tab:selected { background:#413879; }
QCheckBox { spacing:8px; }
"""
class Task(QThread):
    done = Signal(object)
    failed = Signal(str)
    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as exc:
            self.failed.emit(type(exc).__name__ + ": " + str(exc))

def spin_double(value, minimum, maximum, step, decimals=2):
    w = QDoubleSpinBox()
    w.setRange(minimum, maximum)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(value)
    return w

def spin_int(value, minimum, maximum):
    w = QSpinBox()
    w.setRange(minimum, maximum)
    w.setValue(value)
    return w

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LUMAVUN Trade Server | AI + MT5 MCP")
        self.setMinimumSize(950, 720)
        self.resize(1060, 800)
        self.cfg = Settings.load()
        self.tasks = []
        self.busy = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.run_ai)
        self._build()

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 18, 24, 24)
        title = QLabel("LUMAVUN  /  TRADE SERVER")
        title.setObjectName("heading")
        layout.addWidget(title)
        subtitle = QLabel("Windows trading workstation  •  Custom AI  •  MetaTrader 5  •  Local MCP")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._dashboard()
        self._ai_tab()
        self._strategy_tab()
        self._risk_tab()
        self._mcp_tab()
        self.statusBar().showMessage("Preview mode by default. No order is sent without explicit arming.")

    def _dashboard(self):
        page = QWidget()
        pane = QVBoxLayout(page)
        status = QGroupBox("MT5 Account / Terminal")
        status_layout = QVBoxLayout(status)
        self.connection = QLabel("Not checked. Open and log in to the MT5 desktop terminal.")
        self.connection.setWordWrap(True)
        status_layout.addWidget(self.connection)
        row = QHBoxLayout()
        connect = QPushButton("Check MT5 Connection")
        connect.clicked.connect(self.check_mt5)
        row.addWidget(connect)
        positions = QPushButton("Refresh Positions")
        positions.setObjectName("muted")
        positions.clicked.connect(self.check_positions)
        row.addWidget(positions)
        status_layout.addLayout(row)
        pane.addWidget(status)

        control = QGroupBox("AI Strategy Control")
        ctl = QVBoxLayout(control)
        self.arm_status = QLabel()
        ctl.addWidget(self.arm_status)
        row2 = QHBoxLayout()
        once = QPushButton("Analyze One Closed Candle")
        once.clicked.connect(self.run_ai)
        row2.addWidget(once)
        self.auto_button = QPushButton("Start Auto Scan")
        self.auto_button.setObjectName("muted")
        self.auto_button.clicked.connect(self.toggle_auto)
        row2.addWidget(self.auto_button)
        ctl.addLayout(row2)
        row3 = QHBoxLayout()
        arm = QPushButton("Arm DEMO Execution")
        self.arm_demo_btn = arm
        arm.clicked.connect(self.arm_demo)
        row3.addWidget(arm)
        self.disarm_btn = QPushButton("EMERGENCY DISARM")
        self.disarm_btn.setObjectName("danger")
        self.disarm_btn.clicked.connect(self.disarm)
        row3.addWidget(self.disarm_btn)
        ctl.addLayout(row3)
        live = QPushButton("Enable LIVE Orders (separate confirmation)")
        self.arm_live_btn = live
        live.setObjectName("danger")
        live.clicked.connect(self.arm_live)
        ctl.addWidget(live)
        pane.addWidget(control)

        logs = QGroupBox("Activity / Signal / Order Result")
        logs_layout = QVBoxLayout(logs)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("AI output, risk rejections and MT5 order results appear here.")
        logs_layout.addWidget(self.log_box)
        pane.addWidget(logs, 1)
        self.tabs.addTab(page, "Dashboard")
        self.update_arm_label()

    def _ai_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        group = QGroupBox("Bring Your Own AI")
        form = QFormLayout(group)
        self.provider = QComboBox()
        self.provider.addItems(PROVIDER_URLS.keys())
        self.provider.setCurrentText(self.cfg.provider)
        self.provider.currentTextChanged.connect(self.provider_changed)
        form.addRow("Provider", self.provider)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setCurrentText(self.cfg.model)
        form.addRow("Model ID", self.model)
        self.base_url = QLineEdit(self.cfg.base_url)
        self.base_url.setPlaceholderText("Leave blank for default API endpoint")
        form.addRow("Custom base URL", self.base_url)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Stored in Windows Credential Manager, not in settings.json")
        form.addRow("Provider API key", self.api_key)
        buttons = QHBoxLayout()
        save = QPushButton("Save AI Settings / Key")
        save.clicked.connect(self.save_ai)
        buttons.addWidget(save)
        fetch = QPushButton("Fetch Available Models")
        fetch.setObjectName("muted")
        fetch.clicked.connect(self.load_models)
        buttons.addWidget(fetch)
        form.addRow(buttons)
        self.ai_notice = QLabel("OpenAI-compatible providers use /models and /chat/completions. "
                                "Anthropic, Gemini and Ollama have native adapters.")
        self.ai_notice.setWordWrap(True)
        form.addRow(self.ai_notice)
        layout.addWidget(group)
        layout.addStretch()
        self.tabs.addTab(page, "AI Providers")

    def _strategy_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        symbol_row = QHBoxLayout()
        symbol_row.addWidget(QLabel("Broker Symbol:"))
        self.symbol = QLineEdit(self.cfg.symbol)
        symbol_row.addWidget(self.symbol)
        symbol_row.addWidget(QLabel("Timeframe:"))
        self.timeframe = QComboBox()
        self.timeframe.addItems(("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
        self.timeframe.setCurrentText(self.cfg.timeframe)
        symbol_row.addWidget(self.timeframe)
        layout.addLayout(symbol_row)
        layout.addWidget(QLabel("Strategy instructions (plain Indonesian / English):"))
        self.strategy = QPlainTextEdit(self.cfg.strategy)
        layout.addWidget(self.strategy, 1)
        btn = QPushButton("Save Strategy")
        btn.clicked.connect(self.save_strategy)
        layout.addWidget(btn)
        note = QLabel("AI evaluates closed candles. A BUY/SELL proposal must pass all deterministic risk checks. "
                      "A saved strategy does not automatically authorize trading.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs.addTab(page, "Strategy Editor")

    def _risk_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        group = QGroupBox("Hard Risk Limits (cannot be overridden by an AI response)")
        form = QFormLayout(group)
        self.allow_symbols = QLineEdit(self.cfg.allow_symbols)
        form.addRow("Allowed symbols (comma-separated)", self.allow_symbols)
        self.risk = spin_double(self.cfg.risk_per_trade_pct, 0.01, 2, 0.05)
        form.addRow("Max risk / trade (% equity)", self.risk)
        self.daily_loss = spin_double(self.cfg.max_daily_loss_pct, 0.1, 15, 0.5)
        form.addRow("Max realized daily loss (% equity)", self.daily_loss)
        self.spread = spin_double(self.cfg.max_spread_points, 1, 10000, 1, 1)
        form.addRow("Max spread (symbol points)", self.spread)
        self.max_lot = spin_double(self.cfg.max_lot, 0.01, 100, 0.01, 2)
        form.addRow("Absolute maximum lot", self.max_lot)
        self.max_positions = spin_int(self.cfg.max_positions, 1, 100)
        form.addRow("Maximum all-account open positions", self.max_positions)
        self.max_trades = spin_int(self.cfg.max_trades_day, 1, 100)
        form.addRow("Maximum bot entries per day", self.max_trades)
        self.scan_interval = spin_int(self.cfg.scan_interval_seconds, 30, 3600)
        form.addRow("Scan interval (seconds)", self.scan_interval)
        layout.addWidget(group)
        save = QPushButton("Save Hard Limits")
        save.clicked.connect(self.save_risk)
        layout.addWidget(save)
        layout.addWidget(QLabel("Orders require valid SL and TP, minimum 1.5R, current quote, broker order_check, "
                                "and the broker's own lot minimum. If minimum lot is too large for the risk budget, "
                                "no order is sent. No guarantee against slippage or gaps."))
        layout.addStretch()
        self.tabs.addTab(page, "Risk Guard")

    def _mcp_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        group = QGroupBox("MCP Server for External AI Agents")
        inner = QVBoxLayout(group)
        inner.addWidget(QLabel("Pilih Native MetaTrader 5 MCP untuk menggunakan SERVER dan API KEY dari MT5 → Options → MCP.\n"
                               "Server MCP bawaan MT5 berbeda dari Gateway LUMAVUN (opsional).\n"
                               "Kunci tidak pernah disimpan di pengaturan biasa."))
        connection = QGroupBox("MT5 Connection: Local Terminal or Internal MCP Server")
        form = QFormLayout(connection)
        self.mt5_mode = QComboBox()
        self.mt5_mode.addItem("Local MT5 Terminal", "local")
        self.mt5_mode.addItem("LUMAVUN HTTP Gateway (legacy)", "mcp_http")
        self.mt5_mode.addItem("MetaTrader 5 Native MCP (built-in)", "mt5_native")
        self.mt5_mode.setCurrentIndex(2 if self.cfg.mt5_mode == "mt5_native" else
                                      1 if self.cfg.mt5_mode == "mcp_http" else 0)
        self.mt5_mode.currentIndexChanged.connect(self.connection_mode_changed)
        form.addRow("Connection mode", self.mt5_mode)
        self.mt5_url = QLineEdit(self.cfg.mt5_native_url if self.cfg.mt5_mode == "mt5_native"
                                 else self.cfg.mt5_mcp_url)
        self.mt5_url.setPlaceholderText("http://127.0.0.1:22346/mcp")
        form.addRow("MCP server URL", self.mt5_url)
        self.mt5_remote_key = QLineEdit()
        self.mt5_remote_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.mt5_remote_key.setPlaceholderText("API key dari MT5 → Options → MCP (atau Gateway jika dipilih)")
        form.addRow("MCP API Key", self.mt5_remote_key)
        buttons = QHBoxLayout()
        save = QPushButton("Save Connection")
        save.clicked.connect(self.save_mt5_connection)
        buttons.addWidget(save)
        test = QPushButton("Test MCP Connection")
        test.setObjectName("muted")
        test.clicked.connect(self.test_mcp_connection)
        buttons.addWidget(test)
        form.addRow(buttons)
        note = QLabel("Untuk mode Native, aktifkan 'server internal' di tab MCP MT5, salin Alamat dan Kunci API, "
                      "klik OK pada MT5, lalu Test MCP Connection. Tampilkan daftar tool untuk memeriksa kontrak "
                      "yang disediakan server. Auto-order lewat MCP native belum diaktifkan sampai validasi risikonya lengkap.")
        note.setWordWrap(True)
        form.addRow(note)
        inner.addWidget(connection)
        inner.addWidget(QLabel("Discovered Native MetaTrader Tools (read-only display):"))
        self.native_tools_preview = QPlainTextEdit()
        self.native_tools_preview.setReadOnly(True)
        self.native_tools_preview.setMinimumHeight(170)
        self.native_tools_preview.setPlaceholderText("Test MCP Connection untuk menampilkan daftar tool MT5 native.")
        inner.addWidget(self.native_tools_preview)
        self.mcp_orders = QCheckBox("Allow external MCP clients to place risk-checked orders when execution is armed")
        self.mcp_orders.setChecked(self.cfg.allow_mcp_orders)
        self.mcp_orders.toggled.connect(self.set_mcp_orders)
        inner.addWidget(self.mcp_orders)
        inner.addWidget(QLabel("Example client configuration (replace the file path):"))
        sample = {
            "mcpServers": {
                "lumavun-mt5": {
                    "command": r"C:\LUMAVUN\Lumavun-MT5-MCP.exe",
                    "args": []
                }
            }
        }
        example = QPlainTextEdit(json.dumps(sample, indent=2))
        example.setReadOnly(True)
        example.setMinimumHeight(140)
        inner.addWidget(example)
        inner.addWidget(QLabel("Available tools: mt5_account, mt5_positions, mt5_candles,\n"
                               "mt5_order_preview, mt5_place_order. Trading is OFF by default."))
        layout.addWidget(group)
        layout.addStretch()
        self.tabs.addTab(page, "MT5 MCP")
        self.refresh_mcp_arming()

    def connection_mode_changed(self):
        mode = self.mt5_mode.currentData()
        cfg = Settings.load()
        self.mt5_url.setText(cfg.mt5_native_url if mode == "mt5_native" else cfg.mt5_mcp_url)
        self.mt5_remote_key.clear()
        self.refresh_mcp_arming()

    def refresh_mcp_arming(self):
        native = self.mt5_mode.currentData() == "mt5_native"
        self.arm_demo_btn.setEnabled(not native)
        self.arm_live_btn.setEnabled(not native)
        if native:
            self.arm_status.setText("Execution status: NATIVE MCP READ-ONLY (signals only; no orders)")
        else:
            self.update_arm_label()

    def save_mt5_connection(self):
        cfg = Settings.load()
        cfg.mt5_mode = self.mt5_mode.currentData()
        entered_url = self.mt5_url.text().strip()
        try:
            if cfg.mt5_mode == "mt5_native":
                cfg.mt5_native_url = validate_endpoint(entered_url)
            elif cfg.mt5_mode == "mcp_http":
                cfg.mt5_mcp_url = validate_endpoint(entered_url)
            if self.mt5_remote_key.text().strip():
                if cfg.mt5_mode == "mt5_native":
                    save_native_api_key(self.mt5_remote_key.text())
                elif cfg.mt5_mode == "mcp_http":
                    save_remote_key(self.mt5_remote_key.text())
                self.mt5_remote_key.clear()
        except Exception as exc:
            self.log("Invalid MCP connection: " + str(exc))
            return False
        if cfg.mt5_mode == "mt5_native":
            cfg.execution_enabled = False
            cfg.live_allowed = False
        cfg.save()
        self.refresh_mcp_arming()
        self.log("MT5 connection mode saved: " + cfg.mt5_mode)
        return True

    def test_mcp_connection(self):
        if self.mt5_mode.currentData() == "local":
            self.log("Pilih MetaTrader 5 Native MCP atau LUMAVUN Gateway terlebih dahulu.")
            return
        if not self.save_mt5_connection():
            return
        if self.mt5_mode.currentData() == "mt5_native":
            def report_native(info):
                self.native_tools_preview.setPlainText(
                    "\n".join(x["name"] + " | " + ", ".join(x["required"])
                              for x in info["tools"]))
                if info.get("account"):
                    self.connection.setText(json.dumps(info["account"], indent=2, ensure_ascii=False))
                self.log("Native MT5 MCP connected: " + str(info["total_tools"]) + " tools found (read-only).")
            self.task(lambda: inspect_connection(Settings.load()), report_native)
            return
        def report_gateway(status):
            self.connection.setText(json.dumps(status, indent=2))
            self.log("Authenticated LUMAVUN MCP Gateway connected (" +
                     ("DEMO" if status.get("demo") is True else "LIVE/UNKNOWN") + ")")
        self.task(lambda: gateway_call("mt5_account", {}, Settings.load()), report_gateway)

    def log(self, msg):
        self.log_box.appendPlainText(str(msg))
        self.statusBar().showMessage(str(msg)[:180])

    def task(self, fn, on_done):
        if self.busy:
            self.log("An operation is already running.")
            return
        self.busy = True
        t = Task(fn, self)
        self.tasks.append(t)
        def ok(result):
            self.busy = False
            on_done(result)
        def fail(error):
            self.busy = False
            self.log("ERROR: " + error)
        def cleanup():
            self.tasks.remove(t)
            t.deleteLater()
        t.done.connect(ok)
        t.failed.connect(fail)
        t.finished.connect(cleanup)
        t.start()

    def save_ai(self):
        cfg = Settings.load()
        cfg.provider = self.provider.currentText()
        cfg.model = self.model.currentText().strip()
        cfg.base_url = self.base_url.text().strip()
        if self.api_key.text().strip():
            try:
                put_api_key(cfg.provider, self.api_key.text())
            except Exception as exc:
                self.log("Could not store API key: " + str(exc))
                return
            self.api_key.clear()
        cfg.save()
        self.log("AI configuration saved. API key is stored separately, if supplied.")

    def provider_changed(self, provider):
        self.model.clear()
        self.base_url.clear()
        self.api_key.clear()
        self.ai_notice.setText("Default endpoint: " + PROVIDER_URLS.get(provider, "Please provide a HTTPS base URL"))

    def load_models(self):
        self.save_ai()
        self.task(lambda: discover_models(Settings.load()), self.show_models)

    def show_models(self, models):
        prior = self.model.currentText()
        self.model.clear()
        self.model.addItems(models)
        if prior in models:
            self.model.setCurrentText(prior)
        elif models:
            self.model.setCurrentIndex(0)
        self.log("Fetched " + str(len(models)) + " available models. Save the selected model to use it.")

    def save_strategy(self):
        cfg = Settings.load()
        cfg.symbol = self.symbol.text().strip()
        cfg.timeframe = self.timeframe.currentText()
        cfg.strategy = self.strategy.toPlainText().strip()
        if not cfg.symbol or not cfg.strategy:
            self.log("Symbol and strategy cannot be empty.")
            return
        cfg.last_signal_bar = ""
        cfg.save()
        self.log("Strategy saved. Signal cache reset.")

    def save_risk(self):
        cfg = Settings.load()
        cfg.allow_symbols = self.allow_symbols.text().strip()
        cfg.risk_per_trade_pct = self.risk.value()
        cfg.max_daily_loss_pct = self.daily_loss.value()
        cfg.max_spread_points = self.spread.value()
        cfg.max_lot = self.max_lot.value()
        cfg.max_positions = self.max_positions.value()
        cfg.max_trades_day = self.max_trades.value()
        cfg.scan_interval_seconds = self.scan_interval.value()
        cfg.save()
        if self.timer.isActive():
            self.timer.setInterval(cfg.scan_interval_seconds * 1000)
        self.log("Hard risk limits saved.")

    def check_mt5(self):
        def show(status):
            self.connection.setText(json.dumps(status, indent=2))
            self.log("MT5 connection checked (" + ("DEMO" if status.get("demo") is True else "LIVE" if status.get("demo") is False else "UNKNOWN") + ")")
        self.task(lambda: account_status(Settings.load()), show)

    def check_positions(self):
        self.task(lambda: list_positions(Settings.load()), lambda positions: self.log(
            "Positions: " + json.dumps(positions, ensure_ascii=False)))

    def run_ai(self):
        if self.busy:
            return
        self.log("Analyzing latest CLOSED candle with configured AI...")
        self.task(run_strategy_once, lambda result: self.log(
            json.dumps(result, indent=2, ensure_ascii=False)))

    def toggle_auto(self):
        if self.timer.isActive():
            self.timer.stop()
            self.auto_button.setText("Start Auto Scan")
            self.log("Automatic scanning stopped.")
        else:
            cfg = Settings.load()
            self.timer.start(cfg.scan_interval_seconds * 1000)
            self.auto_button.setText("Stop Auto Scan")
            self.log("Automatic scan active, every " + str(cfg.scan_interval_seconds) + " seconds.")
            self.run_ai()

    def update_arm_label(self):
        cfg = Settings.load()
        state = ("DISARMED" if not cfg.execution_enabled else
                 "LIVE ALLOWED (HIGH RISK)" if cfg.live_allowed else "ARMED: DEMO ONLY")
        self.arm_status.setText("Execution status: " + state)

    def arm_demo(self):
        if QMessageBox.question(self, "Arm demo trading?",
            "Allow this application to place orders on DEMO accounts only?\n"
            "The risk guard still applies; demo losses are possible.") != QMessageBox.StandardButton.Yes:
            return
        cfg = Settings.load()
        cfg.execution_enabled = True
        cfg.live_allowed = False
        cfg.save()
        self.refresh_mcp_arming()
        self.log("DEMO order execution armed. LIVE accounts remain blocked.")

    def arm_live(self):
        phrase, ok = QInputDialog.getText(self, "Danger: LIVE TRADING",
            "Real money can be lost. Type ENABLE LIVE TRADING to authorize LIVE orders:")
        if not ok or phrase != "ENABLE LIVE TRADING":
            self.log("LIVE authorization cancelled.")
            return
        if QMessageBox.warning(self, "Confirm LIVE order authorization",
            "Authorize automatic real-money MT5 orders from AI strategies?\n"
            "This is NOT guaranteed safe or profitable.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        cfg = Settings.load()
        cfg.execution_enabled = True
        cfg.live_allowed = True
        cfg.save()
        self.refresh_mcp_arming()
        self.log("WARNING: LIVE order execution is now authorized.")

    def disarm(self):
        cfg = Settings.load()
        cfg.execution_enabled = False
        cfg.live_allowed = False
        cfg.allow_mcp_orders = False
        cfg.save()
        self.mcp_orders.blockSignals(True)
        self.mcp_orders.setChecked(False)
        self.mcp_orders.blockSignals(False)
        self.refresh_mcp_arming()
        self.log("Execution DISARMED for AI engine and MCP. Existing trades remain open.")

    def set_mcp_orders(self, checked):
        if checked and QMessageBox.warning(self, "MCP order access",
            "Allow any local client with access to this MCP server to submit guarded orders "
            "whenever execution is armed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self.mcp_orders.blockSignals(True)
            self.mcp_orders.setChecked(False)
            self.mcp_orders.blockSignals(False)
            return
        cfg = Settings.load()
        cfg.allow_mcp_orders = checked
        cfg.save()
        self.log("External MCP order access: " + ("allowed with guardrails" if checked else "disabled"))

    def closeEvent(self, event):
        self.timer.stop()
        if self.busy:
            QMessageBox.information(self, "Active task", "An operation is running. Stop after it completes.")
            event.ignore()
            return
        # Prevent unattended order execution after the desktop closes.
        self.disarm()
        event.accept()

def main():
    app = QApplication([])
    app.setStyleSheet(STYLESHEET)
    win = Window()
    win.show()
    app.exec()
