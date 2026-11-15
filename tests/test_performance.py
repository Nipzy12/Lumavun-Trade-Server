"""Real MT5 accounting, non-fictional dashboards, and profit-target stop checks."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

from lumavun import engine, performance
from lumavun.config import Settings

UTC = timezone.utc

def deal(ts, typ, entry, profit, commission=0, symbol="XAUUSD"):
    return {
        "time": ts, "ticket": ts, "symbol": symbol, "type": typ,
        "entry": entry, "volume": 0.01, "profit": profit,
        "commission": commission, "swap": 0, "fee": 0
    }

def test_deals_include_costs_and_exclude_balance_transfers():
    entries = [
        deal(10000, 0, 0, 0, -0.20),
        deal(11000, 1, 1, 4.50, -0.20),
        deal(12000, 0, 1, -3, -0.20),
        deal(13000, 2, 0, 1000000, symbol=""),  # deposit, not trade
    ]
    normalized = performance.parse_deals(entries)
    assert len(normalized) == 3
    assert normalized[0]["net"] == -0.20
    assert normalized[1]["net"] == 4.30
    assert normalized[2]["net"] == -3.20
    summary = performance._summarize_deals(
        normalized, datetime.fromtimestamp(9000, UTC))
    assert summary["realized"] == pytest.approx(0.90)
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["closed"] == 2
    assert summary["win_rate"] == 50.0

def test_orders_are_not_fabricated_as_executed_deals():
    with pytest.raises(performance.HistoryUnavailable, match="deals"):
        performance._as_history_deals({"orders": [{"order": 2, "symbol": "XAUUSD"}]})

def test_metaquotes_history_deals_are_extracted():
    result = performance._as_history_deals({
        "data": {"orders": [{"order": 1}],
                 "deals": [deal(1700000000, 0, 1, 1.23)]}
    })
    assert len(result) == 1

def test_utc_goal_period_start():
    now = datetime(2026, 11, 18, 11, 44, tzinfo=UTC)
    assert performance.period_start_utc("day", now) == datetime(2026, 11, 18, tzinfo=UTC)
    assert performance.period_start_utc("week", now) == datetime(2026, 11, 16, tzinfo=UTC)
    assert performance.period_start_utc("month", now) == datetime(2026, 11, 1, tzinfo=UTC)

def test_snapshot_target_and_realized_use_actual_deals(monkeypatch):
    from lumavun import mt5_access
    monkeypatch.setattr(mt5_access, "account_status", lambda cfg: {
        "login": 123, "server": "Demo", "currency": "USD",
        "demo": True, "balance": 102.0, "equity": 101.0
    })
    monkeypatch.setattr(mt5_access, "list_positions", lambda cfg: [
        {"profit": -1.0, "symbol": "XAUUSD"}
    ])
    now = datetime(2026, 11, 18, 18, tzinfo=UTC)
    deals = performance.parse_deals([
        deal(int(datetime(2026,11,17,tzinfo=UTC).timestamp()), 0, 1, 5),
        deal(int(datetime(2026,11,18,tzinfo=UTC).timestamp()), 1, 1, -3)
    ])
    monkeypatch.setattr(performance, "fetch_deals", lambda cfg, start, end: deals)
    cfg = Settings(profit_target_amount=6, profit_target_period="week")
    actual = performance.make_snapshot(cfg, days=7, now=now)
    assert actual["history_available"] is True
    assert actual["history"]["realized"] == 2
    assert actual["target_realized"] == 2
    assert actual["progress"] == pytest.approx(33.3333, abs=0.001)
    assert actual["target_reached"] is False
    assert actual["floating"] == -1.0

def test_missing_broker_history_is_unavailable_not_zero(monkeypatch):
    from lumavun import mt5_access
    monkeypatch.setattr(mt5_access, "account_status", lambda cfg: {
        "login": 42, "currency": "USD", "balance": 10, "equity": 10
    })
    monkeypatch.setattr(mt5_access, "list_positions", lambda cfg: [])
    def unavailable(*args):
        raise performance.HistoryUnavailable("History disabled")
    monkeypatch.setattr(performance, "fetch_deals", unavailable)
    actual = performance.make_snapshot(Settings(profit_target_amount=5), days=7)
    assert actual["history_available"] is False
    assert actual["history"]["realized"] is None
    assert actual["target_realized"] is None
    assert actual["progress"] is None
    assert actual["target_reached"] is False
    assert actual["history_error"] == "History disabled"

def test_target_stop_does_not_request_ai_when_goal_met(monkeypatch):
    cfg = Settings(profit_target_amount=2, pause_at_profit_target=True)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: cfg))
    monkeypatch.setattr(engine, "check_profit_target",
                        lambda cfg: {"enabled": True, "reached": True,
                                     "realized": 2.25, "target": 2, "period": "day"})
    monkeypatch.setattr(engine, "get_candles",
                        lambda *args: pytest.fail("No AI or market fetch when target met"))
    output = engine.run_strategy_once()
    assert output["status"] == "TARGET_REACHED"

def test_target_stop_fails_closed_when_history_unavailable(monkeypatch):
    cfg = Settings(profit_target_amount=2, pause_at_profit_target=True)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: cfg))
    def unavailable(cfg):
        raise performance.HistoryUnavailable("broker unavailable")
    monkeypatch.setattr(engine, "check_profit_target", unavailable)
    monkeypatch.setattr(engine, "get_candles",
                        lambda *args: pytest.fail("Must not scan without verified target"))
    output = engine.run_strategy_once()
    assert output["status"] == "TARGET_CHECK_UNAVAILABLE"

def test_native_history_schema_required_unknown_field_rejected(monkeypatch):
    from lumavun import native_mt5
    monkeypatch.setattr(native_mt5, "_get_tool", lambda name,cfg: {
        "inputSchema": {"properties": {
            "from_time": {"type": "integer"},
            "to_time": {"type": "integer"},
            "private_password": {"type": "string"}},
            "required": ["from_time", "to_time", "private_password"]}})
    now = datetime(2026,11,18,tzinfo=UTC)
    with pytest.raises(performance.HistoryUnavailable, match="Schema history"):
        performance._native_history(Settings(mt5_mode="mt5_native"), now-timedelta(days=1),now)

def test_history_deals_from_native_broker_mcp(monkeypatch):
    from lumavun import native_mt5
    args = []
    monkeypatch.setattr(native_mt5, "_get_tool", lambda name,cfg: {
        "inputSchema": {"properties": {
            "date_from": {"type": "string"},
            "date_to": {"type": "string"}},
            "required": ["date_from", "date_to"]}})
    def read(name, payload, cfg):
        args.append(payload)
        return {"deals": [deal(1700000000, 0, 1, 4.5)]}
    monkeypatch.setattr(native_mt5, "_read_tool", read)
    now = datetime(2026,11,18,tzinfo=UTC)
    result = performance._native_history(Settings(mt5_mode="mt5_native"),
                                         now-timedelta(days=1),now)
    assert len(result) == 1
    assert args[0]["date_from"].startswith("2026-11-17")
