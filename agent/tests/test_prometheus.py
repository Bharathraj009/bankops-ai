import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx2 as httpx
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.evidence.prometheus import PrometheusCollector, QUERIES


def vector(request, value="0.25", **extra):
    return {"status": "success", "data": {"resultType": "vector", "result": [
        {"metric": {}, "value": [float(request.url.params["time"]), value]}
    ]}, **extra}


def collect(handler, **settings):
    return asyncio.run(PrometheusCollector(Settings(**settings), transport=httpx.MockTransport(handler)).collect())


def test_collects_fixed_aggregates_at_one_timestamp_without_forwarding_data():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=vector(request))

    evidence = collect(respond)
    assert evidence.status == "ok"
    assert len(evidence.metrics) == len(requests) == 5
    assert {r.url.params["query"] for r in requests} == {q[2] for q in QUERIES}
    assert len({r.url.params["time"] for r in requests}) == 1
    for request in requests:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/query"
        assert set(request.url.params) == {"query", "time", "timeout"}
        assert not request.content
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
    for metric in evidence.metrics:
        assert metric.status == "ok" and metric.value == 0.25
        assert metric.sampled_at == evidence.evaluated_at
    assert evidence.collected_at >= evidence.evaluated_at
    assert evidence.evaluated_at.tzinfo == timezone.utc


def test_queries_match_existing_dashboard():
    dashboard = json.loads((Path(__file__).parents[2] / "monitoring/grafana/dashboards/bankops-ai.json").read_text())
    # Whitespace is irrelevant to these fixed PromQL expressions.
    normalize = lambda expression: "".join(expression.split())
    assert [normalize(q[2]) for q in QUERIES] == [normalize(p["targets"][0]["expr"]) for p in dashboard["panels"][:5]]


@pytest.mark.parametrize("value", ["NaN", "+Inf", "-Inf"])
def test_nonfinite_values_are_missing_not_zero(value):
    result = collect(lambda r: httpx.Response(200, json=vector(r, value)))
    assert result.status == "unavailable"
    assert all(m.status == "missing" and m.value is None and m.sampled_at is None for m in result.metrics)
    assert "NaN" not in result.model_dump_json()


def test_empty_vectors_and_partial_results():
    def respond(request):
        if request.url.params["query"] == QUERIES[2][2]:
            return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}})
        return httpx.Response(200, json=vector(request, "0"))

    result = collect(respond)
    assert result.status == "partial"
    assert result.metrics[2].status == "missing" and result.metrics[2].value is None
    assert result.metrics[0].value == 0  # Observed zero is distinct from missing.


@pytest.mark.parametrize("code", [301, 302, 401, 500, 503])
def test_http_failures_and_redirects_are_not_followed_or_exposed(code):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(code, text="PRIVATE_REMOTE_BODY", headers={"Location": "https://private.example/account"})

    result = collect(respond)
    assert len(seen) == 5
    assert all(m.status == "unavailable" for m in result.metrics)
    assert "PRIVATE" not in result.model_dump_json() and "private.example" not in result.model_dump_json()


@pytest.mark.parametrize("failure,status", [(httpx.ConnectError, "unavailable"), (httpx.ReadTimeout, "timeout")])
def test_transport_failures_are_safe(failure, status):
    def respond(request):
        raise failure("PRIVATE_CONNECTION_DETAIL", request=request)

    result = collect(respond)
    assert all(m.status == status for m in result.metrics)
    assert "PRIVATE" not in result.model_dump_json()


def test_wall_clock_deadline():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=vector(request))

    result = collect(slow, prometheus_timeout_seconds=0.01)
    assert all(m.status == "timeout" for m in result.metrics)


@pytest.mark.parametrize("payload", [None, [], {}, {"status": "success", "data": []},
    {"status": "success", "data": {"resultType": "matrix", "result": []}},
    {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {"account_id": "PRIVATE_ID"}, "value": [1, "1"]}]}},
    {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [True, "1"]}]}},
])
def test_malformed_or_labeled_results_are_rejected(payload):
    result = collect(lambda r: httpx.Response(200, content=json.dumps(payload)))
    assert all(m.status == "invalid_response" for m in result.metrics)
    assert "PRIVATE_ID" not in result.model_dump_json()


@pytest.mark.parametrize("option", ["warnings", "infos"])
def test_prometheus_annotations_do_not_become_evidence(option):
    result = collect(lambda r: httpx.Response(200, json=vector(r, **{option: ["PRIVATE_DETAILS"]})))
    assert all(m.status == "query_error" for m in result.metrics)
    assert "PRIVATE" not in result.model_dump_json()


def test_prometheus_query_error_is_bounded():
    result = collect(lambda r: httpx.Response(200, json={"status": "error", "error": "PRIVATE_PROMQL_ERROR"}))
    assert all(m.status == "query_error" for m in result.metrics)


@pytest.mark.parametrize("body", [b"not-json PRIVATE_DATA", b"x" * 65537], ids=["invalid-json", "oversized"])
def test_invalid_json_and_oversized_responses(body):
    result = collect(lambda r: httpx.Response(200, content=body))
    assert all(m.status == "invalid_response" for m in result.metrics)


def test_negative_and_invalid_ratio_values_are_rejected():
    result = collect(lambda r: httpx.Response(200, json=vector(r, "-1")))
    assert all(m.status == "invalid_response" for m in result.metrics)
    result = collect(lambda r: httpx.Response(200, json=vector(r, "2")))
    assert result.metrics[1].status == "invalid_response"
    assert result.metrics[0].value == 2


def test_old_samples_are_not_current_evidence():
    def respond(request):
        payload = vector(request)
        payload["data"]["result"][0]["value"][0] -= 301
        return httpx.Response(200, json=payload)

    assert all(m.status == "invalid_response" for m in collect(respond).metrics)


def test_evidence_route_and_health_are_separate(log_output):
    logger, output = log_output
    app = create_app(Settings(), logger=logger)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=vector(request))

    app.app.state.prometheus_collector = PrometheusCollector(Settings(), transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert calls == []
        response = client.get("/evidence/prometheus", headers={"Authorization": "PRIVATE_CREDENTIAL"})
        assert response.status_code == 200 and response.json()["status"] == "ok"
        assert len(calls) == 5
        assert response.headers["X-Correlation-ID"]
        assert client.post("/evidence/prometheus").status_code == 405
    assert "PRIVATE" not in output.getvalue()
