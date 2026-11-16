"""LUMAVUN Trade Server desktop UI (PySide6)."""
from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import QThread, QTimer, Signal, Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)
from .config import Settings, PROVIDER_URLS, put_api_key, SMC_MODELS
from .gateway_auth import save_remote_key, save_native_api_key, validate_endpoint
from .mt5_access import gateway_call
from .native_mt5 import inspect_connection
from .mt5_installer import PY_LAUNCHER_COMMAND, open_install_cmd
from .ai import discover_models
from .engine import run_strategy_once
from .mt5_access import account_status, list_positions, broker_symbols
from .symbols import suggestions
from .office import OfficeView
from .premium_ui import (
    STYLESHEET, PremiumPanel, PageScroll, ResponsiveRow, page_hero, spaced_form,
    hint, make_badge, brand_icon, resource_path,
)

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
        self.setMinimumSize(965, 675)
        self.resize(1390, 860)
        self.setWindowIcon(brand_icon())
        self.cfg = Settings.load()
        self.tasks = []
        self.busy = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.run_ai)
        self._build()

    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 13, 14, 5)
        root.setSpacing(9)
        header = QFrame()
        header.setObjectName("brandHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 12, 19, 12)
        header_layout.setSpacing(15)
        image = QLabel()
        image.setStyleSheet("background:transparent;border:0;")
        image.setFixedSize(68, 68)
        icon = brand_icon()
        image.setPixmap(icon.pixmap(68, 68))
        header_layout.addWidget(image)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        title = QLabel("LUMAVUN  /  TRADE SERVER")
        title.setObjectName("brandTitle")
        texts.addWidget(title)
        subtitle = QLabel("EXECUTIVE AI TRADING WORKSTATION  •  MetaTrader 5  •  Native MCP")
        subtitle.setObjectName("brandSubtitle")
        texts.addWidget(subtitle)
        header_layout.addLayout(texts, 1)
        header_layout.addWidget(make_badge("● PREVIEW / SAFE MODE", "warning"))
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        root.addWidget(self.tabs, 1)

        self.office = OfficeView(self)
        self.office.analyze_requested.connect(self.run_ai)
        self.tabs.addTab(self.office, "▥  Trading Office")
        self._dashboard()
        self._ai_tab()
        self._strategy_tab()
        self._risk_tab()
        self._mcp_tab()
        self.statusBar().showMessage(
            "PREVIEW MODE  •  Orders require explicit permission  •  Native MCP trading is read-only"
        )
        self.statusBar().setSizeGripEnabled(False)

    def _dashboard(self):
        page = PageScroll(self)
        page.add(page_hero(
            "COMMAND CENTER", "Account link, AI analysis and execution controls in one workstation.",
            "Preview is the default. No trade can be sent until execution is explicitly armed."
        ))
        account = PremiumPanel(
            "01  /  MT5 TERMINAL", "Live account connection status and open position reader.",
            accent="gold"
        )
        self.connection = QLabel("Not checked. Open MetaTrader 5 and connect an account.")
        self.connection.setWordWrap(True)
        self.connection.setMinimumHeight(72)
        self.connection.setStyleSheet(
            "color:#cfdbf1; background:#111a33; border:1px solid #47456c;"
            "border-radius:9px; padding:13px; font-family:Consolas;"
        )
        account.layout_body.addWidget(self.connection)
        account_buttons = QHBoxLayout()
        connect = QPushButton("Check MT5 Connection")
        connect.setObjectName("primaryButton")
        connect.clicked.connect(self.check_mt5)
        account_buttons.addWidget(connect)
        positions = QPushButton("Refresh Positions")
        positions.setObjectName("secondaryButton")
        positions.clicked.connect(self.check_positions)
        account_buttons.addWidget(positions)
        account.layout_body.addLayout(account_buttons)
        account.layout_body.addWidget(hint(
            "Pilih mode Local MT5, Gateway, atau Native MCP pada tab MT5 MCP."
        ))

        control = PremiumPanel(
            "02  /  AI TRADE OPERATIONS",
            "Run a one-time closed-candle analysis or manage the automated scanner.",
            accent="violet"
        )
        self.arm_status = make_badge("DISARMED", "warning")
        control.layout_body.addWidget(self.arm_status)
        scan_buttons = QHBoxLayout()
        once = QPushButton("Analyze Closed Candle")
        once.setObjectName("primaryButton")
        once.clicked.connect(self.run_ai)
        scan_buttons.addWidget(once)
        self.auto_button = QPushButton("Start Auto Scan")
        self.auto_button.setObjectName("secondaryButton")
        self.auto_button.clicked.connect(self.toggle_auto)
        scan_buttons.addWidget(self.auto_button)
        control.layout_body.addLayout(scan_buttons)
        controls_row = QHBoxLayout()
        self.arm_demo_btn = QPushButton("Arm DEMO")
        self.arm_demo_btn.clicked.connect(self.arm_demo)
        controls_row.addWidget(self.arm_demo_btn)
        self.disarm_btn = QPushButton("EMERGENCY DISARM")
        self.disarm_btn.setObjectName("danger")
        self.disarm_btn.clicked.connect(self.disarm)
        controls_row.addWidget(self.disarm_btn)
        control.layout_body.addLayout(controls_row)
        self.arm_live_btn = QPushButton("Enable LIVE Orders • Separate Approval")
        self.arm_live_btn.setObjectName("danger")
        self.arm_live_btn.clicked.connect(self.arm_live)
        control.layout_body.addWidget(self.arm_live_btn)
        control.layout_body.addWidget(hint(
            "Danger zone: live orders can lose real money. AI cannot override hard risk limits."
        ))
        page.add(ResponsiveRow(account, control, 2, 2))

        logs = PremiumPanel(
            "03  /  ACTIVITY & AUDIT LOG", "Signal, risk rejection and MT5 execution results.",
            accent="violet"
        )
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(230)
        self.log_box.setPlaceholderText(
            "AI proposal, hard risk validation and order results appear here. "
            "No mock trades or fabricated account values."
        )
        logs.layout_body.addWidget(self.log_box)
        page.add(logs)
        page.end()
        self.tabs.addTab(page, "▦  Dashboard")
        self.update_arm_label()

    def _ai_tab(self):
        page = PageScroll(self)
        page.add(page_hero(
            "CUSTOM AI PROVIDERS",
            "Use a provider model or a private local LLM to analyze closed candles.",
            "API keys remain in the Windows credential vault; only the selected model receives market data."
        ))
        group = PremiumPanel(
            "01  /  MODEL CONNECTION", "Choose provider, model, endpoint and secure credentials.",
            accent="gold"
        )
        form = spaced_form(group)
        self.provider = QComboBox()
        self.provider.addItems(PROVIDER_URLS.keys())
        self.provider.setCurrentText(self.cfg.provider)
        self.provider.currentTextChanged.connect(self.provider_changed)
        form.addRow("AI provider", self.provider)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setCurrentText(self.cfg.model)
        form.addRow("Model identifier", self.model)
        self.base_url = QLineEdit(self.cfg.base_url)
        self.base_url.setPlaceholderText("Optional HTTPS base URL; blank = provider default")
        form.addRow("Endpoint", self.base_url)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Stored securely in Windows Credential Manager")
        form.addRow("API key", self.api_key)
        group.layout_body.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton("Save Provider Settings")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_ai)
        buttons.addWidget(save)
        fetch = QPushButton("Discover Models")
        fetch.setObjectName("secondaryButton")
        fetch.clicked.connect(self.load_models)
        buttons.addWidget(fetch)
        group.layout_body.addLayout(buttons)
        self.ai_notice = hint(
            "OpenAI-compatible providers use model IDs. Anthropic, Gemini, Ollama "
            "and OpenAI Responses have dedicated adapters."
        )
        group.layout_body.addWidget(self.ai_notice)
        guidance = PremiumPanel(
            "02  /  PROVIDER INSTRUCTIONS",
            "Safe setup for cloud API or local Ollama models.", accent="violet"
        )
        guidance.layout_body.addWidget(hint(
            "CLOUD API\n"
            "1. Pilih provider dan simpan API key.\n"
            "2. Klik Discover Models atau isi model ID manual.\n"
            "3. Klik Save Provider Settings untuk mengaktifkan model."
        ))
        guidance.layout_body.addWidget(hint(
            "LOCAL OLLAMA\n"
            "Jalankan Ollama di Windows, pilih Ollama, lalu pilih model lokal.\n"
            "Default endpoint: http://127.0.0.1:11434/v1"
        ))
        guidance.layout_body.addWidget(make_badge("NO API KEY IS LOGGED", "success"))
        guidance.layout_body.addStretch(1)
        page.add(ResponsiveRow(group, guidance, 3, 2))
        page.end()
        self.tabs.addTab(page, "✧  AI Providers")

    def _strategy_tab(self):
        page = PageScroll(self)
        page.add(page_hero(
            "STRATEGY WORKBENCH",
            "Describe the playbook. AI suggests a setup; deterministic safeguards decide what is permitted.",
            "A saved strategy never arms the trade executor automatically."
        ))
        editor = PremiumPanel(
            "01  /  STRATEGY RULES", "Write instructions in Indonesian or English.",
            accent="gold"
        )
        symbols = QHBoxLayout()
        symbols.addWidget(QLabel("Broker symbol"))
        self.symbol = QLineEdit(self.cfg.symbol)
        self.symbol.setPlaceholderText("Broker exact name, e.g. XAUUSDm")
        symbols.addWidget(self.symbol, 2)
        select_symbol = QPushButton("Find Broker Symbol")
        select_symbol.setObjectName("secondaryButton")
        select_symbol.setToolTip("Browse actual symbols supplied by the connected broker")
        select_symbol.clicked.connect(self.browse_broker_symbols)
        symbols.addWidget(select_symbol)
        symbols.addWidget(QLabel("Timeframe"))
        self.timeframe = QComboBox()
        self.timeframe.addItems(("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
        self.timeframe.setCurrentText(self.cfg.timeframe)
        symbols.addWidget(self.timeframe, 1)
        editor.layout_body.addLayout(symbols)
        editor.layout_body.addWidget(hint("Strategy templates (editable; no automatic execution)"))
        self.strategy_preset = QComboBox()
        self.strategy_preset.addItems(SMC_MODELS.keys())
        self.strategy_preset.currentTextChanged.connect(self.apply_strategy_preset)
        editor.layout_body.addWidget(self.strategy_preset)
        editor.layout_body.addWidget(hint(
            "Selecting a preset replaces the editor text. Manual / Custom leaves your text unchanged. "
            "Review and click Save Strategy to persist."
        ))
        editor.layout_body.addWidget(hint("Natural-language strategy"))
        self.strategy = QPlainTextEdit(self.cfg.strategy)
        self.strategy.setMinimumHeight(310)
        editor.layout_body.addWidget(self.strategy)
        save = QPushButton("Save Strategy")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_strategy)
        editor.layout_body.addWidget(save)

        help_card = PremiumPanel(
            "02  /  TRADE PROTOCOL", "How the trade decision moves through the system.",
            accent="violet"
        )
        for step in (
            "01  MARKET DATA\nClosed OHLC candles from the selected MT5 connection.",
            "02  AI ANALYST\nOne structured proposal: BUY, SELL or HOLD with SL and TP.",
            "03  RISK MANAGER\nSpread, lot, equity risk, R:R, allowed symbols and broker limits.",
            "04  EXECUTOR\nDemo or live orders require explicit user permission.",
        ):
            help_card.layout_body.addWidget(hint(step))
        help_card.layout_body.addWidget(make_badge("NO BYPASS OF RISK GUARD", "success"))
        help_card.layout_body.addStretch(1)
        page.add(ResponsiveRow(editor, help_card, 3, 2))
        page.end()
        self.tabs.addTab(page, "⌘  Strategy Editor")

    def _risk_tab(self):
        page = PageScroll(self)
        page.add(page_hero(
            "CAPITAL PROTECTION / RISK GUARD",
            "Hard limits are enforced outside the AI model before orders can reach MT5.",
            "The system may reject all trades if the broker's minimum lot exceeds your risk budget."
        ))
        group = PremiumPanel(
            "01  /  POSITION & ACCOUNT LIMITS",
            "Adjust account-level and per-order safety rules.", accent="gold"
        )
        form = spaced_form(group)
        self.allow_symbols = QLineEdit(self.cfg.allow_symbols)
        self.allow_symbols.setPlaceholderText("XAUUSD, EURUSD, BTCUSD")
        form.addRow("Allowed symbols", self.allow_symbols)
        self.risk = spin_double(self.cfg.risk_per_trade_pct, 0.01, 2, 0.05)
        form.addRow("Risk per trade (% equity)", self.risk)
        self.daily_loss = spin_double(self.cfg.max_daily_loss_pct, 0.1, 15, 0.5)
        form.addRow("Realized daily loss limit (%)", self.daily_loss)
        self.spread = spin_double(self.cfg.max_spread_points, 1, 10000, 1, 1)
        form.addRow("Maximum spread (points)", self.spread)
        self.max_lot = spin_double(self.cfg.max_lot, 0.01, 100, 0.01, 2)
        form.addRow("Maximum position lot", self.max_lot)
        self.max_positions = spin_int(self.cfg.max_positions, 1, 100)
        form.addRow("Max simultaneous positions", self.max_positions)
        self.max_trades = spin_int(self.cfg.max_trades_day, 1, 100)
        form.addRow("Max new trades per day", self.max_trades)
        self.scan_interval = spin_int(self.cfg.scan_interval_seconds, 30, 3600)
        form.addRow("Scanning interval (seconds)", self.scan_interval)
        group.layout_body.addLayout(form)
        save = QPushButton("Save Risk Guard Limits")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_risk)
        group.layout_body.addWidget(save)

        guide = PremiumPanel(
            "02  /  SAFETY DESK", "Protection stays on even if a model proposes an unsafe trade.",
            accent="danger"
        )
        guide.layout_body.addWidget(make_badge("RISK RULES CANNOT BE OVERRIDDEN", "warning"))
        for paragraph in (
            "STOP LOSS + TAKE PROFIT\nA trade without valid levels is rejected.",
            "EQUITY-SIZED LOT\nVolume is derived from stop distance and broker contract size.",
            "PRICE VALIDITY\nFresh quotes, spread cap, order_check and filling rules are required.",
            "DAILY LIMITS\nRealized loss and maximum number of entries prevent overtrading.",
            "ACCOUNT AUTHORIZATION\nDemo vs. live order permission is checked independently.",
        ):
            guide.layout_body.addWidget(hint(paragraph))
        guide.layout_body.addStretch(1)
        page.add(ResponsiveRow(group, guide, 3, 2))
        page.end()
        self.tabs.addTab(page, "⬡  Risk Guard")

    def _mcp_tab(self):
        page = PageScroll(self)
        page.add(page_hero(
            "MT5 MCP / CONNECTIVITY HUB",
            "Connect to MetaTrader 5 native MCP using its internal URL and API key.",
            "Native MT5 MCP is read-only for automated trading. The optional LUMAVUN gateway uses separate credentials."
        ))

        connection = PremiumPanel(
            "01  /  MT5 CONNECTION", "Choose an existing local terminal or native MCP transport.",
            accent="gold"
        )
        form = spaced_form(connection)
        self.mt5_mode = QComboBox()
        self.mt5_mode.addItem("Local MT5 Terminal (Python)", "local")
        self.mt5_mode.addItem("LUMAVUN Gateway (legacy HTTP)", "mcp_http")
        self.mt5_mode.addItem("MetaTrader 5 Built-in MCP", "mt5_native")
        self.mt5_mode.setCurrentIndex(
            2 if self.cfg.mt5_mode == "mt5_native" else
            1 if self.cfg.mt5_mode == "mcp_http" else 0
        )
        self.mt5_mode.currentIndexChanged.connect(self.connection_mode_changed)
        form.addRow("Connection mode", self.mt5_mode)
        self.mt5_url = QLineEdit(
            self.cfg.mt5_native_url if self.cfg.mt5_mode == "mt5_native"
            else self.cfg.mt5_mcp_url
        )
        self.mt5_url.setPlaceholderText("http://127.0.0.1:22346/mcp")
        form.addRow("MCP server URL", self.mt5_url)
        self.mt5_remote_key = QLineEdit()
        self.mt5_remote_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.mt5_remote_key.setPlaceholderText("Paste MT5 Options → MCP API key")
        form.addRow("MCP API key", self.mt5_remote_key)
        connection.layout_body.addLayout(form)
        self.native_candle_fallback = QCheckBox(
            "Jika tool OHLC tidak tersedia, gunakan candle terminal MT5 lokal "
            "(read-only; akun dan server harus sama)"
        )
        self.native_candle_fallback.setChecked(self.cfg.native_local_candle_fallback)
        self.native_candle_fallback.setToolTip(
            "Opsional untuk MT5 di PC yang sama. Tidak akan membaca akun yang berbeda, "
            "tidak memberi izin trading, dan tidak berlaku untuk gateway remote."
        )
        self.native_candle_fallback.toggled.connect(self.set_native_candle_fallback)
        connection.layout_body.addWidget(self.native_candle_fallback)
        buttons = QHBoxLayout()
        save = QPushButton("Save Connection")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_mt5_connection)
        buttons.addWidget(save)
        test = QPushButton("Test MCP Connection")
        test.setObjectName("secondaryButton")
        test.clicked.connect(self.test_mcp_connection)
        buttons.addWidget(test)
        connection.layout_body.addLayout(buttons)
        self.mcp_link_status = make_badge("● NOT TESTED", "warning")
        connection.layout_body.addWidget(self.mcp_link_status)
        connection.layout_body.addWidget(hint(
            "Di MetaTrader 5: Peralatan → Pilihan → MCP → Aktifkan server internal → "
            "salin Alamat + Kunci API → klik OK. Gunakan API key baru jika pernah terlihat di screenshot."
        ))

        discovered = PremiumPanel(
            "02  /  DISCOVERED MT5 TOOLS",
            "Live tool discovery is read-only. Tool names are obtained from the connected server.",
            accent="violet"
        )
        self.native_tools_preview = QPlainTextEdit()
        self.native_tools_preview.setReadOnly(True)
        self.native_tools_preview.setMinimumHeight(250)
        self.native_tools_preview.setPlaceholderText(
            "Belum ada data. Klik Test MCP Connection untuk menemukan tool MetaTrader 5 native."
        )
        discovered.layout_body.addWidget(self.native_tools_preview)
        discovered.layout_body.addWidget(make_badge("NATIVE MCP: READ-ONLY ORDERS", "warning"))
        discovered.layout_body.addStretch(1)
        page.add(ResponsiveRow(connection, discovered, 3, 2))

        permissions = PremiumPanel(
            "03  /  EXTERNAL MCP PERMISSIONS",
            "A separate permission applies only when running the LUMAVUN-owned MCP tools.",
            accent="danger"
        )
        self.mcp_orders = QCheckBox(
            "Allow trusted external MCP clients to request guarded orders when execution is armed"
        )
        self.mcp_orders.setChecked(self.cfg.allow_mcp_orders)
        self.mcp_orders.toggled.connect(self.set_mcp_orders)
        permissions.layout_body.addWidget(self.mcp_orders)
        permissions.layout_body.addWidget(hint(
            "Changing this permission does NOT unlock automatic orders in MetaTrader 5 native MCP mode. "
            "All execution still requires account-mode approval and risk checks."
        ))
        page.add(permissions)

        sample_panel = PremiumPanel(
            "04  /  CLIENT CONFIGURATION",
            "Example for third-party AI MCP clients. Use the installed EXE path on this computer.",
            accent="gold"
        )
        sample = {"mcpServers":{"lumavun-mt5":{
            "command":r"C:\LUMAVUN\Lumavun-MT5-MCP.exe","args":[]}}}
        code = QPlainTextEdit(json.dumps(sample, indent=2, ensure_ascii=False))
        code.setReadOnly(True)
        code.setMinimumHeight(200)
        sample_panel.layout_body.addWidget(code)
        sample_panel.layout_body.addWidget(hint(
            "LUMAVUN MCP tools: mt5_account • mt5_positions • mt5_candles • "
            "mt5_order_preview • mt5_place_order. They are distinct from MetaTrader native tools."
        ))
        page.add(sample_panel)
        installer_panel = PremiumPanel(
            "05  /  PYTHON MT5 PACKAGE",
            "Optional Windows Python integration, separate from packaged EXE dependencies.",
            accent="violet"
        )
        installer_panel.layout_body.addWidget(hint(
            "EXE LUMAVUN sudah menyertakan MetaTrader5. Perintah CMD ini hanya memasang "
            "pustaka pada Python Windows terpisah, tidak memperbaiki modul dalam EXE."
        ))
        self.mt5_install_command = QLineEdit(PY_LAUNCHER_COMMAND)
        self.mt5_install_command.setReadOnly(True)
        installer_panel.layout_body.addWidget(self.mt5_install_command)
        install_buttons = QHBoxLayout()
        self.mt5_install_button = QPushButton("Open CMD / Install MetaTrader5")
        self.mt5_install_button.setObjectName("primaryButton")
        self.mt5_install_button.clicked.connect(self.install_mt5_package)
        install_buttons.addWidget(self.mt5_install_button)
        copy_button = QPushButton("Copy pip command")
        copy_button.setObjectName("secondaryButton")
        copy_button.clicked.connect(self.copy_mt5_install_command)
        install_buttons.addWidget(copy_button)
        installer_panel.layout_body.addLayout(install_buttons)
        installer_panel.layout_body.addWidget(hint(
            "Instalasi hanya dimulai saat tombol diklik. Terminal MetaTrader 5 tetap wajib terpasang."
        ))
        page.add(installer_panel)
        page.end()
        self.tabs.addTab(page, "◇  MT5 MCP")
        self.refresh_mcp_arming()

    def install_mt5_package(self):
        try:
            command = open_install_cmd()
        except (RuntimeError, OSError) as exc:
            QMessageBox.warning(self, "MT5 Python Installer", str(exc))
            self.log("CMD MT5 installer gagal: " + str(exc))
            return
        self.log("Installer CMD dibuka: " + command
                 + ". Lihat output pip di CMD. EXE LUMAVUN tidak berubah.")

    def copy_mt5_install_command(self):
        QApplication.clipboard().setText(self.mt5_install_command.text())
        self.log("Perintah pip MetaTrader5 disalin.")
    def set_native_candle_fallback(self, checked):
        cfg = Settings.load()
        cfg.native_local_candle_fallback = bool(checked)
        cfg.save()
        self.log("Candle local fallback: " + ("ON (read-only, same-account check)"
                                             if checked else "OFF"))
        self.mcp_link_status.setText(
            "● LOCAL READ FALLBACK ON" if checked else "● LOCAL READ FALLBACK OFF"
        )

    def connection_mode_changed(self):
        self.mcp_link_status.setText("● NOT TESTED")
        self.mcp_link_status.setProperty("mode", "warning")
        self.mcp_link_status.style().unpolish(self.mcp_link_status)
        self.mcp_link_status.style().polish(self.mcp_link_status)
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
        self.mcp_link_status.setText("● SAVED / NOT TESTED")
        self.mcp_link_status.setProperty("mode", "warning")
        self.mcp_link_status.style().unpolish(self.mcp_link_status)
        self.mcp_link_status.style().polish(self.mcp_link_status)
        self.log("MT5 connection mode saved: " + cfg.mt5_mode)
        self.office.update_roles()
        self.office.refresh()
        return True

    def test_mcp_connection(self):
        if self.mt5_mode.currentData() == "local":
            self.log("Pilih MetaTrader 5 Native MCP atau LUMAVUN Gateway terlebih dahulu.")
            return
        if not self.save_mt5_connection():
            return
        if self.mt5_mode.currentData() == "mt5_native":
            def report_native(info):
                candle_info = (
                    "OHLC get_chart_history: AVAILABLE"
                    if info["candle_history_available"]
                    else "OHLC get_chart_history: NOT EXPOSED by this MT5 server"
                )
                if not info["candle_history_available"]:
                    candle_info += (
                        "\nRead-only local candle fallback: "
                        + ("ENABLED" if info["local_read_fallback_enabled"] else "DISABLED")
                    )
                self.native_tools_preview.setPlainText(
                    candle_info + "\n\n"
                    + "\n".join(x["name"] + " | " + ", ".join(x["required"])
                                  for x in info["tools"]))
                if info.get("account"):
                    self.connection.setText(json.dumps(info["account"], indent=2, ensure_ascii=False))
                self.mcp_link_status.setText("● CONNECTED / " + str(info["total_tools"]) + " TOOLS")
                self.mcp_link_status.setProperty("mode", "success")
                self.mcp_link_status.style().unpolish(self.mcp_link_status)
                self.mcp_link_status.style().polish(self.mcp_link_status)
                self.log("Native MT5 MCP connected: " + str(info["total_tools"]) + " tools found (read-only).")
            self.task(lambda: inspect_connection(Settings.load()), report_native)
            return
        def report_gateway(status):
            self.connection.setText(json.dumps(status, indent=2))
            self.mcp_link_status.setText("● GATEWAY CONNECTED")
            self.mcp_link_status.setProperty("mode", "success")
            self.mcp_link_status.style().unpolish(self.mcp_link_status)
            self.mcp_link_status.style().polish(self.mcp_link_status)
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
            if self.tabs.currentIndex() == 5:
                self.mcp_link_status.setText("● CONNECTION ERROR")
                self.mcp_link_status.setProperty("mode", "danger")
                self.mcp_link_status.style().unpolish(self.mcp_link_status)
                self.mcp_link_status.style().polish(self.mcp_link_status)
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

    def apply_strategy_preset(self, name):
        template = SMC_MODELS.get(name)
        if template is not None:
            self.strategy.setPlainText(template)
            self.log("SMC template loaded for editing: " + name + ". Click Save Strategy to persist.")

    def browse_broker_symbols(self):
        """Search the active broker's ACTUAL symbol catalog, without guessing."""
        def show(names):
            dialog = QDialog(self)
            dialog.setWindowTitle("Choose an exact broker symbol")
            dialog.resize(560, 500)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(
                "Search the connected broker's instruments. Selecting a new symbol "
                "disarms trading; the risk allowlist must be reviewed separately."
            ))
            search = QLineEdit(self.symbol.text().strip(), dialog)
            search.setPlaceholderText("Search XAUUSD, GOLD, EURUSD, BTCUSD, etc.")
            layout.addWidget(search)
            results = QListWidget(dialog)
            layout.addWidget(results)
            layout.addWidget(QLabel("Broker catalog: " + str(len(names)) + " symbols"))
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel, parent=dialog)
            layout.addWidget(buttons)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            results.itemDoubleClicked.connect(lambda _: dialog.accept())

            def refresh(value):
                available = suggestions(value, names)[:300]
                results.clear()
                results.addItems(available)
                if available:
                    results.setCurrentRow(0)

            search.textChanged.connect(refresh)
            refresh(search.text())
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            item = results.currentItem()
            chosen = item.text() if item else search.text().strip()
            if chosen not in names:
                self.log("Invalid selection: choose a real symbol from the broker catalog.")
                return
            cfg = Settings.load()
            previous = cfg.symbol
            if chosen != previous:
                cfg.symbol = chosen
                cfg.last_signal_bar = ""
                cfg.execution_enabled = False
                cfg.live_allowed = False
                cfg.allow_mcp_orders = False
                cfg.save()
                self.symbol.setText(chosen)
                self.refresh_mcp_arming()
                self.office.update_roles()
                self.log("Broker symbol changed: " + previous + " -> " + chosen +
                         ". Trading DISARMED. Confirm Risk Guard allowed symbols before execution.")
            else:
                self.symbol.setText(chosen)
                self.log("Broker symbol confirmed: " + chosen)

        self.task(lambda: broker_symbols(Settings.load()), show)

    def save_strategy(self):
        cfg = Settings.load()
        symbol = self.symbol.text().strip()
        if cfg.symbol != symbol:
            cfg.execution_enabled = False
            cfg.live_allowed = False
            cfg.allow_mcp_orders = False
        cfg.symbol = symbol
        cfg.timeframe = self.timeframe.currentText()
        cfg.strategy = self.strategy.toPlainText().strip()
        if not cfg.symbol or not cfg.strategy:
            self.log("Symbol and strategy cannot be empty.")
            return
        cfg.last_signal_bar = ""
        cfg.save()
        self.log("Strategy saved. Signal cache reset. If broker symbol changed, trading was DISARMED.")
        self.refresh_mcp_arming()
        self.office.update_roles()

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
        self.office.update_roles()

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
        self.office.update_roles(analyst="Analyzing")
        self.log("Analyzing latest CLOSED candle with configured AI...")
        self.task(run_strategy_once, self._show_ai_result)

    def _show_ai_result(self, result):
        self.log(json.dumps(result, indent=2, ensure_ascii=False))
        status = result.get("status", "")
        self.office.update_roles(analyst=status or "Ready")
        broker_symbol = result.get("broker_symbol")
        if broker_symbol and broker_symbol != self.symbol.text():
            self.symbol.setText(broker_symbol)
        if result.get("auto_resolved"):
            self.refresh_mcp_arming()
            self.log("Broker symbol resolved: " +
                     str(result.get("requested_symbol")) + " -> " + str(broker_symbol) +
                     ". Execution DISARMED; verify the exact symbol on Risk Guard allowlist.")
        reasons = {
            "TARGET_REACHED": "profit target reached",
            "TARGET_CHECK_UNAVAILABLE": "profit target history could not be verified",
            "DATA_UNAVAILABLE": "broker market data/symbol unavailable",
            "SYMBOL_SELECTION_REQUIRED": "multiple broker symbols matched; choose one manually",
        }
        if status in reasons and self.timer.isActive():
            self.timer.stop()
            self.auto_button.setText("Start Auto Scan")
            self.log("Auto scan paused: " + reasons[status] + ".")
        self.office.refresh()

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
        self.office.update_roles()
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
        self.office.update_roles()
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
        self.office.update_roles()
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
    app.setApplicationName("LUMAVUN Trade Server")
    app.setOrganizationName("LUMAVUN")
    app.setStyle("Fusion")
    app.setWindowIcon(brand_icon())
    app.setStyleSheet(STYLESHEET)
    win = Window()
    win.show()
    app.exec()
