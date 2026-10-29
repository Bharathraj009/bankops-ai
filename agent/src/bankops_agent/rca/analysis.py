"""Evidence-grounded, bounded hypothesis selection; never a confirmed diagnosis."""

import asyncio
from datetime import UTC, datetime
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bankops_agent.config import Settings
from bankops_agent.investigation import InvestigationReport
from bankops_agent.rca.provider import LLMProvider, ProviderFailure

Kind = Literal["http_error_degradation", "latency_degradation", "transfer_failure_degradation",
               "service_unavailability", "database_call_degradation"]
Uncertainty = Literal["causality_unconfirmed", "bounded_sample", "incomplete_evidence", "dependencies_not_observed"]
Step = Literal["compare_metric_windows", "inspect_safe_trace_timings", "check_dependency_health",
               "review_sanitized_error_events", "collect_additional_evidence"]
RULE_KINDS = {"high_http_error_rate": "http_error_degradation", "elevated_p95_latency": "latency_degradation",
              "high_transfer_failure_rate": "transfer_failure_degradation", "banking_unavailable": "service_unavailability"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class Hypothesis(StrictModel):
    kind: Kind
    supporting_evidence: tuple[str, ...] = Field(min_length=1, max_length=5)
    confidence: Literal["low", "moderate"]


class ModelAnalysis(StrictModel):
    hypotheses: tuple[Hypothesis, ...] = Field(max_length=3)
    uncertainty: tuple[Uncertainty, ...] = Field(min_length=1, max_length=4)
    recommended_investigation_steps: tuple[Step, ...] = Field(min_length=1, max_length=5)


class EvidenceReference(StrictModel):
    id: str
    source: Literal["rule", "span", "log"]
    observation: Literal["threshold_reached", "service_down", "slow_or_failed_db_call", "warn_event", "error_event"]
    timestamp: datetime
    observed_value: float | None = None
    threshold: float | None = None
    supports: tuple[Kind, ...] = ()


class RCAResult(StrictModel):
    status: Literal["hypotheses", "undetermined"]
    root_cause_confirmed: Literal[False] = False
    analyzed_at: datetime
    reason: Literal["supported_hypotheses", "disabled", "insufficient_evidence", "no_supported_hypotheses",
                    "timeout", "unavailable", "rate_limited", "invalid_output", "input_limit"]
    hypotheses: tuple[Hypothesis, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    uncertainty: tuple[Uncertainty, ...] = ("causality_unconfirmed", "bounded_sample")
    recommended_investigation_steps: tuple[Step, ...] = ("collect_additional_evidence",)


def evidence_catalog(report: InvestigationReport) -> tuple[EvidenceReference, ...]:
    rows = []
    for rule in report.detection.rules:
        if rule.state == "incident" and rule.rule_id in RULE_KINDS:
            rows.append(EvidenceReference(id="rule." + rule.rule_id, source="rule",
                observation="service_down" if rule.rule_id == "banking_unavailable" else "threshold_reached",
                timestamp=report.detection.detected_at, observed_value=rule.observed_value,
                threshold=rule.threshold, supports=(RULE_KINDS[rule.rule_id],)))
    for i, trace in enumerate(report.traces.traces):
        for j, span in enumerate(trace.spans):
            if span.name == "db.call" and (span.failed or span.slow):
                rows.append(EvidenceReference(id=f"span.{i}.{j}", source="span", observation="slow_or_failed_db_call",
                    timestamp=span.started_at, observed_value=span.duration_seconds, supports=("database_call_degradation",)))
                if sum(row.source == "span" for row in rows) >= 10:
                    break
        if sum(row.source == "span" for row in rows) >= 10:
            break
    for i, event in enumerate(report.logs.events[:10]):
        rows.append(EvidenceReference(id=f"log.{i}", source="log", timestamp=event.timestamp,
            observation="error_event" if event.level == "ERROR" else "warn_event"))
    return tuple(rows)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field")
        result[key] = value
    return result


class RCAAnalyzer:
    def __init__(self, settings: Settings, provider: LLMProvider | None = None):
        self.settings, self.provider = settings, provider

    async def analyze(self, report: InvestigationReport) -> RCAResult:
        uncertainty = ("causality_unconfirmed", "bounded_sample")
        if report.evidence_status != "complete":
            uncertainty += ("incomplete_evidence",)
        def undetermined(reason):
            return RCAResult(status="undetermined", reason=reason, analyzed_at=datetime.now(UTC), uncertainty=uncertainty)
        if report.detection.state != "incident":
            return undetermined("insufficient_evidence")
        if self.provider is None:
            return undetermined("disabled")
        try:
            catalog = evidence_catalog(report)
            if not any(row.supports for row in catalog):
                return undetermined("insufficient_evidence")
            evidence = {"incident_state": report.detection.state, "evidence_status": report.evidence_status,
                        "observations": [row.model_dump(mode="json") for row in catalog]}
            # Count the full serialized adapter request budget, including schema/instructions.
            from bankops_agent.rca.provider import INSTRUCTIONS
            schema = ModelAnalysis.model_json_schema()
            request = {"model": self.settings.llm_model, "instructions": INSTRUCTIONS, "evidence": evidence,
                       "response_schema": schema, "max_output_tokens": self.settings.llm_max_output_tokens}
            if len(json.dumps(request).encode("utf-8")) > self.settings.llm_max_input_bytes:
                return undetermined("input_limit")
            async with asyncio.timeout(self.settings.llm_timeout_seconds):
                raw = await self.provider.analyze(evidence, schema)
            if not isinstance(raw, bytes) or len(raw) > self.settings.llm_max_output_bytes:
                return undetermined("invalid_output")
            # Reject duplicate keys; JSON-mode strict validation accepts JSON arrays as tuples.
            json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
            analysis = ModelAnalysis.model_validate_json(raw)
            refs = {row.id: row for row in catalog}
            kinds = set()
            for hypothesis in analysis.hypotheses:
                if hypothesis.kind in kinds or len(set(hypothesis.supporting_evidence)) != len(hypothesis.supporting_evidence):
                    return undetermined("invalid_output")
                kinds.add(hypothesis.kind)
                if any(ref not in refs or hypothesis.kind not in refs[ref].supports for ref in hypothesis.supporting_evidence):
                    return undetermined("invalid_output")
            if not analysis.hypotheses:
                return undetermined("no_supported_hypotheses")
            return RCAResult(status="hypotheses", reason="supported_hypotheses", analyzed_at=datetime.now(UTC),
                hypotheses=analysis.hypotheses, evidence=catalog,
                uncertainty=tuple(dict.fromkeys((*uncertainty, *analysis.uncertainty))),
                recommended_investigation_steps=analysis.recommended_investigation_steps)
        except (TimeoutError,):
            return undetermined("timeout")
        except ProviderFailure as error:
            return undetermined(error.reason if error.reason in ("timeout", "rate_limited", "invalid_output", "input_limit") else "unavailable")
        except (ValueError, TypeError, RecursionError, KeyError):
            return undetermined("invalid_output")
        except Exception:
            return undetermined("unavailable")
