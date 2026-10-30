"""Server-owned fictional observations; no banking/network reads in demo mode."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from bankops_agent.evidence.jaeger import JaegerEvidence, SpanEvidence, TraceEvidence
from bankops_agent.evidence.logs import LogEvidence, LogEvent
from bankops_agent.evidence.prometheus import DETECTION_QUERIES, MetricEvidence, PrometheusEvidence


class FixedSource:
    def __init__(self, value):
        self.value = value

    async def collect(self):
        return self.value

    async def collect_for_detection(self):
        return self.value


def collectors(settings):
    now = datetime.now(UTC)
    scenario = settings.synthetic_scenario
    values = {"api_request_rate": 10.0, "api_error_rate": 0.01, "api_latency_p95": 0.2,
              "transfer_success_rate": 2.0, "transfer_failure_rate": 0.0,
              "banking_availability": 1.0, "transfer_request_rate": 2.0}
    if scenario == "http_errors":
        values["api_error_rate"] = 0.5
    elif scenario == "latency":
        values["api_latency_p95"] = 2.5
    else:
        values["banking_availability"] = 0.0
    metrics = PrometheusEvidence(evaluated_at=now, collected_at=now, status="ok",
        metrics=tuple(MetricEvidence(name=name, unit=unit, status="ok", value=values[name], sampled_at=now)
                      for name, unit, _ in DETECTION_QUERIES))
    span = SpanEvidence(span_id="0000000000000001", name="db.call", started_at=now - timedelta(seconds=3),
        duration_seconds=2.0 if scenario == "latency" else 0.02, failed=False, slow=scenario == "latency")
    trace = TraceEvidence(trace_id="00000000000000000000000000000001", started_at=span.started_at,
        duration_seconds=span.duration_seconds, failed=False, slow_span_count=int(span.slow), failed_span_count=0,
        truncated=False, spans=(span,))
    traces = JaegerEvidence(window_start=now - timedelta(minutes=5), window_end=now, collected_at=now,
        slow_span_seconds=settings.jaeger_slow_span_seconds, status="ok", traces=(trace,))
    logs = LogEvidence(window_start=now - timedelta(minutes=5), window_end=now, collected_at=now, status="ok",
        events=[LogEvent(timestamp=now, level="WARN", event_type="http_request_completed")])
    return SimpleNamespace(prometheus_collector=FixedSource(metrics), jaeger_collector=FixedSource(traces),
                           log_collector=FixedSource(logs))


def permitted_observations(scenario):
    rule = {"http_errors": "high_http_error_rate", "latency": "elevated_p95_latency",
            "service_down": "banking_unavailable"}[scenario]
    kind = {"http_errors": "http_error_degradation", "latency": "latency_degradation",
            "service_down": "service_unavailability"}[scenario]
    rows = [{"id": "rule." + rule, "source": "rule", "observation": "service_down" if scenario == "service_down" else "threshold_reached", "supports": [kind]},
            {"id": "log.0", "source": "log", "observation": "warn_event", "supports": []}]
    if scenario == "latency":
        rows.append({"id": "span.0.0", "source": "span", "observation": "slow_or_failed_db_call",
                     "supports": ["database_call_degradation"]})
    return rows
