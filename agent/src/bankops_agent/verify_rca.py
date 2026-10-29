"""Opt-in synthetic verification. Never reads production evidence or prints secrets."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

import httpx2 as httpx

from bankops_agent.config import Settings
from bankops_agent.evidence.jaeger import JaegerCollector
from bankops_agent.evidence.logs import LogCollector
from bankops_agent.evidence.prometheus import DETECTION_QUERIES, PrometheusCollector
from bankops_agent.rca.analysis import RCAAnalyzer, evidence_catalog
from bankops_agent.rca.provider import JsonHTTPProvider, OpenAICompatibleProvider
from bankops_agent.workflow import build_workflow, run_workflow

SCENARIOS = ("incident", "insufficient", "contradictory", "timeout", "rate_limited", "unavailable",
             "malformed", "unsupported", "missing", "high_confidence", "confirmed")
EXPECTED = {"timeout": "timeout", "rate_limited": "rate_limited", "unavailable": "unavailable",
            "insufficient": "insufficient_evidence", "malformed": "invalid_output", "unsupported": "invalid_output",
            "missing": "invalid_output", "high_confidence": "invalid_output", "confirmed": "invalid_output"}
TARGET_SCENARIOS = {
    "elevated_transfer_failure_rate": ("high_transfer_failure_rate", "transfer_failure_degradation"),
    "high_api_latency": ("elevated_p95_latency", "latency_degradation"),
}


def isolated_settings(**overrides) -> Settings:
    # Explicit defaults override all ambient settings, including local file paths.
    values = {name: field.default for name, field in Settings.model_fields.items()}
    return Settings(**(values | overrides))


def configured_live_settings() -> Settings:
    values = {name: os.environ["BANKOPS_AGENT_" + name.upper()]
              for name in Settings.model_fields if name.startswith("llm_")
              and "BANKOPS_AGENT_" + name.upper() in os.environ}
    return isolated_settings(**values)


def configuration_summary() -> dict:
    provider = os.getenv("BANKOPS_AGENT_LLM_PROVIDER", "disabled")
    return {"provider": provider if provider in ("disabled", "json_http", "openai_compatible") else "invalid",
            "url_present": bool(os.getenv("BANKOPS_AGENT_LLM_URL")),
            "api_key_present": bool(os.getenv("BANKOPS_AGENT_LLM_API_KEY"))}


def model_response(mode: str) -> dict:
    hypothesis = {"kind": "http_error_degradation", "supporting_evidence": ["rule.high_http_error_rate"], "confidence": "low"}
    if mode == "unsupported":
        hypothesis["kind"] = "database_call_degradation"
    if mode == "high_confidence":
        hypothesis["confidence"] = "high"
    value = {"hypotheses": [hypothesis], "uncertainty": ["dependencies_not_observed"],
             "recommended_investigation_steps": ["compare_metric_windows", "collect_additional_evidence"]}
    if mode == "confirmed":
        value["root_cause_confirmed"] = True
    return value


async def verify_case(mode: str, settings: Settings, provider=None) -> dict:
    """Actual collectors + graph, exclusively synthetic local evidence transports."""
    with tempfile.TemporaryDirectory(prefix="bankops-rca-synthetic-") as directory:
        values = {name: getattr(settings, name) for name in Settings.model_fields}
        values.update(log_source_directory=directory, log_source_filename="banking.jsonl")
        local = Settings(**values)
        now = datetime.now(UTC)
        # Contradictory sample: elevated aggregate errors but a fast successful DB span.
        # A successful sample cannot disprove an aggregate, or justify DB degradation.
        source_file = Path(directory) / "banking.jsonl"
        source_file.write_text(json.dumps({"@timestamp": (now-timedelta(seconds=1)).isoformat(),
            "service": {"name": "banking-service"}, "log": {"level": "WARN",
            "logger": "com.bankops.banking.observability.SafeEventLogger"},
            "event_type": "http_request_completed"}) + "\n", encoding="utf-8")
        original_file = source_file.read_bytes()
        calls = {"prometheus": 0, "jaeger": 0, "llm": 0}

        def metrics(request):
            if request.method != "GET":
                raise AssertionError("Evidence must be read-only")
            calls["prometheus"] += 1
            name = next(name for name, _, query in DETECTION_QUERIES if query == request.url.params["query"])
            values = {"api_request_rate": 20, "api_error_rate": 0.2, "api_latency_p95": 1.8,
                      "transfer_success_rate": 2, "transfer_failure_rate": 0.1,
                      "banking_availability": 1, "transfer_request_rate": 2.1}
            if mode in TARGET_SCENARIOS:
                values.update(api_error_rate=0.01, api_latency_p95=0.2,
                              transfer_failure_rate=0.01, transfer_request_rate=2.01)
                if mode == "elevated_transfer_failure_rate":
                    values.update(transfer_failure_rate=0.3, transfer_request_rate=2.3)
                else:
                    values["api_latency_p95"] = 1.8
            result = [] if mode == "insufficient" else [{"metric": {},
                "value": [float(request.url.params["time"]), str(values[name])]}]
            return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": result}})

        def traces(request):
            if request.method != "GET":
                raise AssertionError("Evidence must be read-only")
            calls["jaeger"] += 1
            end = datetime.fromisoformat(request.url.params["query.start_time_max"])
            start_ns = int((end-timedelta(seconds=2)).timestamp() * 1_000_000_000)
            span = {"traceId": f"{1:032x}", "spanId": f"{1:016x}", "name": "db.call",
                    "startTimeUnixNano": str(start_ns),
                    "endTimeUnixNano": str(start_ns + (1_000_000 if mode in ("contradictory", "unsupported") else 1_500_000_000)),
                    "status": {"code": 0 if mode in ("contradictory", "unsupported") else 2}}
            if mode in TARGET_SCENARIOS:
                span["name"] = "transfer.create" if mode == "elevated_transfer_failure_rate" else "http.request"
                span["status"] = {"code": 2 if mode == "elevated_transfer_failure_rate" else 0}
            return httpx.Response(200, json={"result": {"resourceSpans": [{"resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "banking-service"}}]},
                "scopeSpans": [{"spans": [span]}]}]}})

        def inference(request):
            calls["llm"] += 1
            if mode == "timeout": raise httpx.ReadTimeout("synthetic timeout")
            if mode == "rate_limited": return httpx.Response(429)
            if mode == "unavailable": return httpx.Response(503)
            if mode == "malformed": return httpx.Response(200, content=b"not-json")
            if mode == "missing": return httpx.Response(200, content=b"")
            return httpx.Response(200, json=model_response(mode))

        class CountedProvider:
            async def analyze(self, evidence, schema):
                calls["llm"] += 1
                return await provider.analyze(evidence, schema)

        chosen = CountedProvider() if provider is not None else JsonHTTPProvider(
            local, transport=httpx.MockTransport(inference))
        sources = SimpleNamespace(settings=local,
            prometheus_collector=PrometheusCollector(local, transport=httpx.MockTransport(metrics)),
            jaeger_collector=JaegerCollector(local, transport=httpx.MockTransport(traces)),
            log_collector=LogCollector(local), rca_analyzer=RCAAnalyzer(local, chosen))
        report = await run_workflow(build_workflow(sources))
        # Build a fresh catalog from the actual returned report, not model-supplied claims.
        catalog = {row.id: row for row in evidence_catalog(report)}
        rca = report.rca
        checks = [not rca.root_cause_confirmed,
                  {"causality_unconfirmed", "bounded_sample"} <= set(rca.uncertainty),
                  calls["prometheus"] == 7, calls["jaeger"] == 1, source_file.read_bytes() == original_file]
        for hypothesis in rca.hypotheses:
            checks += [hypothesis.confidence in ("low", "moderate"), bool(hypothesis.supporting_evidence),
                       all(ref in catalog and hypothesis.kind in catalog[ref].supports for ref in hypothesis.supporting_evidence)]
        if mode in TARGET_SCENARIOS:
            rule, kind = TARGET_SCENARIOS[mode]
            checks += [report.detection.triggered_rules == (rule,),
                       any(hypothesis.kind == kind and "rule." + rule in hypothesis.supporting_evidence
                           for hypothesis in rca.hypotheses)]
        if mode in ("contradictory", "unsupported"):
            checks.append(not any(row.source == "span" for row in catalog.values()))
        if mode in EXPECTED:
            checks += [rca.status == "undetermined", rca.reason == EXPECTED[mode], not rca.hypotheses]
        else:
            checks.append(rca.status == "hypotheses" or rca.reason == "no_supported_hypotheses")
        if mode == "insufficient":
            checks += [calls["llm"] == 0, report.detection.state == "insufficient_data"]
        else:
            checks.append(calls["llm"] == 1)
        return {"scenario": mode, "passed": all(checks), "incident_status": report.detection.state,
                "rca_status": rca.status, "reason": rca.reason, "hypothesis_count": len(rca.hypotheses),
                "provider_calls": calls["llm"]}


async def verification(*, live: bool = False) -> dict:
    offline = isolated_settings(llm_provider="json_http", llm_url="https://synthetic.invalid/rca")
    cases = [await verify_case(mode, offline) for mode in SCENARIOS]
    result = {"automated": {"transport": "mocked", "passed": all(case["passed"] for case in cases), "cases": cases},
              "configuration": configuration_summary(), "live": {"status": "not_requested"}}
    if not live:
        return result
    blockers = []
    if os.getenv("BANKOPS_AGENT_LIVE_RCA_VERIFY") != "1": blockers.append("explicit_environment_opt_in_required")
    if result["configuration"]["provider"] not in ("json_http", "openai_compatible"): blockers.append("enabled_provider_required")
    if not result["configuration"]["url_present"]: blockers.append("gateway_url_required")
    if blockers:
        result["live"] = {"status": "blocked", "blockers": blockers}
        return result
    try:
        settings = configured_live_settings()
    except Exception:
        result["live"] = {"status": "blocked", "blockers": ["invalid_llm_configuration"]}
        return result
    provider = OpenAICompatibleProvider(settings) if settings.llm_provider == "openai_compatible" else JsonHTTPProvider(settings)
    live_cases = [await verify_case(mode, settings, provider) for mode in ("incident", "contradictory", "insufficient")]
    result["live"] = {"transport": "configured_gateway", "status": "passed" if all(case["passed"] for case in live_cases) else "failed",
                      "cases": live_cases}
    return result


def main(argv=None) -> int:
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, "Invalid verification arguments; use --help\n")
    parser = SafeParser(description="Verify RCA with synthetic evidence; no banking service access")
    parser.add_argument("--live", action="store_true", help="Opt in to at most two real inference requests")
    args = parser.parse_args(argv)
    # This standalone CLI prints only its allowlisted summary, never dependency diagnostics.
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        result = asyncio.run(verification(live=args.live))
        code = 0 if result["automated"]["passed"] and result["live"]["status"] in ("passed", "not_requested") else 2
    except (Exception, KeyboardInterrupt):
        result, code = {"status": "verification_failed", "reason": "safe_execution_failure"}, 2
    finally:
        logging.disable(previous_logging)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
