"""Actual four-node graph and provider adapter; transport is mocked, never inference."""

import asyncio
import json

from fastapi.testclient import TestClient
import httpx2 as httpx
from pydantic import ValidationError
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.rag.outbound import OutboundBlocked, verify_outbound
from bankops_agent.rca.analysis import RCAAnalyzer
from bankops_agent.rca.provider import (
    OpenAICloudProvider,
    OpenAICompatibleProvider,
    ProviderFailure,
    create_provider,
)
from bankops_agent.workflow import build_workflow, run_workflow


@pytest.fixture(autouse=True)
def forbid_real_provider_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Real provider transport must never execute in tests")

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        forbidden,
    )


def config(**changes):
    return Settings(
        **(
            {
                "environment": "test",
                "rag_enabled": True,
                "evidence_mode": "synthetic_demo",
                "llm_provider": "openai_cloud",
                "llm_external_opt_in": True,
                "llm_model": "gpt-5-mini",
                "llm_api_key": "synthetic-test-credential",
            }
            | changes
        )
    )


def response(request, change=None):
    payload = json.loads(request.content)
    evidence = json.loads(payload["messages"][1]["content"])

    observed = next(
        row for row in evidence["observations"] if row["supports"]
    )

    kind = observed["supports"][0]

    source = next(
        row
        for row in evidence["retrieved_sources"]
        if kind in row["supports"]
    )

    value = {
        "hypotheses": [
            {
                "kind": kind,
                "supporting_evidence": [observed["id"]],
                "retrieved_sources": [
                    "invented" if change == "citation" else source["id"]
                ],
                "confidence": "low",
            }
        ],
        "uncertainty": [
            "causality_unconfirmed",
            "bounded_sample",
        ],
        "recommended_investigation_steps": [
            "collect_additional_evidence"
        ],
    }

    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(value),
                    },
                }
            ]
        },
    )


def sources(settings):
    return create_app(settings).app.state


def run(settings, transport):
    state = sources(settings)

    state.rca_analyzer = RCAAnalyzer(
        settings,
        create_provider(settings, transport=transport),
    )

    return asyncio.run(
        run_workflow(build_workflow(state))
    )


@pytest.mark.parametrize(
    "scenario",
    ["http_errors", "latency", "service_down"],
)
def test_real_rag_and_graph_with_mocked_cloud_transport(scenario):
    seen = []

    def mocked(request):
        seen.append(request)
        return response(request)

    settings = config(synthetic_scenario=scenario)

    result = run(
        settings,
        httpx.MockTransport(mocked),
    )

    assert result.evidence_mode == "synthetic_demo"
    assert result.rca.status == "hypotheses"
    assert result.rca.retrieval.status == "matched"
    assert not result.rca.root_cause_confirmed

    assert len(seen) == 1

    payload = json.loads(seen[0].content)

    assert (
        str(seen[0].url)
        == "https://api.openai.com/v1/chat/completions"
    )

    assert payload["store"] is False
    assert payload["stream"] is False
    assert payload["n"] == 1

    assert (
        seen[0].headers["Authorization"]
        == "Bearer synthetic-test-credential"
    )

    text = payload["messages"][1]["content"]
    context = json.loads(text)
    assert context["classification"] == "synthetic"
    for observation in context["observations"]:
        assert set(observation) == {"id", "source", "observation", "supports"}

    # Reject sensitive JSON fields without rejecting safe
    # predefined observation labels such as threshold_reached.
    for private in (
        '"trace_id"',
        '"correlation_id"',
        '"timestamp"',
        '"observed_value"',
        '"threshold"',
        "synthetic-test-credential",
    ):
        assert private not in text

    assert (
        "synthetic-test-credential"
        not in result.model_dump_json()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"llm_external_opt_in": False},
        {"evidence_mode": "operational"},
        {"llm_chat_include_store": False},
    ],
)
def test_cloud_opt_in_and_data_controls_cannot_be_bypassed_with_a_mock(
    changes,
):
    called = []
    settings = config(**changes)
    state = sources(settings)

    # Operational mode deliberately receives synthetic
    # collectors only for this test.
    if settings.evidence_mode == "operational":
        from bankops_agent.rag.synthetic import collectors

        data = collectors(settings)

        (
            state.prometheus_collector,
            state.jaeger_collector,
            state.log_collector,
        ) = (
            data.prometheus_collector,
            data.jaeger_collector,
            data.log_collector,
        )

    state.rca_analyzer = RCAAnalyzer(
        settings,
        OpenAICloudProvider(
            settings,
            transport=httpx.MockTransport(
                lambda request: called.append(request)
                or response(request)
            ),
        ),
    )

    result = asyncio.run(
        run_workflow(build_workflow(state))
    )

    assert result.rca.reason == "outbound_blocked"
    assert not called


def captured_context():
    seen = []
    settings = config()

    run(
        settings,
        httpx.MockTransport(
            lambda request: seen.append(request)
            or response(request)
        ),
    )

    return (
        settings,
        json.loads(
            json.loads(seen[0].content)["messages"][1]["content"]
        ),
    )


@pytest.mark.parametrize(
    "change",
    [
        "pii",
        "secret",
        "timestamp",
        "source_text",
        "source_id",
        "extra",
        "classification",
    ],
)
def test_outbound_payload_tampering_blocked(change):
    settings, context = captured_context()

    if change in ("pii", "secret", "timestamp"):
        context["observations"][0][change] = "must-not-leave"

    elif change == "source_text":
        context["retrieved_sources"][0]["content"] += (
            " private material"
        )

    elif change == "source_id":
        context["retrieved_sources"][0]["id"] = "doc.unreviewed"

    elif change == "extra":
        context["customer_record"] = {
            "name": "Example Person"
        }

    else:
        context["classification"] = "production"

    with pytest.raises(OutboundBlocked):
        verify_outbound(settings, context)


def test_unreviewed_synthetic_label_does_not_grant_cloud_export(
    tmp_path,
):
    from test_rag import document

    (tmp_path / "incident.json").write_bytes(document())

    seen = []

    result = run(
        config(rag_corpus_directory=str(tmp_path)),
        httpx.MockTransport(
            lambda request: seen.append(request)
            or response(request)
        ),
    )

    assert result.rca.reason == "outbound_blocked"
    assert not seen


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "unavailable"),
        (429, "rate_limited"),
        (503, "unavailable"),
        (302, "unavailable"),
    ],
)
def test_provider_failures_preserve_deterministic_report(
    status,
    reason,
):
    seen = []

    def mocked(request):
        seen.append(request)
        return httpx.Response(
            status,
            text="SECRET PRIVATE PROVIDER DIAGNOSTICS",
        )

    result = run(
        config(),
        httpx.MockTransport(mocked),
    )

    assert result.detection.state == "incident"
    assert result.rca.reason == reason
    assert len(seen) == 1

    assert "PRIVATE" not in result.model_dump_json()
    assert result.rca.retrieval.sources


def test_cloud_invalid_citation_is_rejected_independently():
    result = run(
        config(),
        httpx.MockTransport(
            lambda request: response(request, "citation")
        ),
    )

    assert result.rca.reason == "invalid_output"
    assert not result.rca.hypotheses


def test_inference_disabled_still_has_retrieval_and_unchanged_four_nodes():
    settings = Settings(
        rag_enabled=True,
        evidence_mode="synthetic_demo",
    )

    state = sources(settings)
    graph = build_workflow(state)

    assert set(graph.get_graph().nodes) == {
        "__start__",
        "__end__",
        "detection",
        "evidence_collection",
        "report_assembly",
        "rca",
    }

    result = asyncio.run(
        run_workflow(graph)
    )

    assert result.rca.reason == "disabled"
    assert result.rca.retrieval.sources
    assert result.evidence_mode == "synthetic_demo"


def test_legacy_real_transport_also_requires_new_export_controls():
    settings = Settings(
        llm_provider="openai_compatible",
        llm_url="https://provider.invalid/chat",
        llm_api_key="test",
    )

    with pytest.raises(ProviderFailure) as error:
        asyncio.run(
            OpenAICompatibleProvider(settings).analyze(
                {"arbitrary": "private"},
                {},
            )
        )

    assert error.value.reason == "outbound_blocked"


@pytest.mark.parametrize(
    "changes",
    [
        {"llm_url": "https://other.invalid/chat"},
        {"llm_api_key": None},
        {"llm_model": "rca"},
        {"remediation_enabled": True},
        {"airflow_enabled": True},
    ],
)
def test_invalid_cloud_profile_and_no_autonomous_demo_actions(
    changes,
):
    with pytest.raises(ValidationError):
        config(**changes)


def test_environment_credentials_masked_and_no_implicit_cloud_opt_in(
    monkeypatch,
):
    monkeypatch.setenv(
        "BANKOPS_AGENT_LLM_API_KEY",
        "must-never-be-logged",
    )

    settings = Settings()

    assert settings.llm_provider == "disabled"
    assert not settings.llm_external_opt_in

    assert "must-never-be-logged" not in repr(settings)
    assert (
        "must-never-be-logged"
        not in settings.model_dump_json()
    )


def test_isolated_fastapi_workflow_auth_and_human_approval_safeguards(
    monkeypatch,
    tmp_path,
    log_output,
):
    import hashlib
    import secrets

    deployment, proposer, reviewer = (
        secrets.token_urlsafe(32)
        for _ in range(3)
    )

    settings = config(
        api_token_sha256=hashlib.sha256(
            deployment.encode()
        ).hexdigest(),
        approval_db_path=str(
            tmp_path / "approvals.sqlite3"
        ),
        approval_proposer_token_sha256=hashlib.sha256(
            proposer.encode()
        ).hexdigest(),
        approval_reviewer_token_sha256=hashlib.sha256(
            reviewer.encode()
        ).hexdigest(),
    )

    import bankops_agent.app as app_module

    seen = []

    monkeypatch.setattr(
        app_module,
        "create_provider",
        lambda s: create_provider(
            s,
            transport=httpx.MockTransport(
                lambda request: seen.append(request)
                or response(request)
            ),
        ),
    )

    logger, stream = log_output

    with TestClient(
        create_app(settings, logger=logger)
    ) as client:

        assert (
            client.post("/workflows/investigate").status_code
            == 401
        )

        assert (
            client.post(
                "/workflows/investigate",
                headers={
                    "Authorization": "Bearer " + deployment
                },
                json={"evidence": "private"},
            ).status_code
            == 400
        )

        response_value = client.post(
            "/workflows/investigate",
            headers={
                "Authorization": "Bearer " + deployment
            },
        )

        assert response_value.status_code == 200
        assert (
            response_value.json()["rca"]["status"]
            == "hypotheses"
        )

        assert len(seen) == 1

        proposal = {
            "action": "CHECK_SERVICE_HEALTH",
            "evidence_references": [
                "rule.high_http_error_rate"
            ],
        }

        base = "/remediation/proposals"

        assert (
            client.post(
                base,
                json=proposal,
                headers={
                    "Authorization": "Bearer " + reviewer
                },
            ).status_code
            == 403
        )

        created = client.post(
            base,
            json=proposal,
            headers={
                "Authorization": "Bearer " + proposer
            },
        ).json()

        url = base + "/" + created["proposal_id"]

        assert (
            client.post(
                url + "/approve",
                json={"reason": "reviewed_evidence"},
                headers={
                    "Authorization": "Bearer " + proposer
                },
            ).status_code
            == 403
        )

        assert (
            client.post(
                url + "/approve",
                json={"reason": "reviewed_evidence"},
                headers={
                    "Authorization": "Bearer " + reviewer
                },
            ).status_code
            == 200
        )

        assert (
            client.post(
                url + "/execute",
                json={
                    "action": "CHECK_SERVICE_HEALTH",
                    "parameters": {
                        "service": "banking-service"
                    },
                },
                headers={
                    "Authorization": "Bearer " + reviewer
                },
            ).status_code
            == 503
        )

    assert all(
        key not in stream.getvalue()
        for key in (
            deployment,
            proposer,
            reviewer,
            "synthetic-test-credential",
        )
    )
