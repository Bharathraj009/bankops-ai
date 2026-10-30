"""Evidence-grounded, bounded hypothesis selection; never a confirmed diagnosis."""

import asyncio
from datetime import UTC, datetime
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bankops_agent.config import Settings
from bankops_agent.investigation import InvestigationReport
from bankops_agent.rca.provider import LLMProvider, ProviderFailure
from bankops_agent.rag.models import Kind, RetrievalResult
from bankops_agent.rag.outbound import project_observations
from bankops_agent.rag.retrieval import load_index

Uncertainty = Literal["causality_unconfirmed", "bounded_sample", "incomplete_evidence", "dependencies_not_observed"]
Step = Literal["compare_metric_windows", "inspect_safe_trace_timings", "check_dependency_health",
               "review_sanitized_error_events", "collect_additional_evidence"]
RULE_KINDS = {"high_http_error_rate": "http_error_degradation", "elevated_p95_latency": "latency_degradation",
              "reconciliation_insufficient_data": "reconciliation_evidence_gap",
              "reconciliation_financial_violations": "reconciliation_integrity_failure",
              "reconciliation_task_failure": "reconciliation_workflow_failure",
              "high_transfer_failure_rate": "transfer_failure_degradation", "banking_unavailable": "service_unavailability"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class Hypothesis(StrictModel):
    kind: Kind
    supporting_evidence: tuple[str, ...] = Field(min_length=1, max_length=5)
    confidence: Literal["low", "moderate"]
    retrieved_sources: tuple[str, ...] = ()


class ModelAnalysis(StrictModel):
    hypotheses: tuple[Hypothesis, ...] = Field(max_length=3)
    uncertainty: tuple[Uncertainty, ...] = Field(min_length=1, max_length=4)
    recommended_investigation_steps: tuple[Step, ...] = Field(min_length=1, max_length=5)


class RAGHypothesis(Hypothesis):
    retrieved_sources: tuple[str, ...] = Field(min_length=1, max_length=5)


class RAGModelAnalysis(ModelAnalysis):
    hypotheses: tuple[RAGHypothesis, ...] = Field(max_length=3)


class EvidenceReference(StrictModel):
    id: str
    source: Literal["rule", "span", "log"]
    observation: Literal["threshold_reached", "service_down", "slow_or_failed_db_call", "warn_event", "error_event", "reconciliation_failed"]
    timestamp: datetime
    observed_value: float | None = None
    threshold: float | None = None
    supports: tuple[Kind, ...] = ()


class RCAResult(StrictModel):
    status: Literal["hypotheses", "undetermined"]
    root_cause_confirmed: Literal[False] = False
    analyzed_at: datetime
    reason: Literal["supported_hypotheses", "disabled", "insufficient_evidence", "no_supported_hypotheses",
                    "timeout", "unavailable", "rate_limited", "invalid_output", "input_limit",
                    "outbound_blocked", "retrieval_unavailable", "no_retrieval_match"]
    hypotheses: tuple[Hypothesis, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    retrieval: RetrievalResult | None = None
    uncertainty: tuple[Uncertainty, ...] = ("causality_unconfirmed", "bounded_sample")
    recommended_investigation_steps: tuple[Step, ...] = ("collect_additional_evidence",)


def evidence_catalog(report: InvestigationReport, *, include_reconciliation=False) -> tuple[EvidenceReference, ...]:
    rows = []
    for rule in report.detection.rules:
        if rule.rule_id.startswith("reconciliation_") and not include_reconciliation:
            continue  # Reconciliation analysis requires the reviewed RAG grounding path.
        if rule.state == "incident" and rule.rule_id in RULE_KINDS:
            rows.append(EvidenceReference(id="rule." + rule.rule_id, source="rule",
                observation="reconciliation_failed" if rule.rule_id.startswith("reconciliation_") else "service_down" if rule.rule_id == "banking_unavailable" else "threshold_reached",
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
        if event.level == "INFO":
            continue  # Native INFO outcomes are supporting context, never warning evidence.
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
        self.index = None
        if settings.rag_enabled:
            try:
                secrets = (settings.llm_api_key.get_secret_value(),) if settings.llm_api_key else ()
                self.index = load_index(settings.rag_corpus_directory, chunk_words=settings.rag_chunk_words,
                                        overlap=settings.rag_chunk_overlap, secrets=secrets)
            except (OSError, ValueError, TypeError):
                pass  # Never echo malformed documents, local paths or validation input.

    async def analyze(self, report: InvestigationReport) -> RCAResult:
        catalog = evidence_catalog(report, include_reconciliation=self.settings.rag_enabled)
        retrieval = None
        if self.settings.rag_enabled:
            if self.index is None:
                retrieval = RetrievalResult(status="unavailable")
            else:
                retrieval = self.index.retrieve({kind for row in catalog for kind in row.supports},
                                                limit=self.settings.rag_top_k)
        uncertainty = ("causality_unconfirmed", "bounded_sample")
        if report.evidence_status != "complete":
            uncertainty += ("incomplete_evidence",)
        def undetermined(reason):
            return RCAResult(status="undetermined", reason=reason, analyzed_at=datetime.now(UTC),
                             uncertainty=uncertainty, retrieval=retrieval)
        if report.detection.state != "incident":
            return undetermined("insufficient_evidence")
        if self.provider is None:
            return undetermined("disabled")
        if retrieval is not None and retrieval.status != "matched":
            return undetermined("retrieval_unavailable" if retrieval.status == "unavailable" else "no_retrieval_match")
        try:
            if not any(row.supports for row in catalog):
                return undetermined("insufficient_evidence")
            evidence = {"incident_state": report.detection.state, "evidence_status": report.evidence_status,
                        "observations": [row.model_dump(mode="json") for row in catalog]}
            if retrieval is not None:
                evidence["retrieved_sources"] = [row.model_dump(mode="json", exclude={"score"}) for row in retrieval.sources]
            if self.settings.evidence_mode == "synthetic_demo":
                # Refuse to label an operational report synthetic just because a
                # configuration flag was changed after collection.
                if report.evidence_mode != "synthetic_demo":
                    return undetermined("outbound_blocked")
                evidence.update(classification="synthetic", scenario=self.settings.synthetic_scenario,
                                observations=project_observations(catalog))
            # Count the full serialized adapter request budget, including schema/instructions.
            from bankops_agent.rca.provider import INSTRUCTIONS
            model = RAGModelAnalysis if retrieval is not None else ModelAnalysis
            schema = model.model_json_schema()
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
            analysis = model.model_validate_json(raw)
            refs = {row.id: row for row in catalog}
            kinds = set()
            for hypothesis in analysis.hypotheses:
                if hypothesis.kind in kinds or len(set(hypothesis.supporting_evidence)) != len(hypothesis.supporting_evidence):
                    return undetermined("invalid_output")
                kinds.add(hypothesis.kind)
                if any(ref not in refs or hypothesis.kind not in refs[ref].supports for ref in hypothesis.supporting_evidence):
                    return undetermined("invalid_output")
                retrieved = {row.id: row for row in retrieval.sources} if retrieval else {}
                if (len(set(hypothesis.retrieved_sources)) != len(hypothesis.retrieved_sources)
                        or any(ref not in retrieved or hypothesis.kind not in retrieved[ref].supports
                               for ref in hypothesis.retrieved_sources)):
                    return undetermined("invalid_output")
            if not analysis.hypotheses:
                return undetermined("no_supported_hypotheses")
            return RCAResult(status="hypotheses", reason="supported_hypotheses", analyzed_at=datetime.now(UTC),
                hypotheses=analysis.hypotheses, evidence=catalog,
                retrieval=retrieval,
                uncertainty=tuple(dict.fromkeys((*uncertainty, *analysis.uncertainty))),
                recommended_investigation_steps=analysis.recommended_investigation_steps)
        except (TimeoutError,):
            return undetermined("timeout")
        except ProviderFailure as error:
            return undetermined(error.reason if error.reason in ("timeout", "rate_limited", "invalid_output", "input_limit", "outbound_blocked") else "unavailable")
        except (ValueError, TypeError, RecursionError, KeyError):
            return undetermined("invalid_output")
        except Exception:
            return undetermined("unavailable")
