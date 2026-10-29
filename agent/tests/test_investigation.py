import asyncio
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx2 as httpx
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.evidence.jaeger import JaegerCollector, JaegerEvidence
from bankops_agent.evidence.logs import LogEvidence, LogEvent
from bankops_agent.evidence.prometheus import DETECTION_QUERIES, MetricEvidence, PrometheusCollector, PrometheusEvidence
from bankops_agent.investigation import investigate
from test_detection import HEALTHY
from test_jaeger import make_span, payload, request_end
from test_logs import event


class Source:
    def __init__(self, result=None, fail=False):
        self.result, self.fail, self.calls = result, fail, 0

    async def collect(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("PRIVATE source URL credential path")
        return self.result

    collect_for_detection = collect


def state(**values):
    now = datetime.now(UTC)
    metrics = PrometheusEvidence(evaluated_at=now, collected_at=now, status="ok", metrics=tuple(
        MetricEvidence(name=name, unit=unit, value=(HEALTHY | values)[name], sampled_at=now, status="ok")
        for name, unit, _ in DETECTION_QUERIES))
    return SimpleNamespace(settings=Settings(), prometheus_collector=Source(metrics),
        jaeger_collector=Source(JaegerEvidence(window_start=now-timedelta(seconds=300), window_end=now,
            collected_at=now, slow_span_seconds=1, status="missing")),
        log_collector=Source(LogEvidence(window_start=now-timedelta(seconds=300), window_end=now,
            collected_at=now, status="not_configured")))


def test_healthy_with_missing_support_is_partial():
    sources = state()
    result = asyncio.run(investigate(sources))
    assert result.detection.state == "healthy"
    assert result.evidence_status == "partial"
    assert result.traces.status == "missing" and result.logs.status == "not_configured"
    assert not result.possible_explanations and not result.correlations
    assert result.started_at <= result.completed_at
    assert sources.prometheus_collector.calls == sources.jaeger_collector.calls == sources.log_collector.calls == 1


@pytest.mark.parametrize("failed_source", ["prometheus_collector", "jaeger_collector", "log_collector"])
def test_sources_fail_independently(failed_source):
    sources = state(api_error_rate=0.5)
    getattr(sources, failed_source).fail = True
    result = asyncio.run(investigate(sources))
    assert result.detection.state == ("insufficient_data" if failed_source == "prometheus_collector" else "incident")
    assert "PRIVATE" not in result.model_dump_json()
    assert sources.prometheus_collector.calls == sources.jaeger_collector.calls == sources.log_collector.calls == 1


def test_all_failures_never_healthy_or_causal():
    sources = state()
    for source in (sources.prometheus_collector, sources.jaeger_collector, sources.log_collector):
        source.fail = True
    result = asyncio.run(investigate(sources))
    assert result.evidence_status == "unavailable"
    assert result.detection.state == "insufficient_data"
    assert all(rule.state == "insufficient_data" for rule in result.detection.rules)
    assert result.possible_explanations == ()


def test_incident_and_partial_metric_states_preserved():
    sources = state(api_error_rate=0.5)
    evidence = sources.prometheus_collector.result
    missing = evidence.metrics[2].model_copy(update={"status": "missing", "value": None, "sampled_at": None})
    sources.prometheus_collector.result = evidence.model_copy(update={"status": "partial", "metrics": (*evidence.metrics[:2], missing, *evidence.metrics[3:])})
    result = asyncio.run(investigate(sources))
    assert result.detection.state == "incident"
    assert result.detection.triggered_rules == ("high_http_error_rate",)
    assert result.detection.rules[2].state == "insufficient_data"
    assert result.detection.evidence.status == "partial"


def test_stale_and_low_traffic_not_healthy():
    sources = state(api_request_rate=0, transfer_request_rate=0)
    assert asyncio.run(investigate(sources)).detection.state == "insufficient_data"
    evidence = sources.prometheus_collector.result
    sources.prometheus_collector.result = evidence.model_copy(update={"evaluated_at": datetime.now(UTC)-timedelta(hours=1)})
    assert asyncio.run(investigate(sources)).detection.state == "insufficient_data"


def test_collectors_run_concurrently():
    sources = state()
    async def run():
        started = set()
        ready = asyncio.Event()
        async def collect(name, value):
            started.add(name)
            if len(started) == 3:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=1)
            return value
        for name in ("prometheus_collector", "jaeger_collector", "log_collector"):
            source = getattr(sources, name)
            method = lambda name=name, source=source: collect(name, source.result)
            source.collect = source.collect_for_detection = method
        result = await investigate(sources)
        assert started == {"prometheus_collector", "jaeger_collector", "log_collector"}
        assert result.detection.state == "healthy"
    asyncio.run(run())


@pytest.mark.parametrize("workflow", [False, True])
def test_http_integration_real_collectors_privacy_and_correlation(tmp_path, log_output, workflow):
    settings = Settings(log_source_directory=str(tmp_path), log_max_events=2, jaeger_max_traces=1)
    trace_id = f"{1:032x}"
    entries = [event(trace_id=trace_id), event(trace_id=trace_id), event(trace_id=f"{2:032x}")]
    now = datetime.now(UTC)
    for index, entry in enumerate(entries):
        entry["@timestamp"] = (now - timedelta(seconds=3-index)).isoformat()
    source = tmp_path / "banking.jsonl"
    source.write_text("\n".join(json.dumps(entry) for entry in entries)+"\n", encoding="utf-8")
    before = source.read_bytes()
    requests = []
    def prometheus(request):
        requests.append(request)
        query = request.url.params["query"]
        name = next(name for name, _, expression in DETECTION_QUERIES if expression == query)
        value = 0.5 if name == "api_error_rate" else HEALTHY[name]
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": [
            {"metric": {}, "value": [float(request.url.params["time"]), str(value)]}]}})
    def jaeger(request):
        requests.append(request)
        return httpx.Response(200, json=payload([make_span(request_end(request), code=2)]))
    logger, output = log_output
    app = create_app(settings, logger=logger)
    app.app.state.prometheus_collector = PrometheusCollector(settings, transport=httpx.MockTransport(prometheus))
    app.app.state.jaeger_collector = JaegerCollector(settings, transport=httpx.MockTransport(jaeger))
    with TestClient(app) as client:
        response = client.post("/workflows/investigate") if workflow else client.get("/incidents/investigate")
        assert client.get("/incidents/investigate?path=PRIVATE").status_code == 400
        assert client.post("/incidents/investigate").status_code == 405
    report = response.json()
    assert response.status_code == 200 and response.headers["X-Correlation-ID"]
    assert report["detection"]["state"] == "incident"
    assert report["detection"]["triggered_rules"] == ["high_http_error_rate"]
    assert report["evidence_status"] == "partial" and report["logs"]["truncated"]
    assert len(report["logs"]["events"]) == 2
    match = next(group for group in report["correlations"] if group["trace_id"] == trace_id)
    assert match["trace_present"] and len(match["log_event_indexes"]) == 1
    assert not next(group for group in report["correlations"] if group["trace_id"] != trace_id)["trace_present"]
    assert report["observed_facts"]["failed_trace_count"] == 1
    assert report["observed_facts"]["error_event_count"] == 2
    assert report["possible_explanations"] == []
    assert "PRIVATE" not in response.text + output.getvalue()
    assert str(tmp_path) not in response.text and source.read_bytes() == before
    assert len(requests) == 8 and all(request.method == "GET" and not request.content for request in requests)


def test_complete_support_and_correlation_only_groups():
    sources = state()
    sources.jaeger_collector.result = sources.jaeger_collector.result.model_copy(update={"status": "ok"})
    now = datetime.now(UTC)
    entry = LogEvent(timestamp=now, level="WARN", event_type="http_request_completed",
                     correlation_id="12345678-1234-1234-1234-123456789abc")
    sources.log_collector.result = sources.log_collector.result.model_copy(update={"status": "ok", "events": [entry, entry]})
    result = asyncio.run(investigate(sources))
    assert result.evidence_status == "complete"
    assert result.correlations[0].trace_id is None and not result.correlations[0].trace_present
    assert result.correlations[0].log_event_indexes == (0, 1)


@pytest.mark.parametrize("source", ["prometheus", "jaeger", "both"])
def test_http_remote_failures_keep_other_evidence(source, tmp_path):
    settings = Settings(log_source_directory=str(tmp_path))
    (tmp_path / "banking.jsonl").write_text(json.dumps(event())+"\n", encoding="utf-8")
    def respond(request):
        if "query.service_name" in request.url.params:
            if source in ("jaeger", "both"):
                raise httpx.ReadTimeout("PRIVATE upstream details")
            return httpx.Response(200, json=payload([make_span(request_end(request))]))
        if source in ("prometheus", "both"):
            return httpx.Response(503, text="PRIVATE failure response")
        name = next(name for name, _, query in DETECTION_QUERIES if query == request.url.params["query"])
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": [
            {"metric": {}, "value": [float(request.url.params["time"]), str(HEALTHY[name])]}]}})
    app = create_app(settings)
    app.app.state.prometheus_collector = PrometheusCollector(settings, transport=httpx.MockTransport(respond))
    app.app.state.jaeger_collector = JaegerCollector(settings, transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        response = client.get("/incidents/investigate")
    assert response.status_code == 200 and "PRIVATE" not in response.text
    report = response.json()
    assert report["evidence_status"] == "partial"
    assert len(report["logs"]["events"]) == 1
    assert report["detection"]["state"] == ("healthy" if source == "jaeger" else "insufficient_data")
    assert report["traces"]["status"] == ("ok" if source == "prometheus" else "timeout")


def test_orchestration_deadline_and_parent_cancellation():
    async def run():
        sources = state()
        sources.settings = Settings(prometheus_timeout_seconds=0.001)
        async def stalled():
            await asyncio.Event().wait()
        sources.prometheus_collector.collect_for_detection = stalled
        result = await investigate(sources)
        assert result.detection.state == "insufficient_data"
        assert result.detection.evidence.status == "unavailable"
        task = asyncio.create_task(investigate(sources))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
