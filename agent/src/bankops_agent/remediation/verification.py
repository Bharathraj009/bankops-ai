"""Recorded-outcome verification. Never dispatches an action or contacts a source."""

from datetime import UTC, datetime
import hashlib
import hmac

from typing import Literal
from bankops_agent.remediation.models import SafeModel
from bankops_agent.remediation.execution_store import ExecutionStore
from bankops_agent.remediation.store import approval_fingerprint
from uuid import UUID


class VerificationRequest(SafeModel):
    basis: Literal["recorded_execution"]


class Verification(SafeModel):
    proposal_id: UUID
    status: Literal["EXECUTION_SUCCEEDED", "EXECUTION_FAILED", "VERIFICATION_INCONCLUSIVE"]
    reason: Literal["recorded_success", "recorded_failure", "execution_incomplete", "inconsistent_record"]
    verified_at: datetime
    execution_sha256: str
    incident_resolution: Literal["NOT_DETERMINED"] = "NOT_DETERMINED"
    basis: Literal["recorded_execution"] = "recorded_execution"
    verified_by: Literal["human_reviewer"] = "human_reviewer"


SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_verifications (
 proposal_id TEXT PRIMARY KEY REFERENCES remediation_executions(proposal_id),
 record TEXT NOT NULL CHECK(json_valid(record)));
CREATE TABLE IF NOT EXISTS verification_audit (
 proposal_id TEXT PRIMARY KEY REFERENCES execution_verifications(proposal_id),
 event TEXT NOT NULL CHECK(event='VERIFIED'), timestamp TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS verification_no_update BEFORE UPDATE ON execution_verifications
 BEGIN SELECT RAISE(ABORT,'Immutable verification'); END;
CREATE TRIGGER IF NOT EXISTS verification_no_delete BEFORE DELETE ON execution_verifications
 BEGIN SELECT RAISE(ABORT,'Immutable verification'); END;
CREATE TRIGGER IF NOT EXISTS verification_audit_insert AFTER INSERT ON execution_verifications
 BEGIN INSERT INTO verification_audit VALUES(NEW.proposal_id,'VERIFIED',json_extract(NEW.record,'$.verified_at')); END;
CREATE TRIGGER IF NOT EXISTS verification_audit_guard BEFORE INSERT ON verification_audit WHEN NOT EXISTS (
 SELECT 1 FROM execution_verifications WHERE proposal_id=NEW.proposal_id AND json_extract(record,'$.verified_at')=NEW.timestamp)
 BEGIN SELECT RAISE(ABORT,'Invalid verification audit'); END;
CREATE TRIGGER IF NOT EXISTS verification_audit_no_update BEFORE UPDATE ON verification_audit
 BEGIN SELECT RAISE(ABORT,'Immutable verification audit'); END;
CREATE TRIGGER IF NOT EXISTS verification_audit_no_delete BEFORE DELETE ON verification_audit
 BEGIN SELECT RAISE(ABORT,'Immutable verification audit'); END;
"""


class AlreadyVerified(Exception): pass


def assess(execution, consistent):
    if not consistent:
        return "VERIFICATION_INCONCLUSIVE", "inconsistent_record"
    if execution.status == "RUNNING":
        return "VERIFICATION_INCONCLUSIVE", "execution_incomplete"
    success = {"CHECK_SERVICE_HEALTH": {"service_up", "service_down"},
               "REFRESH_INCIDENT_EVIDENCE": {"evidence_refreshed", "evidence_partial"}}
    if execution.status == "SUCCEEDED" and execution.outcome in success[execution.action]:
        return "EXECUTION_SUCCEEDED", "recorded_success"
    if execution.status == "FAILED" and execution.outcome in {"source_unavailable", "timeout", "cancelled", "internal_failure"}:
        return "EXECUTION_FAILED", "recorded_failure"
    return "VERIFICATION_INCONCLUSIVE", "inconsistent_record"


class VerificationStore:
    def __init__(self, approvals):
        self.approvals = approvals

    def read(self, identifier):
        from bankops_agent.remediation.store import NotFound
        with self.approvals.connection() as connection:
            row = connection.execute("SELECT record FROM execution_verifications WHERE proposal_id=?", (str(identifier),)).fetchone()
            if row is None: raise NotFound()
            return Verification.model_validate_json(row["record"])

    def create(self, identifier):
        # One snapshot and atomic record/audit commit; no in-flight claim to recover.
        with self.approvals.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if connection.execute("SELECT 1 FROM execution_verifications WHERE proposal_id=?", (str(identifier),)).fetchone():
                    raise AlreadyVerified()
                execution = ExecutionStore(self.approvals)._read(connection, identifier)
                proposal = self.approvals._read(connection, identifier)
                seal = connection.execute("SELECT e.fingerprint AS execution,b.fingerprint AS binding FROM remediation_executions e JOIN approval_bindings b USING(proposal_id) WHERE proposal_id=?", (str(identifier),)).fetchone()
                expected = approval_fingerprint(proposal)
                consistent = (proposal.status == "APPROVED" and proposal.decided_by == "human_reviewer"
                    and proposal.action == execution.action and seal is not None
                    and hmac.compare_digest(seal["binding"], expected)
                    and hmac.compare_digest(seal["execution"], expected)
                    and [a.event for a in proposal.audit] == ["CREATED", "APPROVED"]
                    and proposal.audit[-1].timestamp == proposal.decided_at
                    and proposal.audit[-1].actor == "human_reviewer"
                    and proposal.decided_at is not None and proposal.decided_at <= execution.started_at
                    and [a.event for a in execution.audit] == (["RUNNING"] if execution.status == "RUNNING" else ["RUNNING", execution.status])
                    and execution.audit[0].timestamp == execution.started_at
                    and (execution.status == "RUNNING" or (execution.audit[-1].timestamp == execution.completed_at
                         and execution.completed_at >= execution.started_at)))
                status, reason = assess(execution, consistent)
                result = Verification(proposal_id=identifier, status=status, reason=reason,
                    verified_at=datetime.now(UTC), execution_sha256=hashlib.sha256(execution.model_dump_json().encode()).hexdigest())
                connection.execute("INSERT INTO execution_verifications VALUES(?,?)", (str(identifier), result.model_dump_json()))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise
