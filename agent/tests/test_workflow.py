import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
import pytest

from bankops_agent.app import create_app
from bankops_agent.investigation import investigate
from bankops_agent.evidence.logs import LogEvent
from bankops_agent.workflow import build_workflow, run_workflow
from test_investigation import state


class FixedClock(datetime):
    instant = datetime.now(UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.instant if tz else cls.instant.replace(tzinfo=None)


@pytest.mark.parametrize("scenario", ["healthy", "incident", "low_traffic", "partial_metrics",
                                      "metrics_failure", "trace_failure", "log_failure", "all_failure"])
def test_workflow_matches_original_semantics(scenario, monkeypatch):
    sources = state(**({"api_error_rate": 0.5} if scenario == "incident" else
                      {"api_request_rate": 0} if scenario == "low_traffic" else {}))
    FixedClock.instant = datetime.now(UTC)
    monkeypatch.setattr("bankops_agent.investigation.datetime", FixedClock)
    monkeypatch.setattr("bankops_agent.workflow.datetime", FixedClock)
    if scenario == "partial_metrics":
        metric = sources.prometheus_collector.result.metrics[0].model_copy(
            update={"status": "missing", "value": None, "sampled_at": None})
        sources.prometheus_collector.result = sources.prometheus_collector.result.model_copy(
            update={"status": "partial", "metrics": (metric, *sources.prometheus_collector.result.metrics[1:])})
    for prefix, name in (("metrics", "prometheus_collector"), ("trace", "jaeger_collector"), ("log", "log_collector")):
        getattr(sources, name).fail = scenario in (f"{prefix}_failure", "all_failure")
    original = asyncio.run(investigate(sources))
    report = asyncio.run(run_workflow(build_workflow(sources)))
    assert report.model_dump(exclude={"rca"}) == original.model_dump()
    assert report.rca.status == "undetermined"
    assert report.possible_explanations == ()
    assert "PRIVATE" not in report.model_dump_json()
    assert all(source.calls == 2 for source in (sources.prometheus_collector, sources.jaeger_collector, sources.log_collector))


def test_transitions_join_both_parallel_branches_once():
    sources = state()
    async def run():
        graph = build_workflow(sources)
        updates = []
        with tracing_context(enabled=False):
            async for update in graph.astream({"started_at": datetime.now(UTC)}, stream_mode="updates"):
                updates.append(update)
        names = [next(iter(update)) for update in updates]
        assert set(names[:2]) == {"detection", "evidence_collection"}
        assert names[2:] == ["report_assembly", "rca"]
        assert updates[-2]["report_assembly"]["report"].detection.state == "healthy"
        assert updates[-1]["rca"]["rca"].status == "undetermined"
    asyncio.run(run())
    assert sources.prometheus_collector.calls == sources.jaeger_collector.calls == sources.log_collector.calls == 1


def test_ambient_tracing_disabled_inside_nodes(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    sources = state()
    original = sources.prometheus_collector.collect_for_detection
    observed = []
    async def checking():
        observed.append(get_tracing_context()["enabled"])
        return await original()
    sources.prometheus_collector.collect_for_detection = checking
    with tracing_context(enabled=True):
        report = asyncio.run(run_workflow(build_workflow(sources)))
    assert report.detection.state == "healthy" and observed == [False]


def install_sources(app, sources):
    # The compiled graph captures the application state, not a copy of collectors.
    for name in ("prometheus_collector", "jaeger_collector", "log_collector"):
        setattr(app.app.state, name, getattr(sources, name))


def test_post_endpoint_contract_and_get_unchanged(log_output):
    logger, output = log_output
    app = create_app(logger=logger)
    install_sources(app, state(api_error_rate=0.5))
    with TestClient(app) as client:
        response = client.post("/workflows/investigate")
        original = client.get("/incidents/investigate")
        assert client.get("/workflows/investigate").status_code == 405
        assert client.post("/incidents/investigate").status_code == 405
    assert response.status_code == original.status_code == 200
    assert response.headers["X-Correlation-ID"]
    assert set(response.json()) == set(original.json()) | {"rca"}
    assert "rca" not in original.json()
    assert response.json()["rca"]["status"] == "undetermined"
    assert response.json()["detection"] == original.json()["detection"] | {
        "detected_at": response.json()["detection"]["detected_at"]}
    assert response.json()["detection"]["state"] == "incident"
    assert "PRIVATE" not in response.text + output.getvalue()


@pytest.mark.parametrize("kwargs", [{"params": {"path": "PRIVATE"}}, {"json": {"input": "PRIVATE"}}, {"content": b"PRIVATE"}])
def test_caller_cannot_inject_state_sources_or_options(kwargs):
    app = create_app()
    sources = state()
    install_sources(app, sources)
    with TestClient(app) as client:
        response = client.post("/workflows/investigate", **kwargs)
    assert response.status_code == 400 and "PRIVATE" not in response.text
    assert sources.prometheus_collector.calls == sources.jaeger_collector.calls == sources.log_collector.calls == 0


def test_workflow_internal_failure_is_safe(log_output):
    class BrokenGraph:
        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("PRIVATE credentials")
    logger, output = log_output
    app = create_app(logger=logger)
    app.app.state.investigation_workflow = BrokenGraph()
    with TestClient(app) as client:
        response = client.post("/workflows/investigate")
    assert response.status_code == 503
    assert response.json() == {"detail": "Investigation workflow unavailable"}
    assert response.headers["X-Correlation-ID"] and "PRIVATE" not in output.getvalue()


def test_concurrent_invocations_have_isolated_state():
    async def run():
        graph = build_workflow(state())
        reports = await asyncio.gather(*(run_workflow(graph) for _ in range(4)))
        assert len({id(report) for report in reports}) == 4
        assert all(report.detection.state == "healthy" for report in reports)
    asyncio.run(run())


def test_exact_id_grouping_and_result_limits_reused(monkeypatch):
    sources = state()
    FixedClock.instant = datetime.now(UTC)
    monkeypatch.setattr("bankops_agent.investigation.datetime", FixedClock)
    monkeypatch.setattr("bankops_agent.workflow.datetime", FixedClock)
    entry = LogEvent(timestamp=FixedClock.instant, level="ERROR", event_type="transfer_outcome",
                     correlation_id="12345678-1234-1234-1234-123456789abc", trace_id=f"{1:032x}")
    sources.log_collector.result = sources.log_collector.result.model_copy(
        update={"status": "partial", "truncated": True, "events": [entry, entry, entry.model_copy(update={"trace_id": None})]})
    graph_result = asyncio.run(run_workflow(build_workflow(sources)))
    assert graph_result.model_dump(exclude={"rca"}) == asyncio.run(investigate(sources)).model_dump()
    assert graph_result.logs.truncated and graph_result.evidence_status == "partial"
    assert graph_result.correlations[0].log_event_indexes == (0, 1)
    assert graph_result.correlations[1].log_event_indexes == (2,)
    assert all(not group.trace_present for group in graph_result.correlations)


def test_graph_deadline_and_cancellation_preserve_semantics():
    async def run():
        sources = state()
        from bankops_agent.config import Settings
        sources.settings = Settings(prometheus_timeout_seconds=0.001)
        async def stalled():
            await asyncio.Event().wait()
        sources.prometheus_collector.collect_for_detection = stalled
        graph = build_workflow(sources)
        report = await run_workflow(graph)
        assert report.detection.state == "insufficient_data"
        assert report.detection.evidence.status == "unavailable"
        task = asyncio.create_task(run_workflow(graph))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
