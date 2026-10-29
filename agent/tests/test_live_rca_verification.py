import asyncio
import json
import logging

import httpx2 as httpx
import pytest

from bankops_agent import verify_rca
from bankops_agent.rca.provider import JsonHTTPProvider


@pytest.mark.parametrize("scenario", verify_rca.SCENARIOS)
def test_synthetic_scenarios_run_complete_graph(scenario):
    settings = verify_rca.isolated_settings(llm_provider="json_http", llm_url="https://synthetic.invalid/rca")
    result = asyncio.run(verify_rca.verify_case(scenario, settings))
    assert result["passed"]
    assert result["provider_calls"] == (0 if scenario == "insufficient" else 1)


def test_default_cli_never_uses_network_or_ambient_sources(monkeypatch, capsys):
    monkeypatch.setenv("BANKOPS_AGENT_LLM_API_KEY", "PRIVATE_KEY")
    monkeypatch.setenv("BANKOPS_AGENT_LOG_SOURCE_DIRECTORY", "PRIVATE_PATH")
    original = httpx.AsyncClient.__init__
    def local_only(self, *args, **kwargs):
        assert kwargs.get("transport") is not None
        return original(self, *args, **kwargs)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", local_only)
    assert verify_rca.main([]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["automated"]["passed"] and result["live"]["status"] == "not_requested"
    assert "PRIVATE" not in output.out + output.err


@pytest.mark.parametrize("environment,blocker", [
    ({}, "explicit_environment_opt_in_required"),
    ({"BANKOPS_AGENT_LIVE_RCA_VERIFY": "1"}, "enabled_provider_required"),
    ({"BANKOPS_AGENT_LIVE_RCA_VERIFY": "1", "BANKOPS_AGENT_LLM_PROVIDER": "json_http"}, "gateway_url_required"),
])
def test_live_gate_requires_explicit_opt_in_and_configuration(environment, blocker, monkeypatch):
    monkeypatch.delenv("BANKOPS_AGENT_LIVE_RCA_VERIFY", raising=False)
    for name, value in environment.items(): monkeypatch.setenv(name, value)
    result = asyncio.run(verify_rca.verification(live=True))
    assert result["live"]["status"] == "blocked" and blocker in result["live"]["blockers"]


def test_bad_configuration_does_not_disclose_values(monkeypatch, capsys):
    monkeypatch.setenv("BANKOPS_AGENT_LIVE_RCA_VERIFY", "1")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_PROVIDER", "json_http")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_URL", "https://PRIVATE:PRIVATE@host/rca")
    assert verify_rca.main(["--live"]) == 2
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err
    assert json.loads(output.out)["live"]["blockers"] == ["invalid_llm_configuration"]


@pytest.mark.parametrize("status,live_status", [(200, "passed"), (429, "failed"), (503, "failed")])
def test_live_path_with_mock_gateway_never_sends_sensitive_evidence(status, live_status, monkeypatch):
    monkeypatch.setenv("BANKOPS_AGENT_LIVE_RCA_VERIFY", "1")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_PROVIDER", "json_http")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_URL", "https://gateway.invalid/rca")
    monkeypatch.setenv("BANKOPS_AGENT_LLM_API_KEY", "PRIVATE_KEY")
    captured = []
    def respond(request):
        captured.append(request)
        assert request.headers["Authorization"] == "Bearer PRIVATE_KEY"
        payload = request.content.decode()
        for forbidden in ("PRIVATE_KEY", "accountId", "account_id", '"amount"', '"balance"',
                          "correlation_id", "trace_id", "span_id", "request_body", "stack_trace"):
            assert forbidden not in payload
        return httpx.Response(status, json=verify_rca.model_response("incident"))
    def factory(settings, *, transport=None):
        return JsonHTTPProvider(settings, transport=transport or httpx.MockTransport(respond))
    monkeypatch.setattr(verify_rca, "JsonHTTPProvider", factory)
    result = asyncio.run(verify_rca.verification(live=True))
    assert result["automated"]["passed"] and result["live"]["status"] == live_status
    assert len(captured) == 2
    assert result["live"]["cases"][-1]["provider_calls"] == 0
    assert "PRIVATE" not in json.dumps(result)


def test_valid_abstention_not_misreported_as_hypotheses():
    class Abstaining:
        async def analyze(self, evidence, schema):
            return json.dumps({"hypotheses": [], "uncertainty": ["dependencies_not_observed"],
                "recommended_investigation_steps": ["collect_additional_evidence"]}).encode()
    result = asyncio.run(verify_rca.verify_case("incident", verify_rca.isolated_settings(), Abstaining()))
    assert result["passed"] and result["hypothesis_count"] == 0
    assert result["reason"] == "no_supported_hypotheses"


def test_cli_exception_is_sanitized(monkeypatch, capsys):
    async def failed(**kwargs): raise RuntimeError("PRIVATE credentials")
    monkeypatch.setattr(verify_rca, "verification", failed)
    assert verify_rca.main([]) == 2
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err
    assert json.loads(output.out)["reason"] == "safe_execution_failure"


def test_argument_errors_never_echo_credentials(capsys):
    with pytest.raises(SystemExit) as error:
        verify_rca.main(["--api-key", "PRIVATE_KEY"])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err


def test_cli_restores_logging_and_never_changes_inference_configuration(monkeypatch, capsys):
    import os
    before = dict(os.environ)
    level = logging.root.manager.disable
    assert verify_rca.main([]) == 0
    assert before == dict(os.environ)
    assert logging.root.manager.disable == level
