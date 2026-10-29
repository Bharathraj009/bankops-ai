"""Read-only orchestration; evidence matches establish identity, never causality."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from bankops_agent.detection.rules import DetectionResult, detect, with_airflow
from bankops_agent.evidence.airflow import AirflowEvidence
from bankops_agent.evidence.jaeger import JaegerEvidence
from bankops_agent.evidence.logs import LogEvidence
from bankops_agent.evidence.prometheus import DETECTION_QUERIES, MetricEvidence, PrometheusEvidence


class Correlation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    trace_id: str | None
    correlation_id: str | None
    trace_present: bool
    log_event_indexes: tuple[int, ...]


class ObservedFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    returned_trace_count: int
    failed_trace_count: int
    slow_span_count: int
    returned_log_event_count: int
    warn_event_count: int
    error_event_count: int


class InvestigationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    started_at: datetime
    completed_at: datetime
    evidence_status: Literal["complete", "partial", "unavailable"]
    detection: DetectionResult
    traces: JaegerEvidence
    logs: LogEvidence
    observed_facts: ObservedFacts
    correlations: tuple[Correlation, ...]
    # No causal inference exists at this stage. An empty list makes that explicit.
    possible_explanations: tuple[Literal["not_assessed"], ...] = ()


async def safely(call, fallback, timeout):
    try:
        async with asyncio.timeout(timeout):
            return await call()
    except Exception:
        # Do not return or log exception messages from evidence sources.
        return fallback()


async def collect_detection(state) -> DetectionResult:
    settings = state.settings

    def missing_metrics():
        now = datetime.now(UTC)
        return PrometheusEvidence(evaluated_at=now, collected_at=now, status="unavailable",
            metrics=tuple(MetricEvidence(name=name, unit=unit, status="unavailable")
                          for name, unit, _ in DETECTION_QUERIES))

    async def metrics_decision():
        metrics = await safely(state.prometheus_collector.collect_for_detection, missing_metrics,
                               settings.prometheus_timeout_seconds + 1)
        return detect(metrics, settings, detected_at=datetime.now(UTC))
    if not settings.airflow_enabled:
        return await metrics_decision()
    def missing_airflow():
        return AirflowEvidence(collected_at=datetime.now(UTC),status='unavailable')
    decision, airflow = await asyncio.gather(metrics_decision(),
        safely(state.airflow_collector.collect,missing_airflow,settings.airflow_timeout_seconds + 1))
    return with_airflow(decision,airflow)


async def collect_support(state) -> tuple[JaegerEvidence, LogEvidence]:
    settings = state.settings

    def missing_traces():
        now = datetime.now(UTC)
        return JaegerEvidence(window_start=now - timedelta(seconds=settings.jaeger_window_seconds),
            window_end=now, collected_at=now, slow_span_seconds=settings.jaeger_slow_span_seconds,
            status="unavailable")

    def missing_logs():
        now = datetime.now(UTC)
        return LogEvidence(window_start=now - timedelta(seconds=settings.log_window_seconds),
                           window_end=now, collected_at=now, status="unavailable")

    traces, logs = await asyncio.gather(
        safely(state.jaeger_collector.collect, missing_traces, settings.jaeger_timeout_seconds + 1),
        safely(state.log_collector.collect, missing_logs, 5),
    )
    return traces, logs


def assemble_report(started: datetime, decision: DetectionResult,
                    traces: JaegerEvidence, logs: LogEvidence) -> InvestigationReport:
    groups = {}
    trace_ids = {trace.trace_id for trace in traces.traces}
    for index, event in enumerate(logs.events):
        if event.trace_id or event.correlation_id:
            groups.setdefault((event.trace_id, event.correlation_id), []).append(index)
    correlations = tuple(Correlation(trace_id=trace_id, correlation_id=correlation_id,
        trace_present=trace_id in trace_ids, log_event_indexes=tuple(indexes))
        for (trace_id, correlation_id), indexes in groups.items())
    complete = decision.evidence.status == "ok" and traces.status == "ok" and logs.status == "ok"
    useful = any(metric.status == "ok" for metric in decision.evidence.metrics) or bool(traces.traces or logs.events)
    if decision.airflow is not None:
        complete = complete and decision.airflow.status == 'ok'
        useful = useful or bool(decision.airflow.runs)
    return InvestigationReport(started_at=started, completed_at=datetime.now(UTC),
        evidence_status="complete" if complete else "partial" if useful else "unavailable",
        detection=decision, traces=traces, logs=logs, correlations=correlations,
        observed_facts=ObservedFacts(returned_trace_count=len(traces.traces),
            failed_trace_count=sum(trace.failed for trace in traces.traces),
            slow_span_count=sum(trace.slow_span_count for trace in traces.traces),
            returned_log_event_count=len(logs.events),
            warn_event_count=sum(event.level == "WARN" for event in logs.events),
            error_event_count=sum(event.level == "ERROR" for event in logs.events)))


async def investigate(state) -> InvestigationReport:
    started = datetime.now(UTC)
    decision, (traces, logs) = await asyncio.gather(collect_detection(state), collect_support(state))
    return assemble_report(started, decision, traces, logs)
