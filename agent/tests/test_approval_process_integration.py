"""Real loopback HTTP, real service process restarts, temporary storage and test roles."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time

import httpx2 as httpx

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from fastapi.testclient import TestClient


@contextmanager
def service(root, proposer, reviewer, *, remediation=None):
    ready = root / "port.json"
    if ready.exists(): ready.unlink()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("BANKOPS_AGENT_")}
    environment.update(APPROVAL_TEST_ROOT=str(root),
        APPROVAL_TEST_PROPOSER_HASH=hashlib.sha256(proposer.encode()).hexdigest(),
        APPROVAL_TEST_REVIEWER_HASH=hashlib.sha256(reviewer.encode()).hexdigest())
    if remediation is not None:
        environment.update(APPROVAL_TEST_REMEDIATION="1", APPROVAL_TEST_EVIDENCE_URL=remediation)
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("approval_verification_server.py"))],
        env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(trust_env=False, timeout=5) as client:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert process.poll() is None, "Isolated approval service exited before readiness"
                if ready.exists():
                    url = "http://127.0.0.1:" + str(json.loads(ready.read_text())["port"])
                    try:
                        if client.get(url + "/health").status_code == 200: break
                    except httpx.HTTPError: pass
                time.sleep(0.05)
            else: raise AssertionError("Isolated approval service did not become ready")
            yield client, url
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_full_approval_workflow_across_real_process_restarts(tmp_path):
    proposer, reviewer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    proposer_auth, reviewer_auth = {"Authorization": "Bearer " + proposer}, {"Authorization": "Bearer " + reviewer}
    body = {"action": "restart_banking_service", "evidence_references": ["rule.banking_unavailable"]}
    decision = {"reason": "reviewed_evidence"}
    observed = {}
    with service(tmp_path, proposer, reviewer) as (client, url):
        base = url + "/remediation/proposals"
        observed["unauthenticated_create"] = client.post(base, json=body).status_code
        observed["invalid_credential"] = client.post(base, json=body, headers={"Authorization": "Bearer " + secrets.token_urlsafe(32)}).status_code
        observed["reviewer_cannot_propose"] = client.post(base, json=body, headers=reviewer_auth).status_code
        created = client.post(base, json=body, headers=proposer_auth)
        observed["create"] = created.status_code
        pending = created.json()
        assert pending["status"] == "PENDING" and len(pending["audit"]) == 1
        path = base + "/" + pending["proposal_id"]
        observed["proposer_cannot_approve"] = client.post(path + "/approve", json=decision, headers=proposer_auth).status_code
        observed["unauthenticated_decision"] = client.post(path + "/approve", json=decision).status_code
        observed["review"] = client.get(path, headers=reviewer_auth).status_code
        approved_response = client.post(path + "/approve", json=decision, headers=reviewer_auth)
        observed["approve"] = approved_response.status_code
        approved = approved_response.json()
        observed["duplicate"] = client.post(path + "/approve", json=decision, headers=reviewer_auth).status_code
        observed["conflicting"] = client.post(path + "/reject", json=decision, headers=reviewer_auth).status_code
        second = client.post(base, json=body, headers=proposer_auth).json()
        second_path = base + "/" + second["proposal_id"]
        rejected_response = client.post(second_path + "/reject", json={"reason": "risk_unacceptable"}, headers=reviewer_auth)
        observed["reject"] = rejected_response.status_code
        rejected = rejected_response.json()
        race = client.post(base, json=body, headers=proposer_auth).json()
        race_path = base + "/" + race["proposal_id"]
        def choose(action):
            return client.post(race_path + "/" + action, json=decision, headers=reviewer_auth).status_code
        with ThreadPoolExecutor(max_workers=2) as workers:
            observed["concurrent"] = sorted(workers.map(choose, ("approve", "reject")))
        race_final = client.get(race_path, headers=reviewer_auth).json()
    # The first OS process is gone; the next process reopens the exact same SQLite file.
    with service(tmp_path, proposer, reviewer) as (client, url):
        base = url + "/remediation/proposals/"
        for original in (approved, rejected, race_final):
            response = client.get(base + original["proposal_id"], headers=reviewer_auth)
            assert response.status_code == 200 and response.json() == original
            assert original["status"] in ("APPROVED", "REJECTED")
            assert [event["event"] for event in original["audit"]] == ["CREATED", original["status"]]
            assert original["audit"][0]["timestamp"] == original["created_at"]
            assert original["audit"][1]["timestamp"] == original["decided_at"]
            assert datetime.fromisoformat(original["decided_at"]) >= datetime.fromisoformat(original["created_at"])
            assert original["decided_by"] == "human_reviewer"
        observed["restart_persistence"] = True
    with sqlite3.connect(tmp_path / "approvals.sqlite3") as database:
        for statement in ("UPDATE approval_audit SET actor='human_reviewer'", "DELETE FROM approval_audit"):
            try: database.execute(statement)
            except sqlite3.IntegrityError: pass
            else: raise AssertionError("Audit mutation was allowed")
        assert database.execute("SELECT count(*) FROM proposals").fetchone()[0] == 3
        assert database.execute("SELECT count(*) FROM approval_audit").fetchone()[0] == 6
        observed["audit_records"] = 6
    assert not (tmp_path / "forbidden-attempt.log").exists()
    with TestClient(create_app(Settings(environment="production"))) as disabled:
        assert disabled.post("/remediation/proposals", json=body).status_code == 503
    assert observed == {"unauthenticated_create": 401, "invalid_credential": 401, "reviewer_cannot_propose": 403,
        "create": 201, "proposer_cannot_approve": 403, "unauthenticated_decision": 401, "review": 200,
        "approve": 200, "duplicate": 409, "conflicting": 409, "reject": 200, "concurrent": [200, 409],
        "restart_persistence": True, "audit_records": 6}
    print("APPROVAL_PROCESS_VERIFICATION=" + json.dumps(observed, sort_keys=True))
