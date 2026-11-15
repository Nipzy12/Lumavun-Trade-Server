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


def test_openai_uses_responses_for_reasoning_models(monkeypatch):
    from lumavun import ai
    calls = []
    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs["json"]))
        return {"output": [{"type": "message", "content": [{"type": "output_text",
                 "text": '{"side":"HOLD","reason":"Wait"}'}]}]}
    monkeypatch.setattr(ai, "_headers", lambda cfg: {"Authorization": "Bearer sample"})
    monkeypatch.setattr(ai, "_request", fake_request)
    proposal, reason = ai.propose_trade(Settings(provider="OpenAI", model="gpt-6-astra"),
                                        [{"time": t, "close": 1.0} for t in range(10)])
    assert proposal is None and reason == "Wait"
    assert calls[0][1].endswith("/responses")
    assert "temperature" not in calls[0][2]
