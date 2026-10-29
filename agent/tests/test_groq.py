import asyncio
import json
import logging
from pathlib import Path

import httpx2 as httpx
import pytest

from bankops_agent import verify_groq
from bankops_agent.config import Settings
from bankops_agent.rca.provider import OpenAICompatibleProvider, ProviderFailure


def enable_mocked_live(monkeypatch):
    for suffix, value in {"GROQ_LIVE_VERIFY": "1", "LLM_PROVIDER": "openai_compatible",
        "LLM_URL": verify_groq.ENDPOINT, "LLM_MODEL": verify_groq.MODEL,
        "LLM_API_KEY": "PRIVATE_TEST_TOKEN", "LLM_CHAT_INCLUDE_STORE": "false"}.items():
        monkeypatch.setenv("BANKOPS_AGENT_" + suffix, value)


def install_transport(monkeypatch, handler):
    def factory(settings, *, transport=None):
        return OpenAICompatibleProvider(settings, transport=transport or httpx.MockTransport(handler))
    monkeypatch.setattr(verify_groq, "OpenAICompatibleProvider", factory)


def test_profile_disabled_no_credentials_committed():
    fields = dict(line.split("=", 1) for line in Path(".env.groq.example").read_text().splitlines()
                  if line and not line.startswith("#"))
    config = Settings(**{key.removeprefix("BANKOPS_AGENT_").lower(): value for key, value in fields.items()})
    assert config.llm_provider == "disabled" and config.llm_api_key is None
    assert str(config.llm_url) == verify_groq.ENDPOINT and config.llm_model == verify_groq.MODEL
    assert not config.llm_chat_include_store and fields["BANKOPS_AGENT_GROQ_LIVE_VERIFY"] == "0"


def test_default_verification_exactly_two_mocked_scenarios(monkeypatch):
    original = httpx.AsyncClient.__init__
    def no_network(self, *args, **kwargs):
        assert isinstance(kwargs.get("transport"), httpx.MockTransport)
        original(self, *args, **kwargs)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", no_network)
    result = asyncio.run(verify_groq.verification())
    assert result["status"] == "passed" and result["mode"] == "mocked"
    assert tuple(case["scenario"] for case in result["cases"]) == verify_groq.SCENARIOS
    assert result["inference_requests"] == 2
    assert all(case["provider_calls"] == 1 and case["hypothesis_count"] == 1 for case in result["cases"])


def test_groq_compatibility_strict_grounding_and_secrets(monkeypatch, capsys):
    enable_mocked_live(monkeypatch)
    captured = []
    def respond(request):
        captured.append(request)
        body = json.loads(request.content)
        assert str(request.url) == verify_groq.ENDPOINT
        assert request.headers["Authorization"] == "Bearer PRIVATE_TEST_TOKEN"
        assert body["model"] == "openai/gpt-oss-20b"
        assert "store" not in body and body["n"] == 1 and body["stream"] is False
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        assert body["max_completion_tokens"] <= 2048
        for forbidden in ("PRIVATE", "account_id", "transfer_id", '"balance"', '"amount"', "trace_id", "correlation_id"):
            assert forbidden not in request.content.decode()
        return verify_groq.mocked_completion(request)
    install_transport(monkeypatch, respond)
    assert verify_groq.main(["--live"]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["status"] == "passed" and len(captured) == result["inference_requests"] == 2
    observed = [json.loads(json.loads(request.content)["messages"][1]["content"])["observations"] for request in captured]
    assert [next(row["id"] for row in rows if row["source"] == "rule") for rows in observed] == [
        "rule.high_transfer_failure_rate", "rule.elevated_p95_latency"]
    assert "PRIVATE" not in output.out + output.err


@pytest.mark.parametrize("mode", ["rate_limit", "unavailable", "timeout", "invalid", "invented"])
def test_provider_failures_consume_two_slots_without_retry(mode, monkeypatch):
    enable_mocked_live(monkeypatch)
    captured = []
    def respond(request):
        captured.append(request)
        if mode == "timeout": raise httpx.ReadTimeout("PRIVATE")
        if mode == "invalid": return httpx.Response(200, text="PRIVATE malformed")
        if mode == "invented":
            return httpx.Response(200, json={"choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"hypotheses": [{"kind": "database_call_degradation",
                "supporting_evidence": ["span.999.999"], "confidence": "moderate"}],
                "uncertainty": ["causality_unconfirmed"], "recommended_investigation_steps": ["collect_additional_evidence"]})}}]})
        return httpx.Response(429 if mode == "rate_limit" else 503, text="PRIVATE")
    install_transport(monkeypatch, respond)
    result = asyncio.run(verify_groq.verification(live=True))
    assert result["status"] == "failed" and len(captured) == result["inference_requests"] == 2
    assert all(case["rca_status"] == "undetermined" for case in result["cases"])
    assert "PRIVATE" not in json.dumps(result)


def test_request_budget_hard_limit_including_failures_and_concurrency():
    class Failing:
        def __init__(self): self.calls = 0
        async def analyze(self, *args):
            self.calls += 1
            raise ProviderFailure("rate_limited")
    async def run():
        provider = Failing()
        budget = verify_groq.TwoRequestBudget(provider)
        results = await asyncio.gather(*(budget.analyze({}, {}) for _ in range(5)), return_exceptions=True)
        assert all(isinstance(value, ProviderFailure) for value in results)
        assert provider.calls == budget.requests == 2
    asyncio.run(run())


def test_live_flag_alone_cannot_enable_inference(monkeypatch):
    enable_mocked_live(monkeypatch)
    monkeypatch.delenv("BANKOPS_AGENT_GROQ_LIVE_VERIFY")
    def unexpected(*args, **kwargs): raise AssertionError("No provider construction allowed")
    monkeypatch.setattr(verify_groq, "OpenAICompatibleProvider", unexpected)
    result = asyncio.run(verify_groq.verification(live=True))
    assert result["status"] == "blocked" and result["inference_requests"] == 0


@pytest.mark.parametrize("setting,value", [("LLM_PROVIDER", "disabled"), ("LLM_URL", "https://other.invalid/chat"),
    ("LLM_MODEL", "other-model"), ("LLM_CHAT_INCLUDE_STORE", "true"), ("LLM_API_KEY", "")])
def test_live_guard_requires_exact_groq_profile(setting, value, monkeypatch):
    enable_mocked_live(monkeypatch)
    monkeypatch.setenv("BANKOPS_AGENT_" + setting, value)
    result = asyncio.run(verify_groq.verification(live=True))
    assert result["status"] == "blocked" and result["inference_requests"] == 0


def test_cli_never_echoes_bad_arguments_or_exceptions(monkeypatch, capsys):
    with pytest.raises(SystemExit): verify_groq.main(["--key", "PRIVATE"])
    async def failed(**kwargs): raise RuntimeError("PRIVATE")
    monkeypatch.setattr(verify_groq, "verification", failed)
    previous = logging.root.manager.disable
    assert verify_groq.main([]) == 2
    assert logging.root.manager.disable == previous
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err


def test_transport_explicitly_disables_retries_and_environment_proxy(monkeypatch):
    from bankops_agent.rca.provider import post_json
    captured = []
    def factory(**kwargs):
        captured.append(kwargs)
        return httpx.MockTransport(lambda request: httpx.Response(200, content=b"{}"))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", factory)
    config = Settings(llm_provider="openai_compatible", llm_url=verify_groq.ENDPOINT,
                      llm_model=verify_groq.MODEL, llm_api_key="PRIVATE", llm_chat_include_store=False)
    assert asyncio.run(post_json(config, {})) == b"{}"
    assert captured == [{"retries": 0, "trust_env": False}]
