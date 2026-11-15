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

## Download two EXE files

1. Open GitHub repository Actions -> Windows EXE Build.
2. Run workflow manually or open latest successful run.
3. Download the Lumavun-Trade-Server-Windows artifact ZIP.
4. Extract LUMAVUN-Trade-Server.exe (dashboard) and Lumavun-MT5-MCP.exe (MCP stdio server).

A Windows GitHub Actions runner builds both binaries. They are not hand-compiled in this chat.

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


## New: HTTP MCP Gateway using an internal URL and API key

**MT5 does not have a built-in MCP API key.** The broker trading server name is NOT an MCP URL. LUMAVUN generates its own gateway API key in the Windows credential vault. Keep the broker terminal logged in locally; never send an MT5 account password to a remote LUMAVUN desktop.

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
