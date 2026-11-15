import pytest
from lumavun.risk import (
    TradeRejected, calculate_lot, ensure_direction, normalize_volume,
)

def test_buy_must_have_correct_protective_stop():
    ensure_direction("BUY", 4000, 3997, 4006)
    with pytest.raises(TradeRejected, match="SL"):
        ensure_direction("BUY", 4000, 4002, 4006)

def test_sell_must_have_correct_protective_stop():
    ensure_direction("SELL", 4000, 4003, 3994)
    with pytest.raises(TradeRejected, match="SL"):
        ensure_direction("SELL", 4000, 3998, 3994)

def test_reject_poor_reward_risk():
    with pytest.raises(TradeRejected, match="Reward/risk"):
        ensure_direction("BUY", 4000, 3990, 4008)

def test_round_lots_down_not_up():
    assert normalize_volume(0.036, 0.01, 1.0, 0.01) == 0.03

def test_broker_minimum_cannot_exceed_risk_budget():
    with pytest.raises(TradeRejected, match="Minimum broker lot"):
        calculate_lot(10, 0.5, 10, 0.01, 100, 0.01, 0.1)

def test_volume_cap_never_increases_risk():
    assert calculate_lot(10000, 1, 100, 0.01, 10, 0.01, 0.2) == 0.2

def test_refuse_zero_equity():
    with pytest.raises(TradeRejected):
        calculate_lot(0, 1, 100, 0.01, 1, 0.01, 0.1)
