import asyncio
import copy
import json

from fastapi.testclient import TestClient
import httpx2 as httpx
from pydantic import ValidationError
import pytest

from bankops_agent import verify_rca
from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.rca.analysis import ModelAnalysis, RCAAnalyzer
from bankops_agent.rca.provider import OpenAICompatibleProvider, ProviderFailure, create_provider
from test_investigation import state
from test_rca import VALID, analyze
from test_workflow import install_sources


def settings(**changes):
    return Settings(**({"llm_provider": "openai_compatible", "llm_url": "https://provider.invalid/v1/chat/completions",
                       "llm_api_key": "PRIVATE_TEST_TOKEN", "llm_model": "test-model"} | changes))


def completion(content=None):
    return {"id": "PRIVATE_METADATA", "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(VALID) if content is None else content, "refusal": None}}]}


def test_chat_request_strict_schema_and_grounded_response():
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=completion())
    config = settings()
    result = analyze(OpenAICompatibleProvider(config, transport=httpx.MockTransport(respond)), config)
    assert result.status == "hypotheses" and result.hypotheses[0].supporting_evidence == ("rule.high_http_error_rate",)
    request = seen[0]
    body = json.loads(request.content)
    assert request.method == "POST" and str(request.url) == str(config.llm_url)
    assert request.headers["Authorization"] == "Bearer PRIVATE_TEST_TOKEN"
    assert body["model"] == "test-model"
    assert body["max_completion_tokens"] == config.llm_max_output_tokens
    assert body["stream"] is False and body["store"] is False and body["n"] == 1
    assert "untrusted" in body["messages"][0]["content"] and body["messages"][0]["role"] == "system"
    assert body["messages"][1]["role"] == "user"
    evidence = json.loads(body["messages"][1]["content"])
    assert evidence["incident_state"] == "incident"
    assert body["response_format"] == {"type": "json_schema", "json_schema": {
        "name": "bankops_rca", "strict": True, "schema": ModelAnalysis.model_json_schema()}}
    for forbidden in ("PRIVATE", "accountId", '"amount"', '"balance"', "trace_id", "correlation_id", "span_id"):
        assert forbidden not in request.content.decode()
    assert "PRIVATE" not in result.model_dump_json()
    assert len(request.content) <= config.llm_max_input_bytes and len(seen) == 1


@pytest.mark.parametrize("case", ["no_choices", "many_choices", "bad_index", "boolean_index", "length", "filter",
    "tool_finish", "refusal", "tool_call", "function_call", "wrong_role", "empty_content", "null_content",
    "content_parts", "error_envelope", "not_object", "bad_choice", "bad_message"])
def test_invalid_envelopes_and_unsupported_completions(case):
    value = completion()
    choice, message = value["choices"][0], value["choices"][0]["message"]
    if case == "no_choices": value["choices"] = []
    if case == "many_choices": value["choices"] *= 2
    if case == "bad_index": choice["index"] = 1
    if case == "boolean_index": choice["index"] = False
    if case in ("length", "filter", "tool_finish"): choice["finish_reason"] = {"length": "length", "filter": "content_filter", "tool_finish": "tool_calls"}[case]
    if case == "refusal": message["refusal"] = "PRIVATE refusal"
    if case == "tool_call": message["tool_calls"] = [{"function": {"name": "PRIVATE"}}]
    if case == "function_call": message["function_call"] = {}
    if case == "wrong_role": message["role"] = "system"
    if case == "empty_content": message["content"] = ""
    if case == "null_content": message["content"] = None
    if case == "content_parts": message["content"] = [{"text": "PRIVATE"}]
    if case == "error_envelope": value["error"] = {"message": "PRIVATE"}
    if case == "not_object": value = []
    if case == "bad_choice": value["choices"] = [None]
    if case == "bad_message": choice["message"] = None
    config = settings()
    provider = OpenAICompatibleProvider(config, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=value)))
    result = analyze(provider, config)
    assert result.status == "undetermined" and result.reason == "invalid_output"
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("body", [b"not JSON PRIVATE", b"\xff", b'{"choices":[],"choices":[]}', b"x" * 17000],
                         ids=["malformed", "encoding", "duplicate_key", "oversized_envelope"])
def test_bad_raw_response(body):
    config = settings()
    provider = OpenAICompatibleProvider(config, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
    assert analyze(provider, config).reason == "invalid_output"


@pytest.mark.parametrize("change", ["invented_ref", "confirmed", "malformed_content"])
def test_chat_content_still_passes_independent_rca_validation(change):
    value = copy.deepcopy(VALID)
    if change == "invented_ref": value["hypotheses"][0]["supporting_evidence"] = ["rule.PRIVATE"]
    if change == "confirmed": value["root_cause_confirmed"] = True
    content = "PRIVATE invalid JSON" if change == "malformed_content" else json.dumps(value)
    config = settings()
    provider = OpenAICompatibleProvider(config, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=completion(content))))
    result = analyze(provider, config)
    assert result.reason == "invalid_output" and not result.hypotheses


@pytest.mark.parametrize("status,reason", [(429, "rate_limited"), (401, "unavailable"), (403, "unavailable"),
                                          (503, "unavailable"), (302, "unavailable"), (400, "unavailable")])
def test_http_errors_no_retry_redirect_or_secret_echo(status, reason):
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(status, text="PRIVATE key diagnostics", headers={"Location": "https://other.invalid"})
    config = settings()
    result = analyze(OpenAICompatibleProvider(config, transport=httpx.MockTransport(respond)), config)
    assert result.reason == reason and len(seen) == 1
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("error,reason", [(httpx.ReadTimeout("PRIVATE"), "timeout"), (httpx.ConnectError("PRIVATE"), "unavailable")])
def test_transport_failures(error, reason):
    def respond(request): raise error
    config = settings()
    assert analyze(OpenAICompatibleProvider(config, transport=httpx.MockTransport(respond)), config).reason == reason


def test_actual_request_budget_prevents_network():
    def unexpected(request): raise AssertionError("Network must not be reached")
    config = settings(llm_max_input_bytes=1024)
    provider = OpenAICompatibleProvider(config, transport=httpx.MockTransport(unexpected))
    with pytest.raises(ProviderFailure) as error:
        asyncio.run(provider.analyze({"observations": ["x" * 2000]}, {}))
    assert error.value.reason == "input_limit"


def test_slow_stream_is_bounded_by_wall_clock():
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{"
            await asyncio.Event().wait()
    config = settings(llm_timeout_seconds=0.02)
    provider = OpenAICompatibleProvider(config, transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowStream())))
    assert analyze(provider, config).reason == "timeout"


@pytest.mark.parametrize("change", [{"llm_api_key": None}, {"llm_api_key": ""}, {"llm_api_key": " \t"},
    {"llm_api_key": "PRIVATE\n"}, {"llm_url": None}, {"llm_url": "http://remote.invalid/chat"}])
def test_required_safe_configuration(change):
    with pytest.raises(ValidationError): settings(**change)


def test_factory_env_and_default_disabled(monkeypatch):
    assert create_provider(Settings()) is None
    monkeypatch.setenv("BANKOPS_AGENT_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_URL", "https://provider.invalid/v1/chat/completions")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_API_KEY", "PRIVATE_TEST_TOKEN")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_MODEL", "test-model")
    config = Settings()
    assert isinstance(create_provider(config), OpenAICompatibleProvider)
    assert "PRIVATE" not in repr(config)


def test_workflow_selects_chat_adapter_and_get_never_calls_model(monkeypatch, log_output):
    config = settings()
    captured = []
    def respond(request):
        captured.append(request)
        return httpx.Response(200, json=completion())
    original = OpenAICompatibleProvider.__init__
    def mocked(self, settings, *, transport=None):
        original(self, settings, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(OpenAICompatibleProvider, "__init__", mocked)
    app = create_app(config, logger=log_output[0])
    install_sources(app, state(api_error_rate=0.5))
    with TestClient(app) as client:
        get = client.get("/incidents/investigate")
        assert captured == [] and "rca" not in get.json()
        response = client.post("/workflows/investigate")
    assert response.status_code == 200 and response.json()["rca"]["status"] == "hypotheses"
    assert len(captured) == 1
    assert "PRIVATE" not in response.text + log_output[1].getvalue()


def test_live_verifier_supports_adapter_without_real_calls(monkeypatch):
    monkeypatch.setenv("BANKOPS_AGENT_LIVE_RCA_VERIFY", "1")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_URL", "https://provider.invalid/v1/chat/completions")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_API_KEY", "PRIVATE_TEST_TOKEN")
    captured = []
    def respond(request):
        captured.append(request)
        return httpx.Response(200, json=completion())
    def factory(settings):
        return OpenAICompatibleProvider(settings, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(verify_rca, "OpenAICompatibleProvider", factory)
    result = asyncio.run(verify_rca.verification(live=True))
    assert result["live"]["status"] == "passed" and len(captured) == 2
    assert "PRIVATE" not in json.dumps(result)
