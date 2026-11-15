# LUMAVUN Trade Server (Windows)

Native MetaTrader 5 desktop assistant with multi-provider AI, an MCP server, an editable strategy, and deterministic risk protections.

**Status:** initial MVP. Test on DEMO first. Real-money trading can lose funds. The app cannot guarantee profitability or protect against all market gaps and broker outages.

## Features

- PySide6 desktop dashboard: MT5 status, open positions, strategy editor, provider/model selection, editable risk controls and periodic AI scanning.
- AI integration: OpenAI, OpenRouter, Groq, DeepSeek, xAI, Together, Mistral, Ollama (local), Anthropic, Gemini, and custom OpenAI-compatible providers. Use models supported by your chosen provider; where model discovery exists, click Fetch Available Models.
- API keys stored with Windows Credential Manager via keyring, not in the JSON settings file. Remote endpoints must use HTTPS.
- MT5 account, positions, and CLOSED OHLC candle reads through the locally running Windows MetaTrader 5 terminal.
- Separate MCP stdio executable exposing mt5_account, mt5_positions, mt5_candles, mt5_order_preview, mt5_place_order.
- Trade checks: demo-only by default, explicit live authorization, separate MCP order authorization, per-trade equity risk, max lot, max spread, symbols allowlist, minimum reward/risk, SL/TP, max positions and daily trades, daily realized-loss gate, order_check before order_send.

## Download Windows EXE files

1. Open GitHub repository Actions -> Windows EXE Build.
2. Run workflow manually or open latest successful run.
3. Download the Lumavun-Trade-Server-Windows artifact ZIP.
4. Extract LUMAVUN-Trade-Server.exe (dashboard), Lumavun-MT5-MCP.exe (stdio server) and optional Lumavun-MT5-Gateway.exe (HTTP gateway).

A Windows GitHub Actions runner builds the executables. They are not hand-compiled in this chat.

## Usage on Windows

1. Install MetaTrader 5, log in on a DEMO account, enable algorithmic trading in the terminal, and leave MT5 running.
2. Launch LUMAVUN-Trade-Server.exe and click Check MT5 Connection.
3. Set AI provider, secret API key (not needed for Ollama), model ID and optional custom HTTPS base URL.
4. Enter the exact broker symbol including suffix, timeframe and strategy. Save.
5. Add the exact symbol to the risk allowlist. Configure lot cap, max risk, spread and trade limits.
6. Click Analyze One Closed Candle. Initially all AI signals are previews, not orders.
7. If appropriate, arm DEMO execution. LIVE real-money trading requires the phrase ENABLE LIVE TRADING and separate confirmation. Emergency Disarm blocks any further app-originated order but never closes existing positions.
8. Start Auto Scan for periodic analysis while the app remains open. Only one evaluation is run per latest closed candle.

For low-equity accounts, broker minimum lot may exceed the configured risk cap. In that case the app refuses to execute a trade, even if an AI wants to place one. Always test and verify broker symbols, contract sizes, permissions, and market hours before enabling trades.

## MCP stdio configuration

Example MCP client config (adjust local Windows path):

    {
      "mcpServers": {
        "lumavun-mt5": {
          "command": "C:\\LUMAVUN\\Lumavun-MT5-MCP.exe",
          "args": []
        }
      }
    }

The MCP tool for submitting an order is disabled by default. It works only when BOTH desktop execution and MCP order permission are enabled; live accounts also require separate live authorization. Read-only tools and risk previews do not require this permission. MCP uses stdio, not a public network service.

## Development

Python 3.11 on Windows:

    py -3.11 -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt pytest
    python -m pytest -q
    python main.py

To run the MCP executable from source:

    python mcp_entry.py

Architecture: desktop GUI -> AI strategy engine -> LLM JSON proposal -> deterministic risk gate -> local MT5 terminal. External MCP clients use the same gate. Only one order-send function can reach MT5.

Known limits: no backtester, news calendar filter, guaranteed execution, unattended Windows service, or floating-equity-based daily loss lock. Daily loss uses realized P/L from MT5. Strategy prompts are not validated for predictive quality, and API billing belongs to the chosen provider. Do not run an external MCP client you do not trust.


## Native MetaTrader 5 MCP (preferred, NO extra gateway)

Recent versions of MetaTrader 5 include a native MCP server. This is **not** the extra LUMAVUN gateway. See [official MetaQuotes configuration](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/configuration) and [official tool capabilities](https://www.metatrader5.com/en/terminal/help/mcp_and_ai/capabilities).

1. Open MetaTrader 5 on Windows and log in to your broker (start with demo). Go to **Tools → Options → MCP**.
2. Check **Enable internal server**, confirm the address (typically `http://127.0.0.1:22346/mcp`), and click **Generate** for an API key. Copy both fields and **click OK** to save.
3. Open `LUMAVUN-Trade-Server.exe`, tab **MT5 MCP**.
4. Choose **MetaTrader 5 Native MCP (built-in)**, paste the copied URL and **MT5-generated** API key, click **Save Connection**, then **Test MCP Connection**.
5. The app initiates the Streamable HTTP MCP handshake with `Authorization: Bearer <your MT5 key>`, discovers actual MT5 tool names, and optionally shows account info. Use **Check MT5 Connection** on Dashboard for account status. If the terminal exposes the supported candle tool schema, the AI can analyze closed candles.
6. Native MCP **automatic order sending is intentionally disabled in this release**. AI output can be `SIGNAL_ONLY`; no native trading tool is called. For guarded demo orders, use **Local MT5 Terminal** mode (Python bridge) instead. Native broker trade tool schemas and lot/risk constraints require validation on the actual terminal before automated execution is safe.

Native MetaTrader 5 tools include `get_trading_account_info`, `get_trading_open_positions`, `get_chart_history`, and `trade_send_market_order`, **not** the `mt5_account` and `mt5_candles` names used by the separate LUMAVUN gateway. Tool schemas vary by MT5 build, so the app discovers them on connection and does not guess unknown required arguments.

**Security:** the MT5 API key is kept separately in Windows Credential Manager; never commit it, paste it into public chat or include it in screenshots. If a screenshot previously revealed the key, **regenerate it in MT5** before use. The server URL `127.0.0.1` works only when LUMAVUN and MT5 run on the same machine. HTTPS is required for network addresses or use a trusted encrypted localhost tunnel.

## Optional legacy: LUMAVUN HTTP MCP Gateway

**MetaTrader 5 DOES include a native MCP server and API key** in current versions. This optional LUMAVUN gateway is separate and only needed when explicitly choosing the legacy gateway mode. The broker trading server name is NOT an MCP URL. The legacy LUMAVUN gateway generates its own API key in the Windows credential vault. Keep the broker terminal logged in locally; never send an MT5 account password to a remote LUMAVUN desktop.

New Windows ZIP contains THREE programs:
- **LUMAVUN-Trade-Server.exe**: Desktop trading dashboard and MCP URL/API key configuration.
- **Lumavun-MT5-MCP.exe**: Existing MCP stdio server for local MCP clients.
- **Lumavun-MT5-Gateway.exe**: New HTTP Streamable MCP server exposing the same risk-checked MT5 tools.

### Same Windows PC (recommended first)

1. Open MT5, log into a demo account, leave MT5 running.
2. Start Lumavun-MT5-Gateway.exe. It creates an independent 256-bit API token and prints:
   - MCP URL: `http://127.0.0.1:8765/mcp`
   - MCP API KEY: `luma_...` (your unique token).
3. Keep the gateway terminal running, open LUMAVUN-Trade-Server.exe.
4. Go to **MT5 MCP** tab, set **Internal MCP Gateway**, paste the URL and API key and click **Save Connection**.
5. Click **Test MCP Connection**; a successful demo connection reports account server and equity.
6. Use Dashboard **Check MT5 Connection**, and then Strategy Editor as before. Sending orders remains disabled until both the local dashboard AND the gateway host have appropriate permissions. The gateway uses the existing **execution_enabled, live_allowed, allow_mcp_orders** settings on the gateway Windows host, and its risk guard cannot be bypassed by an API call.

### Access across two computers

For access outside the gateway PC, use an **encrypted tunnel** (SSH/VPN with localhost forwarding) or expose the gateway through TLS with a trusted certificate:

    Lumavun-MT5-Gateway.exe --bind 192.168.1.20 --public-host 192.168.1.20 --certfile C:\secure\server-cert.pem --keyfile C:\secure\server-key.pem

The certificate must be trusted on the LUMAVUN client and its subjectAltName must include the IP/hostname being used. Then enter `https://192.168.1.20:8765/mcp` on the client. Configure Windows Firewall to permit *only trusted machines* to connect. The gateway refuses non-loopback listening without TLS and does not allow browser Origins. Plain `http://192.168.x.x` is intentionally blocked to protect the bearer key.

To rotate the gateway key, stop the gateway, then restart with:

    Lumavun-MT5-Gateway.exe --rotate-key

Paste the new token in the client. The old one stops working. API keys are persisted in Windows Credential Manager, and are never stored in settings.json.

### Limits and trade safety

- MCP Gateway must run on the same Windows host as the MT5 terminal. It is not a replacement for the broker's server.
- Trading permissions are independently checked by the client and host. Demo testing first. LIVE needs separate host and client confirmations.
- Host-side limits (spread, lot, daily loss, allowlist, position limits) are always enforced, regardless of AI provider.
- The gateway cannot work if MT5 is closed or not logged in, though a transport handshake can still succeed.
- The gateway stops when its EXE console closes. Do not expose it directly to the public internet.


## AI Trading Office dashboard (Windows app)

The first tab is now **Trading Office**. Its workspace/office illustration is drawn directly with Qt (no copied or externally licensed assets). Four visible desks represent the actual software states:

- **AI Analyst**: ready/analyzing/HOLD or trade signal status, sourced from real `run_strategy_once` actions.
- **Risk Manager**: the configured deterministic limits are active; this is NOT an autonomous AI employee.
- **Trade Executor**: explicitly disarmed / DEMO armed / LIVE authorized. Built-in MT5 MCP stays read-only.
- **Performance Desk**: MT5 data loading/ready/connection failure, without fake account values.

**KPIs and report**: MT5 balance, equity, floating position profit, realized trading-deal P&L, count of profitable/losing closing deals, win rate, cumulative realized P&L curve, and transaction journal. Filter UTC periods (today, 7, 30, 90 days). The display stays blank (dash) and reports a connection/history error if the broker data is unavailable. No demo values are invented.

**History source**:
- Direct local MT5: `history_deals_get(start, end)`. Only broker deal types BUY/SELL with valid symbols are counted, including profit, swap, commissions and fees. Deposits and withdrawals do not count as profit.
- MT5 built-in MCP: tool `get_trading_history_orders` when it has a recognized time-range schema and returns an executed `deals` list. Different MT5 versions may expose another format; unsupported formats fail visibly instead of showing guessed figures.
- Legacy LUMAVUN Gateway: no history endpoint is implemented, so journal and target progress report unavailable in that mode.

**Profit target**: save a positive amount in the account currency, choose daily/weekly/monthly UTC reporting, and monitor realized P&L toward the goal. Progress can be negative/zero, or exceed 100% internally, with the meter capped at 100%. A target is **not** a guaranteed return or permission to increase risk.

**Optional stop rule**: tick **Stop auto trading saat target tercapai**. Before an automated AI scan, the engine checks realized broker deal history for that period. If the goal is met, the scan returns `TARGET_REACHED` without new orders. If history cannot be retrieved, it returns `TARGET_CHECK_UNAVAILABLE` and stops the scanning timer instead of trading blind. This does NOT close existing positions or cancel broker orders. If you want to stop order sending immediately, use the Emergency Disarm button as well.

Windows CI builds the executable and renders the real Office QWidget in a headless smoke test. The Windows ZIP includes `trading-office-preview.png` (with placeholder labels rather than fictional account balances).

Design references: [RigelHQ Claude Office](https://github.com/rigel-hq/claude-office) for office/agent-role metaphor; [Scope360](https://scope360.io/) and [MetaTrader 5 trading reports](https://www.metatrader5.com/en/terminal/help/trading_advanced/history_report) for financial KPI grouping and realized/floating separation.

