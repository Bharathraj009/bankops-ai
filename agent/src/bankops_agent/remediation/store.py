"""Independent SQLite approval store with atomic decisions and append-only audit."""

from contextlib import contextmanager
from datetime import UTC, datetime
import json
import hashlib
from pathlib import Path
import sqlite3
from uuid import uuid4

from bankops_agent.remediation.models import AuditEvent, Proposal

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
 id TEXT PRIMARY KEY, action TEXT NOT NULL CHECK(action IN ('restart_banking_service','scale_banking_service','investigate_dependency')),
 evidence TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED')),
 created_at TEXT NOT NULL, created_by TEXT NOT NULL CHECK(created_by='proposal_service'),
 decided_at TEXT, decided_by TEXT, reason TEXT,
 CHECK((status='PENDING' AND decided_at IS NULL AND decided_by IS NULL AND reason IS NULL) OR
 (status IN ('APPROVED','REJECTED') AND decided_at IS NOT NULL AND decided_at>=created_at
 AND decided_by IS NOT NULL AND decided_by='human_reviewer' AND reason IS NOT NULL
 AND reason IN ('reviewed_evidence','insufficient_evidence','risk_unacceptable','alternative_required')))
);
CREATE TABLE IF NOT EXISTS approval_audit (
 sequence INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id),
 event TEXT NOT NULL CHECK(event IN ('CREATED','APPROVED','REJECTED')),
 actor TEXT NOT NULL CHECK(actor IN ('proposal_service','human_reviewer')), timestamp TEXT NOT NULL,
 UNIQUE(proposal_id,event)
);
CREATE TRIGGER IF NOT EXISTS pending_insert BEFORE INSERT ON proposals WHEN NEW.status!='PENDING'
 BEGIN SELECT RAISE(ABORT,'Pending required'); END;
CREATE TRIGGER IF NOT EXISTS guarded_update BEFORE UPDATE ON proposals
 WHEN OLD.status!='PENDING' OR NEW.status NOT IN ('APPROVED','REJECTED') OR
 NEW.id IS NOT OLD.id OR NEW.action IS NOT OLD.action OR NEW.evidence IS NOT OLD.evidence OR
 NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by
 BEGIN SELECT RAISE(ABORT,'Invalid transition'); END;
CREATE TRIGGER IF NOT EXISTS no_proposal_delete BEFORE DELETE ON proposals
 BEGIN SELECT RAISE(ABORT,'Immutable proposal'); END;
CREATE TRIGGER IF NOT EXISTS audit_create AFTER INSERT ON proposals
 BEGIN INSERT INTO approval_audit(proposal_id,event,actor,timestamp) VALUES(NEW.id,'CREATED',NEW.created_by,NEW.created_at); END;
CREATE TRIGGER IF NOT EXISTS audit_decision AFTER UPDATE ON proposals
 BEGIN INSERT INTO approval_audit(proposal_id,event,actor,timestamp) VALUES(NEW.id,NEW.status,NEW.decided_by,NEW.decided_at); END;
CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON approval_audit
 BEGIN SELECT RAISE(ABORT,'Immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON approval_audit
 BEGIN SELECT RAISE(ABORT,'Immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS guarded_audit_insert BEFORE INSERT ON approval_audit WHEN NOT EXISTS (
 SELECT 1 FROM proposals WHERE id=NEW.proposal_id AND
 ((NEW.event='CREATED' AND NEW.actor=created_by AND NEW.timestamp=created_at) OR
 (NEW.event=status AND NEW.actor=decided_by AND NEW.timestamp=decided_at)))
 BEGIN SELECT RAISE(ABORT,'Invalid audit event'); END;
"""


class NotFound(Exception): pass
class AlreadyDecided(Exception): pass

SAFE_ACTIONS = ("CHECK_SERVICE_HEALTH", "REFRESH_INCIDENT_EVIDENCE")


def safe_schema():
    # Additive companion tables preserve legacy proposal checks, rows and audit history.
    sql = SCHEMA.replace("proposals", "read_only_proposals").replace("approval_audit", "read_only_audit")
    sql = sql.replace("'restart_banking_service','scale_banking_service','investigate_dependency'",
                      "'CHECK_SERVICE_HEALTH','REFRESH_INCIDENT_EVIDENCE'")
    import re
    return re.sub(r"(CREATE TRIGGER IF NOT EXISTS )(\w+)", r"\1safe_\2", sql)


def approval_fingerprint(proposal):
    return hashlib.sha256(json.dumps({"proposal": proposal.model_dump(mode="json"),
        "parameters": {"service": "banking-service"}}, sort_keys=True).encode()).hexdigest()


class ApprovalStore:
    def __init__(self, path):
        self.path = path
        # Provision a dedicated private directory; never connect to banking storage.
        parent = Path(path).parent
        if not parent.is_dir():
            raise OSError("Approval storage directory unavailable")
        for part in (Path(path), *Path(path).parents):
            if part.is_symlink() or (part.exists() and getattr(part.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400):
                raise OSError("Unsafe approval storage")
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            connection.executescript(safe_schema())
            from bankops_agent.remediation.execution_store import EXECUTION_SCHEMA
            connection.executescript(EXECUTION_SCHEMA)
            from bankops_agent.remediation.verification import SCHEMA as VERIFICATION_SCHEMA
            connection.executescript(VERIFICATION_SCHEMA)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def _read(self, connection, identifier):
        row = connection.execute("SELECT * FROM proposals WHERE id=?", (str(identifier),)).fetchone()
        audit_table = "approval_audit"
        if row is None:
            row = connection.execute("SELECT * FROM read_only_proposals WHERE id=?", (str(identifier),)).fetchone()
            audit_table = "read_only_audit"
        if row is None: raise NotFound()
        audit = connection.execute(f"SELECT * FROM {audit_table} WHERE proposal_id=? ORDER BY sequence", (str(identifier),)).fetchall()
        return Proposal(proposal_id=row['id'], action=row['action'], evidence_references=json.loads(row['evidence']),
            status=row['status'], created_at=row['created_at'], created_by=row['created_by'],
            decided_at=row['decided_at'], decided_by=row['decided_by'], decision_reason=row['reason'],
            audit=tuple(AuditEvent(event=item['event'], actor=item['actor'], timestamp=item['timestamp']) for item in audit))

    def read(self, identifier):
        with self.connection() as connection:
            # One snapshot prevents status/audit mismatches under concurrent decisions.
            connection.execute("BEGIN")
            return self._read(connection, identifier)

    def create(self, proposal):
        identifier, now = str(uuid4()), datetime.now(UTC).isoformat()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                table = "read_only_proposals" if proposal.action in SAFE_ACTIONS else "proposals"
                connection.execute(f"INSERT INTO {table}(id,action,evidence,status,created_at,created_by) VALUES(?,?,?,'PENDING',?,'proposal_service')",
                    (identifier, proposal.action, json.dumps(proposal.evidence_references), now))
                result = self._read(connection, identifier)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def decide(self, identifier, status, reason):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._read(connection, identifier)
                if current.status != 'PENDING': raise AlreadyDecided()
                table = "read_only_proposals" if current.action in SAFE_ACTIONS else "proposals"
                connection.execute(f"UPDATE {table} SET status=?,decided_at=?,decided_by='human_reviewer',reason=? WHERE id=? AND status='PENDING'",
                    (status, datetime.now(UTC).isoformat(), reason, str(identifier)))
                result = self._read(connection, identifier)
                if result.action in SAFE_ACTIONS and status == "APPROVED":
                    connection.execute("INSERT INTO approval_bindings(proposal_id,fingerprint) VALUES(?,?)",
                                       (str(identifier), approval_fingerprint(result)))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise
