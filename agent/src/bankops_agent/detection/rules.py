"""Pure deterministic rules. Missing observations never constitute evidence of health."""

from datetime import datetime
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict

from bankops_agent.config import Settings
from bankops_agent.evidence.prometheus import PrometheusEvidence
from bankops_agent.evidence.airflow import AirflowEvidence

State = Literal["healthy", "incident", "insufficient_data"]
RuleId = Literal["banking_unavailable", "high_http_error_rate", "elevated_p95_latency", "high_transfer_failure_rate",
                 "reconciliation_financial_violations", "reconciliation_task_failure", "reconciliation_insufficient_data"]


class RuleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_id: RuleId
    state: State
    reason: Literal["service_up", "service_down", "threshold_reached", "below_threshold", "low_traffic", "missing_or_invalid_evidence", "reconciliation_failed", "reconciliation_passed"]
    observed_value: float | None = None
    threshold: float | None = None
    observed_traffic: float | None = None
    minimum_traffic: float | None = None


class DetectionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: State
    detected_at: datetime
    triggered_rules: tuple[RuleId, ...]
    rules: tuple[RuleResult, ...]
    evidence: PrometheusEvidence
    airflow: AirflowEvidence | None = None


def with_airflow(decision: DetectionResult, evidence: AirflowEvidence) -> DetectionResult:
    if evidence.status == 'disabled': return decision
    outcomes = {run.outcome for run in evidence.runs if run.state == 'failed'}
    complete_pass = evidence.status == 'ok' and bool(evidence.runs) and all(run.outcome == 'pass' for run in evidence.runs)
    rules = tuple(RuleResult(rule_id='reconciliation_' + outcome,
        state='incident' if outcome in outcomes else 'healthy' if complete_pass else 'insufficient_data',
        reason='reconciliation_failed' if outcome in outcomes else 'reconciliation_passed' if complete_pass else 'missing_or_invalid_evidence')
        for outcome in ('financial_violations','task_failure','insufficient_data'))
    triggered = (*decision.triggered_rules, *(r.rule_id for r in rules if r.state == 'incident'))
    state = 'incident' if triggered else 'healthy' if decision.state == 'healthy' and complete_pass else 'insufficient_data'
    return decision.model_copy(update={'state':state,'rules':(*decision.rules,*rules),'triggered_rules':triggered,'airflow':evidence})


def detect(evidence: PrometheusEvidence, settings: Settings, *, detected_at: datetime) -> DetectionResult:
    """Identical evidence, settings and decision time produce identical output; no I/O or state."""
    maximum_age = settings.incident_max_evidence_age_seconds

    def fresh(timestamp):
        if timestamp is None or timestamp.tzinfo is None or detected_at.tzinfo is None:
            return False
        return -1 <= (detected_at - timestamp).total_seconds() <= maximum_age

    snapshot_fresh = fresh(evidence.evaluated_at) and fresh(evidence.collected_at)
    if snapshot_fresh:
        snapshot_fresh = evidence.collected_at >= evidence.evaluated_at

    def value(name, unit):
        matches = [metric for metric in evidence.metrics if metric.name == name]
        if not snapshot_fresh or len(matches) != 1:
            return None
        metric = matches[0]
        number = metric.value
        if metric.unit != unit or metric.status != "ok" or number is None or not math.isfinite(number) or number < 0 or not fresh(metric.sampled_at):
            return None
        if name == "banking_availability" and number not in (0, 1):
            return None
        if name == "api_error_rate" and number > 1:
            return None
        return number

    availability = value("banking_availability", "ratio")
    rules = [RuleResult(rule_id="banking_unavailable", observed_value=availability,
        state="insufficient_data" if availability is None else "incident" if availability == 0 else "healthy",
        reason="missing_or_invalid_evidence" if availability is None else "service_down" if availability == 0 else "service_up")]

    definitions = (
        ("high_http_error_rate", "api_error_rate", "ratio", settings.incident_http_error_ratio,
         "api_request_rate", settings.incident_min_api_request_rate),
        ("elevated_p95_latency", "api_latency_p95", "seconds", settings.incident_p95_seconds,
         "api_request_rate", settings.incident_min_api_request_rate),
        ("high_transfer_failure_rate", "transfer_failure_rate", "requests_per_second", settings.incident_transfer_failure_rate,
         "transfer_request_rate", settings.incident_min_transfer_request_rate),
    )
    for rule_id, metric, unit, threshold, traffic_metric, minimum in definitions:
        observed, traffic = value(metric, unit), value(traffic_metric, "requests_per_second")
        if observed is None or traffic is None:
            state, reason = "insufficient_data", "missing_or_invalid_evidence"
        elif traffic < minimum:
            state, reason = "insufficient_data", "low_traffic"
        elif observed >= threshold:
            state, reason = "incident", "threshold_reached"
        else:
            state, reason = "healthy", "below_threshold"
        rules.append(RuleResult(rule_id=rule_id, state=state, reason=reason, observed_value=observed,
                                threshold=threshold, observed_traffic=traffic, minimum_traffic=minimum))

    triggered = tuple(rule.rule_id for rule in rules if rule.state == "incident")
    # Any confirmed incident wins over unknown rules. Health requires complete valid evidence,
    # including metrics not directly consumed by a rule, e.g. transfer successes.
    required = {"api_request_rate": "requests_per_second", "api_error_rate": "ratio", "api_latency_p95": "seconds",
                "transfer_success_rate": "requests_per_second", "transfer_failure_rate": "requests_per_second",
                "banking_availability": "ratio", "transfer_request_rate": "requests_per_second"}
    complete = all(value(name, unit) is not None for name, unit in required.items())
    complete = complete and {metric.name for metric in evidence.metrics} == set(required) and evidence.status == "ok"
    state = "incident" if triggered else "healthy" if complete and all(rule.state == "healthy" for rule in rules) else "insufficient_data"
    return DetectionResult(state=state, detected_at=detected_at, triggered_rules=triggered, rules=tuple(rules), evidence=evidence)
