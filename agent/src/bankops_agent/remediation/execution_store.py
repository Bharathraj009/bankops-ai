"""Durable at-most-once claims and atomic execution audit, separate from banking."""

from datetime import UTC, datetime
import hmac
import json

from bankops_agent.remediation.models import Execution, ExecutionAudit

EXECUTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_bindings (
 proposal_id TEXT PRIMARY KEY REFERENCES read_only_proposals(id), fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64));
CREATE TRIGGER IF NOT EXISTS binding_no_update BEFORE UPDATE ON approval_bindings BEGIN SELECT RAISE(ABORT,'Immutable binding'); END;
CREATE TRIGGER IF NOT EXISTS binding_no_delete BEFORE DELETE ON approval_bindings BEGIN SELECT RAISE(ABORT,'Immutable binding'); END;
CREATE TRIGGER IF NOT EXISTS binding_guard BEFORE INSERT ON approval_bindings WHEN NOT EXISTS (
 SELECT 1 FROM read_only_proposals WHERE id=NEW.proposal_id AND status='APPROVED' AND decided_by='human_reviewer')
 BEGIN SELECT RAISE(ABORT,'Approval required'); END;
CREATE TABLE IF NOT EXISTS remediation_executions (
 proposal_id TEXT PRIMARY KEY REFERENCES approval_bindings(proposal_id),
 action TEXT NOT NULL CHECK(action IN ('CHECK_SERVICE_HEALTH','REFRESH_INCIDENT_EVIDENCE')),
 parameters TEXT NOT NULL CHECK(parameters='{"service": "banking-service"}'),
 fingerprint TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('RUNNING','SUCCEEDED','FAILED')),
 started_at TEXT NOT NULL, completed_at TEXT, outcome TEXT,
 CHECK((status='RUNNING' AND completed_at IS NULL AND outcome IS NULL) OR
 (status IN ('SUCCEEDED','FAILED') AND completed_at IS NOT NULL AND completed_at>=started_at AND outcome IS NOT NULL
 AND outcome IN ('service_up','service_down','evidence_refreshed','evidence_partial','source_unavailable','timeout','cancelled','internal_failure'))));
CREATE TABLE IF NOT EXISTS execution_audit (
 sequence INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES remediation_executions(proposal_id),
 event TEXT NOT NULL CHECK(event IN ('RUNNING','SUCCEEDED','FAILED')), timestamp TEXT NOT NULL,
 UNIQUE(proposal_id,event));
CREATE TRIGGER IF NOT EXISTS execution_claim_guard BEFORE INSERT ON remediation_executions WHEN NEW.status!='RUNNING' OR NOT EXISTS (
 SELECT 1 FROM read_only_proposals p JOIN approval_bindings b ON p.id=b.proposal_id
 WHERE p.id=NEW.proposal_id AND p.status='APPROVED' AND p.decided_by='human_reviewer'
 AND p.action=NEW.action AND b.fingerprint=NEW.fingerprint)
 BEGIN SELECT RAISE(ABORT,'Approved binding required'); END;
CREATE TRIGGER IF NOT EXISTS execution_update_guard BEFORE UPDATE ON remediation_executions WHEN
 OLD.status!='RUNNING' OR NEW.status NOT IN ('SUCCEEDED','FAILED') OR NEW.proposal_id IS NOT OLD.proposal_id OR
 NEW.action IS NOT OLD.action OR NEW.parameters IS NOT OLD.parameters OR NEW.fingerprint IS NOT OLD.fingerprint OR NEW.started_at IS NOT OLD.started_at
 BEGIN SELECT RAISE(ABORT,'Invalid execution transition'); END;
CREATE TRIGGER IF NOT EXISTS execution_no_delete BEFORE DELETE ON remediation_executions BEGIN SELECT RAISE(ABORT,'Immutable execution'); END;
CREATE TRIGGER IF NOT EXISTS execution_start_audit AFTER INSERT ON remediation_executions
 BEGIN INSERT INTO execution_audit(proposal_id,event,timestamp) VALUES(NEW.proposal_id,'RUNNING',NEW.started_at); END;
CREATE TRIGGER IF NOT EXISTS execution_finish_audit AFTER UPDATE ON remediation_executions
 BEGIN INSERT INTO execution_audit(proposal_id,event,timestamp) VALUES(NEW.proposal_id,NEW.status,NEW.completed_at); END;
CREATE TRIGGER IF NOT EXISTS execution_audit_no_update BEFORE UPDATE ON execution_audit BEGIN SELECT RAISE(ABORT,'Immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS execution_audit_no_delete BEFORE DELETE ON execution_audit BEGIN SELECT RAISE(ABORT,'Immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS execution_audit_guard BEFORE INSERT ON execution_audit WHEN NOT EXISTS (
 SELECT 1 FROM remediation_executions WHERE proposal_id=NEW.proposal_id AND status=NEW.event
 AND NEW.timestamp=CASE WHEN status='RUNNING' THEN started_at ELSE completed_at END)
 BEGIN SELECT RAISE(ABORT,'Invalid execution audit'); END;
CREATE TRIGGER IF NOT EXISTS safe_unique_id BEFORE INSERT ON read_only_proposals WHEN EXISTS (SELECT 1 FROM proposals WHERE id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'Duplicate proposal'); END;
CREATE TRIGGER IF NOT EXISTS legacy_unique_id BEFORE INSERT ON proposals WHEN EXISTS (SELECT 1 FROM read_only_proposals WHERE id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'Duplicate proposal'); END;
"""


class NotExecutable(Exception): pass
class AlreadyExecuted(Exception): pass


class ExecutionStore:
    def __init__(self, approvals):
        self.approvals = approvals

    def _read(self, connection, identifier):
        from bankops_agent.remediation.store import NotFound
        row = connection.execute("SELECT * FROM remediation_executions WHERE proposal_id=?", (str(identifier),)).fetchone()
        if row is None: raise NotFound()
        audit = connection.execute("SELECT event,timestamp FROM execution_audit WHERE proposal_id=? ORDER BY sequence", (str(identifier),)).fetchall()
        return Execution(proposal_id=row['proposal_id'], action=row['action'], parameters=json.loads(row['parameters']),
            status=row['status'], started_at=row['started_at'], completed_at=row['completed_at'], outcome=row['outcome'],
            audit=tuple(ExecutionAudit(**dict(item)) for item in audit))

    def read(self, identifier):
        with self.approvals.connection() as connection:
            connection.execute("BEGIN")
            return self._read(connection, identifier)

    def claim(self, identifier, request):
        from bankops_agent.remediation.store import SAFE_ACTIONS, approval_fingerprint
        with self.approvals.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                proposal = self.approvals._read(connection, identifier)
                if (proposal.action not in SAFE_ACTIONS or proposal.status != 'APPROVED'
                    or proposal.decided_by != 'human_reviewer' or proposal.decided_at is None
                    or [event.event for event in proposal.audit] != ['CREATED','APPROVED']
                    or proposal.audit[-1].actor != 'human_reviewer' or proposal.audit[-1].timestamp != proposal.decided_at
                    or request.action != proposal.action or request.parameters.model_dump() != {"service": "banking-service"}):
                    raise NotExecutable()
                binding = connection.execute("SELECT fingerprint FROM approval_bindings WHERE proposal_id=?", (str(identifier),)).fetchone()
                if binding is None or not hmac.compare_digest(binding['fingerprint'], approval_fingerprint(proposal)):
                    raise NotExecutable()
                if connection.execute("SELECT 1 FROM remediation_executions WHERE proposal_id=?", (str(identifier),)).fetchone():
                    raise AlreadyExecuted()
                connection.execute("INSERT INTO remediation_executions(proposal_id,action,parameters,fingerprint,status,started_at) VALUES(?,?,?,?,'RUNNING',?)",
                    (str(identifier), proposal.action, json.dumps(request.parameters.model_dump()), binding['fingerprint'], datetime.now(UTC).isoformat()))
                result = self._read(connection, identifier)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def finish(self, identifier, status, outcome):
        with self.approvals.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute("UPDATE remediation_executions SET status=?,outcome=?,completed_at=? WHERE proposal_id=? AND status='RUNNING'",
                    (status, outcome, datetime.now(UTC).isoformat(), str(identifier)))
                if cursor.rowcount != 1: raise AlreadyExecuted()
                result = self._read(connection, identifier)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise
