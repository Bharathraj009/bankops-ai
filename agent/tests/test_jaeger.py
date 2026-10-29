import asyncio
from datetime import datetime, timezone
import json

import httpx2 as httpx
import pytest
from pydantic import ValidationError

from bankops_agent.config import Settings
from bankops_agent.evidence.jaeger import JaegerCollector, MAX_RESPONSE_BYTES


def make_span(end, trace=1, span=1, duration=2, name="http.request", code=0, ago=10):
    stamp = int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000 - int(ago * 1e9)
    return {"traceId": f"{trace:032x}", "spanId": f"{span:016x}", "name": name,
            "startTimeUnixNano": str(stamp), "endTimeUnixNano": str(stamp + int(duration * 1e9)),
            "status": {"code": code, "message": "PRIVATE_EXCEPTION"},
            "attributes": [{"key": "account.id", "value": {"stringValue": "PRIVATE_ACCOUNT_ID"}}],
            "events": [{"name": "PRIVATE_BODY"}], "traceState": "PRIVATE_CREDENTIAL"}


def payload(spans, service="banking-service"):
    return {"result": {"resourceSpans": [{"resource": {"attributes": [
        {"key": "service.name", "value": {"stringValue": service}},
        {"key": "customer", "value": {"stringValue": "PRIVATE_PERSON"}},
    ]}, "scopeSpans": [{"scope": {"name": "PRIVATE_SCOPE"}, "spans": spans}]}]}}


def request_end(request):
    return datetime.fromisoformat(request.url.params["query.start_time_max"])


def collect(handler, **options):
    return asyncio.run(JaegerCollector(Settings(**options), transport=httpx.MockTransport(handler)).collect())


def test_fixed_get_query_safe_fields_and_error_slow_indicators():
    seen = []

    def respond(request):
        seen.append(request)
        end = request_end(request)
        good = make_span(end, name="transfer.create", duration=1, code="STATUS_CODE_ERROR")
        unknown = make_span(end, span=2, duration=0.5, name="POST PRIVATE_REQUEST_BODY")
        unknown["attributes"].append({"key": "http.response.status_code", "value": {"intValue": "503"}})
        return httpx.Response(200, json=payload([good, unknown]))

    result = collect(respond)
    assert result.status == "ok" and len(result.traces) == 1
    request = seen[0]
    assert request.method == "GET" and request.url.path == "/api/v3/traces" and not request.content
    assert request.url.params["query.service_name"] == "banking-service"
    assert request.url.params["query.search_depth"] == "10"
    assert request.url.params["query.raw_traces"] == "true"
    assert "authorization" not in request.headers
    assert (result.window_end - result.window_start).total_seconds() == 300
    trace = result.traces[0]
    assert trace.trace_id == f"{1:032x}" and trace.duration_seconds == 1
    assert trace.failed and trace.failed_span_count == 2 and trace.slow_span_count == 1
    assert [s.name for s in trace.spans] == ["transfer.create", "other"]
    assert trace.spans[0].duration_seconds == 1 and trace.spans[0].slow
    assert not trace.spans[1].slow
    assert "PRIVATE" not in result.model_dump_json()
    assert "attributes" not in result.model_dump_json()


def test_filters_foreign_services_old_and_future_spans():
    def respond(request):
        end = request_end(request)
        data = payload([make_span(end, ago=301), make_span(end, ago=-1), make_span(end, ago=0.1, duration=1)])
        data["result"]["resourceSpans"] += payload([make_span(end)], "PRIVATE_SERVICE")["result"]["resourceSpans"]
        return httpx.Response(200, json=data)

    result = collect(respond)
    assert result.status == "missing" and not result.traces
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("options,expected_traces,expected_spans", [
    ({"jaeger_max_traces": 1}, 1, 3),
    ({"jaeger_max_spans_per_trace": 1}, 3, 3),
    ({"jaeger_max_total_spans": 2}, 1, 2),
])
def test_enforces_all_output_limits(options, expected_traces, expected_spans):
    def respond(request):
        end = request_end(request)
        return httpx.Response(200, json=payload([make_span(end, trace=t, span=s) for t in range(1, 4) for s in range(1, 4)]))

    result = collect(respond, **options)
    assert result.status == "partial" and result.truncated
    assert len(result.traces) == expected_traces
    assert sum(len(t.spans) for t in result.traces) == expected_spans


def test_pretty_json_and_streaming_envelopes():
    def pretty(request):
        return httpx.Response(200, text=json.dumps(payload([make_span(request_end(request))]), indent=2))

    assert collect(pretty).status == "ok"

    def streaming(request):
        end = request_end(request)
        return httpx.Response(200, text="\n".join(json.dumps(payload([make_span(end, trace=t)])) for t in (1, 2)))

    assert len(collect(streaming).traces) == 2


def test_duplicate_and_invalid_spans_are_marked_partial():
    def respond(request):
        good = make_span(request_end(request))
        bad = good | {"spanId": "PRIVATE_TRANSFER_ID"}
        reversed_interval = good | {"endTimeUnixNano": "0"}
        return httpx.Response(200, json=payload([good, good, bad, reversed_interval]))

    result = collect(respond)
    assert result.status == "partial" and len(result.traces[0].spans) == 1
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("body", [b"not-json PRIVATE", b"x" * (MAX_RESPONSE_BYTES + 1)], ids=["invalid-json", "oversized"])
def test_invalid_and_oversized_bodies(body):
    result = collect(lambda r: httpx.Response(200, content=body))
    assert result.status == "invalid_response" and not result.traces
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("data", [{}, {"error": {"message": "PRIVATE"}}, {"result": {"resourceSpans": "PRIVATE"}}, []])
def test_invalid_schemas(data):
    assert collect(lambda r: httpx.Response(200, json=data)).status == "invalid_response"


def test_empty_result_is_missing():
    result = collect(lambda r: httpx.Response(200, json={"result": {}}))
    assert result.status == "missing" and not result.traces


@pytest.mark.parametrize("message,status", [("No traces found", "missing"), ("PRIVATE_UNKNOWN_404", "unavailable")])
def test_jaeger_not_found_is_missing_only_for_known_empty_search(message, status):
    result = collect(lambda r: httpx.Response(404, json={"error": {"httpCode": 404, "message": message}}))
    assert result.status == status and not result.traces
    assert message not in result.model_dump_json()


@pytest.mark.parametrize("code", [302, 401, 500, 503])
def test_failures_and_redirects_are_safe(code):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(code, text="PRIVATE_BACKEND", headers={"Location": "https://private.example"})

    result = collect(respond)
    assert len(seen) == 1 and result.status == "unavailable"
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("error,status", [(httpx.ConnectError, "unavailable"), (httpx.ReadTimeout, "timeout")])
def test_transport_failure(error, status):
    def respond(request):
        raise error("PRIVATE_BACKEND", request=request)

    assert collect(respond).status == status


def test_wall_clock_timeout():
    async def respond(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"result": {}})

    assert collect(respond, jaeger_timeout_seconds=0.01).status == "timeout"


@pytest.mark.parametrize("field,value", [
    ("jaeger_url", "http://user:PRIVATE@localhost"), ("jaeger_url", "http://localhost?secret=x"),
    ("jaeger_url", "file:///private"), ("jaeger_timeout_seconds", 0), ("jaeger_timeout_seconds", 31),
    ("jaeger_window_seconds", 0), ("jaeger_window_seconds", 3601),
    ("jaeger_max_traces", 51), ("jaeger_max_spans_per_trace", 501), ("jaeger_max_total_spans", 2001),
    ("jaeger_slow_span_seconds", float("nan")),
])
def test_configuration_bounds(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})
