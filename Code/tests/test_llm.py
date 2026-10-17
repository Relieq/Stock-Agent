import pytest

from services import llm
from services.llm import LLMConfig, ProviderUnavailable, Usage, VisionClient


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str = "error"):
        super().__init__(message)
        self.status_code = status_code


class APIConnectionError(Exception):
    pass


class Fake:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def call(self, prompt, images, schema, schema_name, limit, detail):
        self.calls += 1
        out = self.outcomes.pop(0) if self.outcomes else {"ok": True}
        if isinstance(out, Exception):
            raise out
        return out, 100, 10


def client_with(*backends) -> VisionClient:
    c = VisionClient.__new__(VisionClient)
    c._configs = [LLMConfig("anthropic", "", "k", "claude-haiku-5-5"), LLMConfig("openai", "", "k", "gpt-5.4-mini")][:len(backends)]
    c._backends = dict(enumerate(backends))
    c.active, c.usage, c.steps, c.switches, c.down, c.step_providers, c.extras = 0, Usage(), {}, [], set(), {}, set()
    return c


def test_switches_to_fallback_when_out_of_credit_and_stays_there():
    primary, fallback = Fake(FakeStatusError(400, "Your credit balance is too low")), Fake()
    c = client_with(primary, fallback)
    assert c.json_from_images("p", [], {}, "statement_BS") == {"ok": True}
    assert c.cfg.provider == "openai" and len(c.switches) == 1 and c.switches[0]["sticky"]
    c.json_from_images("p", [], {}, "statement_IS")
    assert primary.calls == 1 and fallback.calls == 2       # không quay lại nhà chính đã hết tiền


def test_rate_limit_server_error_and_connection_error_trigger_fallback():
    for err in (FakeStatusError(429), FakeStatusError(529), FakeStatusError(503), APIConnectionError()):
        c = client_with(Fake(err), Fake())
        assert c.json_from_images("p", [], {}, "x") == {"ok": True} and c.active == 1


def test_refusal_falls_back_for_that_call_only():
    primary, fallback = Fake(ProviderUnavailable("refusal", sticky=False)), Fake()
    c = client_with(primary, fallback)
    c.json_from_images("p", [], {}, "x")
    c.json_from_images("p", [], {}, "x")
    assert c.active == 0 and primary.calls == 2 and fallback.calls == 1


def test_bad_request_is_not_hidden_by_fallback():
    c = client_with(Fake(FakeStatusError(400, "invalid schema")), Fake())
    with pytest.raises(FakeStatusError):
        c.json_from_images("p", [], {}, "x")


def test_error_on_last_provider_is_raised():
    c = client_with(Fake(FakeStatusError(429)), Fake(FakeStatusError(429)))
    with pytest.raises(FakeStatusError):
        c.json_from_images("p", [], {}, "x")


def test_cost_uses_model_that_actually_answered():
    c = client_with(Fake(FakeStatusError(429)), Fake())
    c.json_from_images("p", [], {}, "statement_BS")
    assert c.usage.usd == pytest.approx(llm.cost_usd("gpt-5.4-mini", 100, 10))
    assert c.steps["statement_BS"].usd == pytest.approx(c.usage.usd)


def test_admin_choice_reorders_configured_providers(monkeypatch):
    import tempfile
    from pathlib import Path
    tmp_path = Path(tempfile.mkdtemp())
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(llm, "settings_path", lambda: tmp_path / "settings.json")
    assert [p for p, _ in llm.provider_order()] == ["openai", "anthropic"]
    llm.write_settings(llm_primary="anthropic")
    assert [p for p, _ in llm.provider_order()] == ["anthropic", "openai"]
    llm.write_settings(llm_primary="gemini")            # nhà chưa cấu hình: giữ thứ tự trong .env
    assert [p for p, _ in llm.provider_order()] == ["openai", "anthropic"]


def test_claude_images_fit_its_limits():
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("L", (2380, 3370), 255).save(buf, "PNG")
    w, h = Image.open(io.BytesIO(llm.fit_claude(buf.getvalue()))).size
    assert max(w, h) <= 2576 and -(-w // 28) * -(-h // 28) <= 4784


def test_step_override_uses_named_provider_for_that_step_only():
    primary, other = Fake(), Fake()
    c = client_with(primary, other)                 # nhà chính: anthropic; nhà thứ hai: openai
    c.step_providers = {"page_classification": "openai"}
    c.json_from_images("p", [], {}, "page_classification")
    c.json_from_images("p", [], {}, "statement_BS")
    assert other.calls == 1 and primary.calls == 1 and c.active == 0


def test_step_override_falls_back_when_its_provider_is_down():
    primary, other = Fake(), Fake(FakeStatusError(429))
    c = client_with(primary, other)
    c.step_providers = {"page_classification": "openai"}
    c.json_from_images("p", [], {}, "page_classification")          # openai lỗi -> anthropic trả lời
    c.json_from_images("p", [], {}, "page_classification")          # openai đã hỏng trong đợt: không thử lại
    assert other.calls == 1 and primary.calls == 2 and c.active == 0


def test_step_model_spec_uses_extra_model_only_for_that_step(monkeypatch):
    primary, other, strong = Fake(), Fake(), Fake()
    c = client_with(primary, other)
    c.step_providers = {"repair_escalate": "anthropic:claude-opus-5-5"}
    monkeypatch.setattr(llm, "_provider_config", lambda p, m: LLMConfig(p, "", "k", m))
    c._backends[2] = strong
    c.json_from_images("p", [], {}, "reread_cells", step="repair_escalate")
    c.json_from_images("p", [], {}, "statement_BS")
    assert strong.calls == 1 and primary.calls == 1 and other.calls == 0
    assert c.steps["repair_escalate"].usd == pytest.approx(llm.cost_usd("claude-opus-5-5", 100, 10))


def test_failed_step_model_falls_back_to_normal_order(monkeypatch):
    primary, strong = Fake(), Fake(FakeStatusError(529))
    c = client_with(primary, Fake())
    c.step_providers = {"repair_escalate": "anthropic:claude-opus-5-5"}
    monkeypatch.setattr(llm, "_provider_config", lambda p, m: LLMConfig(p, "", "k", m))
    c._backends[2] = strong
    c.json_from_images("p", [], {}, "x", step="repair_escalate")
    assert primary.calls == 1 and c.active == 0
