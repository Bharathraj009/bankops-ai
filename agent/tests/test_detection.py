from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from bankops_agent.config import Settings
from bankops_agent.detection.rules import detect
from bankops_agent.evidence.prometheus import DETECTION_QUERIES, MetricEvidence, PrometheusEvidence

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HEALTHY = {"api_request_rate": 10, "api_error_rate": 0.01, "api_latency_p95": 0.2,
           "transfer_success_rate": 1, "transfer_failure_rate": 0.01,
           "banking_availability": 1, "transfer_request_rate": 2}


def snapshot(**overrides):
    values = HEALTHY | overrides
    return PrometheusEvidence(evaluated_at=NOW, collected_at=NOW, status="ok", metrics=tuple(
        MetricEvidence(name=name, unit=unit, status="ok" if values[name] is not None else "missing",
                       value=values[name], sampled_at=NOW if values[name] is not None else None)
        for name, unit, _ in DETECTION_QUERIES))


def evaluate(evidence=None, **settings):
    return detect(evidence if evidence is not None else snapshot(), Settings(**settings), detected_at=NOW)


def test_healthy_and_deterministic():
    evidence = snapshot()
    first, second = evaluate(evidence), evaluate(evidence)
    assert first == second
    assert first.state == "healthy" and not first.triggered_rules
    assert len(first.rules) == 4 and all(r.state == "healthy" for r in first.rules)
    assert first.evidence == evidence and first.detected_at == NOW


@pytest.mark.parametrize("metric,value,rule", [
    ("api_error_rate", 0.05, "high_http_error_rate"),
    ("api_latency_p95", 1, "elevated_p95_latency"),
    ("transfer_failure_rate", 0.05, "high_transfer_failure_rate"),
    ("banking_availability", 0, "banking_unavailable"),
])
def test_every_rule_triggers_at_inclusive_boundary(metric, value, rule):
    result = evaluate(snapshot(**{metric: value}))
    assert result.state == "incident" and result.triggered_rules == (rule,)
    assert next(r for r in result.rules if r.rule_id == rule).observed_value == value


@pytest.mark.parametrize("metric,threshold,value,rule", [
    ("api_error_rate", "incident_http_error_ratio", 0.1, "high_http_error_rate"),
    ("api_latency_p95", "incident_p95_seconds", 2, "elevated_p95_latency"),
    ("transfer_failure_rate", "incident_transfer_failure_rate", 0.2, "high_transfer_failure_rate"),
])
def test_threshold_configuration_is_used(metric, threshold, value, rule):
    evidence = snapshot(**{metric: value})
    assert rule in evaluate(evidence).triggered_rules
    assert evaluate(evidence, **{threshold: value + 0.01}).state == "healthy"


@pytest.mark.parametrize("traffic,changed,rule", [
    ("api_request_rate", {"api_error_rate": 0.9}, "high_http_error_rate"),
    ("api_request_rate", {"api_latency_p95": 10}, "elevated_p95_latency"),
    ("transfer_request_rate", {"transfer_failure_rate": 1}, "high_transfer_failure_rate"),
])
def test_low_traffic_prevents_rate_incidents(traffic, changed, rule):
    result = evaluate(snapshot(**(changed | {traffic: 0.099})))
    assert result.state == "insufficient_data" and not result.triggered_rules
    decision = next(r for r in result.rules if r.rule_id == rule)
    assert decision.state == "insufficient_data" and decision.reason == "low_traffic"


@pytest.mark.parametrize("traffic,setting,changed,rule", [
    ("api_request_rate", "incident_min_api_request_rate", {"api_error_rate": 0.9}, "high_http_error_rate"),
    ("api_request_rate", "incident_min_api_request_rate", {"api_latency_p95": 10}, "elevated_p95_latency"),
    ("transfer_request_rate", "incident_min_transfer_request_rate", {"transfer_failure_rate": 1}, "high_transfer_failure_rate"),
])
def test_minimum_traffic_is_configurable_and_inclusive(traffic, setting, changed, rule):
    evidence = snapshot(**(changed | {traffic: 0.2}))
    assert rule in evaluate(evidence, **{setting: 0.2}).triggered_rules
    assert rule not in evaluate(evidence, **{setting: 0.21}).triggered_rules


@pytest.mark.parametrize("metric", list(HEALTHY))
def test_any_missing_metric_prevents_healthy(metric):
    result = evaluate(snapshot(**{metric: None}))
    assert result.state == "insufficient_data" and not result.triggered_rules


def test_confirmed_outage_wins_over_missing_and_zero_traffic():
    result = evaluate(snapshot(banking_availability=0, api_error_rate=None, api_request_rate=0, transfer_request_rate=0))
    assert result.state == "incident" and result.triggered_rules == ("banking_unavailable",)


def test_multiple_rules_and_partial_data():
    result = evaluate(snapshot(api_error_rate=0.9, api_latency_p95=2, transfer_failure_rate=0.5, banking_availability=None))
    assert result.state == "incident"
    assert set(result.triggered_rules) == {"high_http_error_rate", "elevated_p95_latency", "high_transfer_failure_rate"}


@pytest.mark.parametrize("status", ["missing", "timeout", "unavailable", "invalid_response", "query_error"])
def test_failed_evidence_is_never_health_or_assumed_outage(status):
    evidence = snapshot().model_copy(update={"status": "unavailable", "metrics": tuple(
        m.model_copy(update={"status": status, "value": None, "sampled_at": None}) for m in snapshot().metrics)})
    result = evaluate(evidence)
    assert result.state == "insufficient_data" and not result.triggered_rules
    assert all(r.state == "insufficient_data" for r in result.rules)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1])
def test_invalid_metric_values_are_not_health(bad):
    assert evaluate(snapshot(api_error_rate=bad)).state == "insufficient_data"


@pytest.mark.parametrize("change", ["old", "future", "naive", "duplicate", "wrong_unit", "invalid_availability", "absent"])
def test_malformed_or_stale_evidence_is_insufficient(change):
    evidence = snapshot()
    if change in ("old", "future", "naive"):
        timestamp = NOW - timedelta(seconds=61) if change == "old" else NOW + timedelta(seconds=2) if change == "future" else NOW.replace(tzinfo=None)
        evidence = evidence.model_copy(update={"evaluated_at": timestamp})
    elif change == "duplicate":
        evidence = evidence.model_copy(update={"metrics": evidence.metrics + (evidence.metrics[0],)})
    elif change == "wrong_unit":
        evidence = evidence.model_copy(update={"metrics": tuple(m.model_copy(update={"unit": "seconds"}) if m.name == "transfer_success_rate" else m for m in evidence.metrics)})
    elif change == "invalid_availability":
        evidence = snapshot(banking_availability=0.5)
    elif change == "absent":
        evidence = evidence.model_copy(update={"metrics": evidence.metrics[:-1]})
    assert evaluate(evidence).state == "insufficient_data"


@pytest.mark.parametrize("setting,value", [
    ("incident_http_error_ratio", 0), ("incident_http_error_ratio", 1.1),
    ("incident_p95_seconds", -1), ("incident_transfer_failure_rate", float("inf")),
    ("incident_min_api_request_rate", 0), ("incident_min_transfer_request_rate", 0),
    ("incident_max_evidence_age_seconds", 301),
])
def test_invalid_thresholds_are_rejected(setting, value):
    with pytest.raises(ValidationError):
        Settings(**{setting: value})


def test_environment_thresholds(monkeypatch):
    monkeypatch.setenv("BANKOPS_AGENT_INCIDENT_HTTP_ERROR_RATIO", "0.2")
    assert evaluate(snapshot(api_error_rate=0.1)).state == "healthy"
