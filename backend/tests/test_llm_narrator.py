"""LLM narrator wiring: off by default, request shape, and the existing validator still guards the output."""
import json

from app.engine import explain, llm_narrator


class _Resp:
    def __init__(self, text): self.text = text
    def read(self): return json.dumps({"choices": [{"message": {"content": self.text}}]}).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_off_without_key(monkeypatch):
    monkeypatch.delenv("TRACEGUARD_LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm_narrator, "ENV_FILE", llm_narrator.ENV_FILE.with_name("does-not-exist.env"))
    monkeypatch.setattr(explain, "_llm", None)
    assert llm_narrator.configure_from_env() is None and explain._llm is None


def test_placeholder_key_stays_off(monkeypatch):
    monkeypatch.setenv("TRACEGUARD_LLM_API_KEY", "paste_your_groq_key_here")
    monkeypatch.setattr(explain, "_llm", None)
    assert llm_narrator.configure_from_env() is None


def test_request_goes_to_configured_endpoint_with_bearer(monkeypatch):
    seen = {}
    def fake(req, timeout):
        seen.update(url=req.full_url, auth=req.headers["Authorization"], body=json.loads(req.data)); return _Resp("ok [E_AUTH_FAILURE]")
    monkeypatch.setattr(llm_narrator.urllib.request, "urlopen", fake)
    out = llm_narrator.make_llm("k123", "https://example.test/v1/", "m1")({"user": "x"})
    assert out.startswith("ok") and seen["url"] == "https://example.test/v1/chat/completions" and seen["auth"] == "Bearer k123"
    assert seen["body"]["model"] == "m1" and seen["body"]["temperature"] == 0


def test_network_error_falls_back_to_template(monkeypatch, results):
    def boom(req, timeout): raise OSError("down")
    monkeypatch.setattr(llm_narrator.urllib.request, "urlopen", boom)
    monkeypatch.setattr(explain, "_llm", llm_narrator.make_llm("k", "https://example.test/v1", "m"))
    r = next(iter(results.values())) if isinstance(results, dict) else results[0]
    out = explain.narrate(r, "Test User")
    assert out["source"] == "template" and "unavailable" in out["rejected_reason"]
