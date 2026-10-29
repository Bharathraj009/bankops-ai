"""Isolated UI fixture: real agent contracts/graph, synthetic collectors, no external I/O.

Run with the existing agent Python 3.12 environment. --fake-rca explicitly enables
an in-memory deterministic test provider; it is not an LLM or network adapter.
Default RCA stays disabled. No agent/banking configuration is modified.
"""
import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent" / "src"))

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.evidence.prometheus import DETECTION_QUERIES, MetricEvidence, PrometheusEvidence
from bankops_agent.evidence.jaeger import JaegerEvidence, TraceEvidence, SpanEvidence
from bankops_agent.evidence.logs import LogEvidence, LogEvent
from bankops_agent.rca.analysis import RCAAnalyzer
import uvicorn

TRACE = "a" * 32
CORRELATION = "11111111-1111-4111-8111-111111111111"


class Metrics:
    async def collect_for_detection(self):
        now = datetime.now(UTC)
        values = dict(api_request_rate=20, api_error_rate=0.2, api_latency_p95=0.2,
                      transfer_success_rate=2, transfer_failure_rate=0,
                      banking_availability=1, transfer_request_rate=2)
        return PrometheusEvidence(evaluated_at=now, collected_at=now, status="ok", metrics=tuple(
            MetricEvidence(name=name, unit=unit, status="ok", value=values[name], sampled_at=now)
            for name, unit, _ in DETECTION_QUERIES))


class Traces:
    async def collect(self):
        now = datetime.now(UTC)
        return JaegerEvidence(window_start=now-timedelta(seconds=300), window_end=now,
            collected_at=now, slow_span_seconds=1, status="ok", traces=(TraceEvidence(
                trace_id=TRACE, started_at=now, duration_seconds=2, failed=True,
                slow_span_count=1, failed_span_count=1, truncated=False,
                spans=(SpanEvidence(span_id="b"*16, name="db.call", started_at=now,
                    duration_seconds=2, failed=True, slow=True),)),))


class Logs:
    async def collect(self):
        now = datetime.now(UTC)
        return LogEvidence(window_start=now-timedelta(seconds=300), window_end=now,
            collected_at=now, status="ok", events=[LogEvent(timestamp=now, level="ERROR",
                event_type="http_request_completed", trace_id=TRACE, correlation_id=CORRELATION)])


class SyntheticProvider:
    async def analyze(self, evidence, schema):
        # Bounded, deliberately synthetic result passes through the REAL RCA validator.
        return json.dumps({"hypotheses": [{"kind": "http_error_degradation",
            "supporting_evidence": ["rule.high_http_error_rate"], "confidence": "low"}],
            "uncertainty": ["dependencies_not_observed"],
            "recommended_investigation_steps": ["compare_metric_windows", "collect_additional_evidence"]}).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, choices=(18060,18061), default=18060)
    parser.add_argument("--fake-rca", action="store_true")
    args = parser.parse_args()
    settings = Settings(environment="test", llm_provider="disabled", llm_url=None,
        llm_api_key=None, approval_db_path=None, remediation_enabled=False, airflow_enabled=False)
    app = create_app(settings)
    app.app.state.prometheus_collector = Metrics()
    app.app.state.jaeger_collector = Traces()
    app.app.state.log_collector = Logs()
    if args.fake_rca:
        app.app.state.rca_analyzer = RCAAnalyzer(settings, SyntheticProvider())
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_config=None)


if __name__ == "__main__":
    main()
