import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi.testclient import TestClient
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.remediation.engine import RemediationEngine
from bankops_agent.remediation.execution_store import ExecutionStore
from bankops_agent.remediation.models import ExecutionRequest
from test_approvals import setup
from test_investigation import state
from test_workflow import install_sources

HEALTH = "CHECK_SERVICE_HEALTH"
REFRESH = "REFRESH_INCIDENT_EVIDENCE"


@pytest.fixture
def environment(setup):
    settings, proposer, reviewer = setup
    settings = Settings(**(settings.model_dump() | {"remediation_enabled": True}))
    app = create_app(settings)
    sources = state()
    install_sources(app, sources)
    with TestClient(app) as client:
        yield settings, app, client, proposer, reviewer, sources


def request(action=HEALTH):
    return {"action": action, "parameters": {"service": "banking-service"}}


def proposal(environment, action=HEALTH, decision="approve"):
    _, _, client, proposer, reviewer, _ = environment
    result = client.post("/remediation/proposals", json={"action": action,
        "evidence_references": ["rule.banking_unavailable"]}, headers=proposer)
    assert result.status_code == 201
    path = "/remediation/proposals/" + result.json()["proposal_id"]
    if decision:
        assert client.post(path + "/" + decision, json={"reason": "reviewed_evidence"}, headers=reviewer).status_code == 200
    return path


@pytest.mark.parametrize("action,outcome", [(HEALTH, "service_up"), (REFRESH, "evidence_partial")])
def test_approved_read_only_execution_persistence_and_audit(environment, action, outcome, monkeypatch):
    settings, app, client, proposer, reviewer, sources = environment
    def no_llm(*args): raise AssertionError("RCA must not run")
    monkeypatch.setattr(app.app.state.rca_analyzer, "analyze", no_llm)
    path = proposal(environment, action)
    approved = client.get(path, headers=reviewer).json()
    response = client.post(path + "/execute", json=request(action), headers=reviewer)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "SUCCEEDED" and result["outcome"] == outcome
    assert result["parameters"] == {"service": "banking-service"}
    assert result["completed_at"] >= result["started_at"]
    assert [event["event"] for event in result["audit"]] == ["RUNNING", "SUCCEEDED"]
    assert client.get(path, headers=reviewer).json() == approved
    assert sources.prometheus_collector.calls == 1
    assert sources.jaeger_collector.calls == (1 if action == REFRESH else 0)
    assert client.post(path + "/execute", json=request(action), headers=reviewer).status_code == 409
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path + "/execution", headers=reviewer).json() == result
        assert restarted.post(path + "/execute", json=request(action), headers=reviewer).status_code == 409


@pytest.mark.parametrize("decision", [None, "reject"])
def test_pending_rejected_never_execute(environment, decision):
    _, _, client, _, reviewer, sources = environment
    path = proposal(environment, decision=decision)
    assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 409
    assert sources.prometheus_collector.calls == 0


def test_auth_disabled_unsupported_and_exact_parameters(environment):
    settings, _, client, proposer, reviewer, sources = environment
    path = proposal(environment)
    assert client.post(path + "/execute", json=request()).status_code == 401
    assert client.post(path + "/execute", json=request(), headers=proposer).status_code == 403
    assert client.post(path + "/execute", json=request(REFRESH), headers=reviewer).status_code == 409
    for value in (request() | {"url": "PRIVATE"}, {"action": "restart_banking_service", "parameters": {}},
                  {"action": HEALTH, "parameters": {"service": "https://PRIVATE"}},
                  {"action": HEALTH, "parameters": {"service": "banking-service", "command": "PRIVATE"}}):
        response = client.post(path + "/execute", json=value, headers=reviewer)
        assert response.status_code == 400 and "PRIVATE" not in response.text
    legacy = proposal(environment, "restart_banking_service")
    assert client.post(legacy + "/execute", json=request(), headers=reviewer).status_code == 409
    disabled = Settings(**(settings.model_dump() | {"remediation_enabled": False}))
    with TestClient(create_app(disabled)) as other:
        assert other.post(path + "/execute", json=request(), headers=reviewer).status_code == 503
    assert sources.prometheus_collector.calls == 0


def test_modified_proposal_rejected_by_approval_binding(environment):
    _, app, client, _, reviewer, sources = environment
    path = proposal(environment)
    with app.app.state.approval_store.connection() as connection:
        # Simulate privileged corruption; normal database metadata updates are already forbidden.
        connection.execute("DROP TRIGGER safe_guarded_update")
        connection.execute("DROP TRIGGER safe_audit_decision")
        connection.execute("UPDATE read_only_proposals SET evidence='[\"rule.high_http_error_rate\"]'")
    assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 409
    assert sources.prometheus_collector.calls == 0


def test_concurrent_execution_cross_instance_claims_once(environment):
    settings, _, client, _, reviewer, sources = environment
    path = proposal(environment)
    app2 = create_app(settings)
    install_sources(app2, sources)
    with TestClient(app2) as second:
        def execute(index):
            return (client if index % 2 else second).post(path + "/execute", json=request(), headers=reviewer).status_code
        with ThreadPoolExecutor(max_workers=6) as pool:
            codes = list(pool.map(execute, range(6)))
    assert codes.count(200) == 1 and codes.count(409) == 5
    assert sources.prometheus_collector.calls == 1
    assert len(client.get(path + "/execution", headers=reviewer).json()["audit"]) == 2


@pytest.mark.parametrize("mode,outcome", [("exception", "internal_failure"), ("missing", "source_unavailable"), ("timeout", "timeout")])
def test_failure_is_safe_terminal_and_never_retried(environment, mode, outcome):
    settings, app, client, _, reviewer, sources = environment
    path = proposal(environment)
    if mode == "exception": sources.prometheus_collector.fail = True
    elif mode == "missing":
        snapshot = sources.prometheus_collector.result
        sources.prometheus_collector.result = snapshot.model_copy(update={"status": "unavailable", "metrics": ()})
    else:
        app.app.state.settings = Settings(**(settings.model_dump() | {"remediation_timeout_seconds": 0.01}))
        async def slow(): await asyncio.sleep(1)
        sources.prometheus_collector.collect_for_detection = slow
    response = client.post(path + "/execute", json=request(), headers=reviewer)
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED" and response.json()["outcome"] == outcome
    assert "PRIVATE" not in response.text
    assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 409


@pytest.mark.parametrize("phase", ["RUNNING", "SUCCEEDED"])
def test_atomic_execution_audit_failure_fails_closed(environment, phase):
    _, app, client, _, reviewer, sources = environment
    path = proposal(environment)
    with app.app.state.approval_store.connection() as connection:
        connection.execute(f"CREATE TRIGGER inject_failure BEFORE INSERT ON execution_audit WHEN NEW.event='{phase}' BEGIN SELECT RAISE(ABORT,'test'); END")
    assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 503
    if phase == "RUNNING":
        assert sources.prometheus_collector.calls == 0
        assert client.get(path + "/execution", headers=reviewer).status_code == 404
    else:
        assert sources.prometheus_collector.calls == 1
        assert client.get(path + "/execution", headers=reviewer).json()["status"] == "RUNNING"
        assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 409


@pytest.mark.parametrize("statement", ["DELETE FROM remediation_executions", "UPDATE remediation_executions SET status='RUNNING'",
    "DELETE FROM execution_audit", "UPDATE execution_audit SET event='FAILED'", "UPDATE approval_bindings SET fingerprint='changed'",
    "DELETE FROM approval_bindings"])
def test_execution_and_binding_immutable(environment, statement):
    _, app, client, _, reviewer, _ = environment
    path = proposal(environment)
    assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 200
    with app.app.state.approval_store.connection() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement)


def test_cancellation_finishes_failed_without_releasing_claim(environment):
    _, app, _, _, _, sources = environment
    path = proposal(environment)
    async def run():
        entered = asyncio.Event()
        async def wait():
            entered.set()
            await asyncio.Event().wait()
        sources.prometheus_collector.collect_for_detection = wait
        engine = RemediationEngine(app.app.state)
        task = asyncio.create_task(engine.execute(path.rsplit('/',1)[1], ExecutionRequest(**request())))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert engine.store.read(path.rsplit('/',1)[1]).outcome == "cancelled"
    asyncio.run(run())


def test_default_disabled_and_direct_engine_denies_before_claim(environment):
    settings, app, _, _, _, sources = environment
    path = proposal(environment)
    app.app.state.settings = Settings(**(settings.model_dump() | {"remediation_enabled": False}))
    with pytest.raises(PermissionError):
        asyncio.run(RemediationEngine(app.app.state).execute(path.rsplit('/',1)[1], ExecutionRequest(**request())))
    assert sources.prometheus_collector.calls == 0
    assert Settings(environment="production").remediation_enabled is False


def test_service_down_is_successful_read_not_a_write(environment):
    _, app, client, _, reviewer, _ = environment
    sources = state(banking_availability=0)
    install_sources(app, sources)
    path = proposal(environment)
    result = client.post(path + "/execute", json=request(), headers=reviewer)
    assert result.json()["status"] == "SUCCEEDED" and result.json()["outcome"] == "service_down"


def test_handler_uses_only_fixed_read_only_prometheus_queries(environment, monkeypatch):
    import httpx2 as httpx
    import json
    import subprocess
    from bankops_agent.evidence.prometheus import DETECTION_QUERIES, PrometheusCollector
    from test_detection import HEALTHY
    _, app, client, _, reviewer, _ = environment
    observed = []
    def respond(req):
        observed.append(req)
        name = next(name for name, _, query in DETECTION_QUERIES if query == req.url.params["query"])
        return httpx.Response(200, json={"status":"success","data":{"resultType":"vector","result":[
            {"metric":{},"value":[float(req.url.params["time"]),str(HEALTHY[name])]}]}})
    app.app.state.prometheus_collector = PrometheusCollector(app.app.state.settings, transport=httpx.MockTransport(respond))
    def forbidden(*args, **kwargs): raise AssertionError("No shell allowed")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    path = proposal(environment)
    assert client.post(path + "/execute", json=request(), headers=reviewer).json()["status"] == "SUCCEEDED"
    assert len(observed) == 7 and all(req.method == "GET" and req.url.path == "/api/v1/query" and not req.content for req in observed)


def test_legacy_database_additive_upgrade_preserves_history(setup):
    from datetime import UTC, datetime
    from uuid import uuid4
    from bankops_agent.remediation.store import SCHEMA, ApprovalStore
    settings, _, _ = setup
    identifier = str(uuid4())
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(settings.approval_db_path) as connection:
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO proposals(id,action,evidence,status,created_at,created_by) VALUES(?,'restart_banking_service','[]','PENDING',?,'proposal_service')",(identifier,now))
        connection.execute("UPDATE proposals SET status='APPROVED',decided_at=?,decided_by='human_reviewer',reason='reviewed_evidence' WHERE id=?",(now,identifier))
        before = [tuple(row) for row in connection.execute("SELECT * FROM approval_audit ORDER BY sequence")]
    store = ApprovalStore(settings.approval_db_path)
    assert store.read(identifier).status == "APPROVED"
    with store.connection() as connection:
        assert [tuple(row) for row in connection.execute("SELECT * FROM approval_audit ORDER BY sequence")] == before


def test_reviewer_audit_must_match_approved_seal(environment):
    _, app, client, _, reviewer, sources = environment
    path = proposal(environment)
    with app.app.state.approval_store.connection() as connection:
        connection.execute("DROP TRIGGER safe_immutable_audit_update")
        connection.execute("UPDATE read_only_audit SET actor='proposal_service' WHERE event='APPROVED'")
    assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 409
    assert sources.prometheus_collector.calls == 0


def test_sealing_failure_rolls_back_human_approval(environment):
    _, app, client, _, reviewer, sources = environment
    path = proposal(environment, decision=None)
    with app.app.state.approval_store.connection() as connection:
        connection.execute("CREATE TRIGGER binding_failure BEFORE INSERT ON approval_bindings BEGIN SELECT RAISE(ABORT,'test'); END")
    assert client.post(path + "/approve", json={"reason":"reviewed_evidence"}, headers=reviewer).status_code == 503
    item = client.get(path, headers=reviewer).json()
    assert item["status"] == "PENDING" and len(item["audit"]) == 1
    assert client.post(path + "/execute", json=request(), headers=reviewer).status_code == 409
    assert sources.prometheus_collector.calls == 0
