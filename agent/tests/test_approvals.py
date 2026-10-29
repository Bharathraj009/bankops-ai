from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import secrets
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.remediation.models import ProposalCreate
from bankops_agent.remediation.store import ApprovalStore, AlreadyDecided

CREATE = {"action": "restart_banking_service", "evidence_references": ["rule.banking_unavailable"]}
DECISION = {"reason": "reviewed_evidence"}


@pytest.fixture
def setup(tmp_path):
    proposer, reviewer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    settings = Settings(approval_db_path=str(tmp_path / "approvals.sqlite3"),
        approval_proposer_token_sha256=hashlib.sha256(proposer.encode()).hexdigest(),
        approval_reviewer_token_sha256=hashlib.sha256(reviewer.encode()).hexdigest())
    return settings, {"Authorization": "Bearer " + proposer}, {"Authorization": "Bearer " + reviewer}


@pytest.mark.parametrize("choice,status", [("approve", "APPROVED"), ("reject", "REJECTED")])
def test_http_lifecycle_restart_persistence_and_audit(setup, choice, status):
    settings, proposer, reviewer = setup
    with TestClient(create_app(settings)) as client:
        created = client.post("/remediation/proposals", json=CREATE, headers=proposer)
        assert created.status_code == 201
        item = created.json()
        assert item["status"] == "PENDING" and item["decided_by"] is None
        assert len(item["audit"]) == 1 and item["audit"][0]["event"] == "CREATED"
        path = "/remediation/proposals/" + item["proposal_id"]
        assert client.get(path, headers=reviewer).json() == item
        result = client.post(path + "/" + choice, json=DECISION, headers=reviewer)
        assert result.status_code == 200 and result.headers["X-Correlation-ID"]
        decided = result.json()
        assert decided["status"] == status and decided["decided_by"] == "human_reviewer"
        assert decided["decided_at"] >= decided["created_at"]
        assert [event["event"] for event in decided["audit"]] == ["CREATED", status]
        for repeated in ("approve", "reject"):
            assert client.post(path + "/" + repeated, json=DECISION, headers=reviewer).status_code == 409
        assert client.patch(path, json={"status": "PENDING"}, headers=reviewer).status_code == 405
        assert client.delete(path, headers=reviewer).status_code == 405
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path, headers=reviewer).json() == decided


def test_authentication_and_role_separation_no_ai_self_approval(setup, log_output):
    settings, proposer, reviewer = setup
    with TestClient(create_app(settings, logger=log_output[0])) as client:
        assert client.post("/remediation/proposals", json=CREATE).status_code == 401
        assert client.post("/remediation/proposals", json=CREATE, headers=reviewer).status_code == 403
        created = client.post("/remediation/proposals", json=CREATE, headers=proposer).json()
        path = "/remediation/proposals/" + created["proposal_id"]
        for endpoint in ("approve", "reject"):
            response = client.post(path + "/" + endpoint, json=DECISION, headers=proposer)
            assert response.status_code == 403
            assert client.post(path + "/" + endpoint, json=DECISION).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer " + "PRIVATE" * 10}).status_code == 401
        assert client.get(path, headers=[("Authorization", proposer["Authorization"]), ("Authorization", reviewer["Authorization"])]).status_code == 401
        assert client.get(path, headers=proposer).json()["status"] == "PENDING"
    output = log_output[1].getvalue()
    assert "PRIVATE" not in output
    assert proposer["Authorization"] not in output and reviewer["Authorization"] not in output


@pytest.mark.parametrize("extra", [{"status": "APPROVED"}, {"created_by": "human_reviewer"},
    {"command": "PRIVATE"}, {"accountId": "PRIVATE"}, {"action": "PRIVATE"},
    {"evidence_references": ["account.PRIVATE"]}, {"evidence_references": []}])
def test_request_allowlist_never_echoes_sensitive_values(setup, extra):
    settings, proposer, _ = setup
    with TestClient(create_app(settings)) as client:
        response = client.post("/remediation/proposals", json=CREATE | extra, headers=proposer)
    assert response.status_code == 400 and "PRIVATE" not in response.text


def test_invalid_decision_ids_missing_and_bounded_bodies(setup):
    settings, proposer, reviewer = setup
    with TestClient(create_app(settings)) as client:
        base = "/remediation/proposals"
        assert client.get(base + "/not-a-uuid", headers=reviewer).status_code == 400
        assert client.get(base + "/" + str(uuid4()), headers=reviewer).status_code == 404
        assert client.post(base, content=b"x" * 4097, headers=proposer).status_code == 413
        assert client.post(base, content=b'{"action":"a","action":"b"}', headers=proposer).status_code == 400
        assert client.post(base, content=b"not JSON PRIVATE", headers=proposer).status_code == 400
        identifier = client.post(base, json=CREATE, headers=proposer).json()["proposal_id"]
        for value in ({}, {"reason": "PRIVATE"}, DECISION | {"decided_by": "human_reviewer"}, DECISION | {"status": "APPROVED"}):
            result = client.post(base + "/" + identifier + "/approve", json=value, headers=reviewer)
            assert result.status_code == 400 and "PRIVATE" not in result.text
        assert client.get(base + "/" + identifier, headers=reviewer).json()["status"] == "PENDING"


def test_concurrent_conflicting_decisions_exactly_one_commits(setup):
    settings, _, _ = setup
    first, second = ApprovalStore(settings.approval_db_path), ApprovalStore(settings.approval_db_path)
    proposal = first.create(ProposalCreate(**CREATE))
    def decide(index):
        try:
            return (first if index % 2 else second).decide(proposal.proposal_id, "APPROVED" if index % 2 else "REJECTED", "reviewed_evidence").status
        except AlreadyDecided: return "conflict"
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(decide, range(8)))
    assert results.count("conflict") == 7
    final = second.read(proposal.proposal_id)
    assert final.status in ("APPROVED", "REJECTED") and len(final.audit) == 2


def test_audit_failure_rolls_back_decision(setup):
    settings, _, _ = setup
    store = ApprovalStore(settings.approval_db_path)
    proposal = store.create(ProposalCreate(**CREATE))
    with store.connection() as connection:
        connection.execute("CREATE TRIGGER injected_failure BEFORE INSERT ON approval_audit WHEN NEW.event='APPROVED' BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError): store.decide(proposal.proposal_id, "APPROVED", "reviewed_evidence")
    current = store.read(proposal.proposal_id)
    assert current.status == "PENDING" and len(current.audit) == 1 and current.decided_at is None


@pytest.mark.parametrize("statement", [
    "UPDATE proposals SET action='scale_banking_service' WHERE id=?",
    "UPDATE proposals SET status='APPROVED' WHERE id=?",
    "UPDATE proposals SET status='APPROVED',decided_at='2099',decided_by=NULL,reason=NULL WHERE id=?",
    "DELETE FROM proposals WHERE id=?",
    "UPDATE approval_audit SET actor='human_reviewer' WHERE proposal_id=?",
    "DELETE FROM approval_audit WHERE proposal_id=?",
    "INSERT INTO approval_audit(proposal_id,event,actor,timestamp) VALUES(?,'APPROVED','human_reviewer','2099')",
])
def test_database_guards(statement, setup):
    settings, _, _ = setup
    store = ApprovalStore(settings.approval_db_path)
    item = store.create(ProposalCreate(**CREATE))
    with store.connection() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement, (str(item.proposal_id),))
    assert store.read(item.proposal_id).status == "PENDING"


def test_disabled_and_storage_failure_are_safe(tmp_path, setup, monkeypatch):
    with TestClient(create_app()) as client:
        assert client.post("/remediation/proposals", json=CREATE).status_code == 503
        assert client.get("/health").status_code == 200
    settings, proposer, reviewer = setup
    app = create_app(settings)
    def fail(*args): raise sqlite3.OperationalError("PRIVATE database path")
    monkeypatch.setattr(app.app.state.approval_store, "create", fail)
    with TestClient(app) as client:
        response = client.post("/remediation/proposals", json=CREATE, headers=proposer)
        assert response.status_code == 503 and "PRIVATE" not in response.text
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize("changes", [{"approval_proposer_token_sha256": None}, {"approval_reviewer_token_sha256": "PRIVATE"},
    {"approval_db_path": "relative.sqlite3"}, {"approval_db_path": ":memory:"}, {"approval_db_path": "//host/share/a.sqlite3"}])
def test_configuration_fails_closed(setup, changes):
    settings, _, _ = setup
    values = settings.model_dump() | changes
    with pytest.raises(ValidationError): Settings(**values)


def test_same_credential_cannot_hold_both_roles(setup):
    settings, _, _ = setup
    with pytest.raises(ValidationError):
        Settings(**(settings.model_dump() | {"approval_reviewer_token_sha256": settings.approval_proposer_token_sha256}))


def test_http_race_across_app_instances(setup):
    settings, proposer, reviewer = setup
    with TestClient(create_app(settings)) as first, TestClient(create_app(settings)) as second:
        item = first.post("/remediation/proposals", json=CREATE, headers=proposer).json()
        path = "/remediation/proposals/" + item["proposal_id"]
        def decide(index):
            return (first if index == 0 else second).post(path + ("/approve" if index == 0 else "/reject"),
                json=DECISION, headers=reviewer).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, (0, 1)))
        assert sorted(results) == [200, 409]
        assert len(first.get(path, headers=reviewer).json()["audit"]) == 2


def test_approval_does_not_execute_or_call_external_services(setup, monkeypatch):
    import subprocess
    import httpx2
    def forbidden(*args, **kwargs): raise AssertionError("No execution or outbound calls allowed")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, "__init__", forbidden)
    settings, proposer, reviewer = setup
    with TestClient(create_app(settings)) as client:
        identifier = client.post("/remediation/proposals", json=CREATE, headers=proposer).json()["proposal_id"]
        assert client.post("/remediation/proposals/" + identifier + "/approve", json=DECISION, headers=reviewer).status_code == 200


def test_terminal_state_database_guard(setup):
    settings, _, _ = setup
    store = ApprovalStore(settings.approval_db_path)
    item = store.create(ProposalCreate(**CREATE))
    store.decide(item.proposal_id, "APPROVED", "reviewed_evidence")
    with store.connection() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE proposals SET status='REJECTED' WHERE id=?", (str(item.proposal_id),))
    assert store.read(item.proposal_id).status == "APPROVED"


def test_missing_directory_fails_closed_without_affecting_health(setup, tmp_path):
    settings, proposer, _ = setup
    settings = Settings(**(settings.model_dump() | {"approval_db_path": str(tmp_path / "missing" / "store.sqlite3")}))
    with TestClient(create_app(settings)) as client:
        response = client.post("/remediation/proposals", json=CREATE, headers=proposer)
        assert response.status_code == 503 and str(tmp_path) not in response.text
        assert client.get("/health").status_code == 200


def test_broken_symlink_source_rejected_before_database_creation(tmp_path, monkeypatch):
    from pathlib import Path
    target = tmp_path / "broken.sqlite3"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == target or original(path))
    with pytest.raises(OSError): ApprovalStore(str(target))
    assert not target.exists()
