import pytest
from lumavun.ai import AIError, _extract, _url
from lumavun.config import Settings

def test_ai_hold_never_creates_order():
    proposal, reason = _extract('{"side":"HOLD","sl":null,"tp":null,"reason":"No setup"}', "XAUUSD")
    assert proposal is None
    assert reason == "No setup"

def test_buy_proposal_does_not_include_position_size():
    proposal, reason = _extract('{"side":"BUY","sl":3990,"tp":4020,"lot":999,"reason":"Sweep"}', "XAUUSD")
    assert (proposal.symbol, proposal.side, proposal.sl, proposal.tp) == ("XAUUSD", "BUY", 3990, 4020)
    assert not hasattr(proposal, "lot")

def test_non_json_is_rejected():
    with pytest.raises(AIError, match="JSON"):
        _extract("BUY NOW without a stop", "XAUUSD")

def test_remote_insecure_provider_is_blocked():
    cfg = Settings(provider="Custom (OpenAI-compatible)", base_url="http://evil.example/v1")
    with pytest.raises(AIError, match="HTTPS"):
        _url(cfg)

def test_local_ollama_http_is_allowed():
    assert _url(Settings(provider="Ollama")) == "http://127.0.0.1:11434/v1"
