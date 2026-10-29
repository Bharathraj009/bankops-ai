"""Bounded proposal and decision types. No scripts, commands, or personal data."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProposalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Action(StrEnum):
    RESTART_BANKING_SERVICE = "restart_banking_service"
    SCALE_BANKING_SERVICE = "scale_banking_service"
    INVESTIGATE_DEPENDENCY = "investigate_dependency"
    CHECK_SERVICE_HEALTH = "CHECK_SERVICE_HEALTH"
    REFRESH_INCIDENT_EVIDENCE = "REFRESH_INCIDENT_EVIDENCE"


class SafeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposalCreate(SafeModel):
    action: Action
    evidence_references: tuple[Literal["rule.banking_unavailable", "rule.high_http_error_rate",
        "rule.elevated_p95_latency", "rule.high_transfer_failure_rate"], ...] = Field(min_length=1, max_length=4)


class ApprovalDecision(SafeModel):
    reason: Literal["reviewed_evidence", "insufficient_evidence", "risk_unacceptable", "alternative_required"]


class AuditEvent(SafeModel):
    event: Literal["CREATED", "APPROVED", "REJECTED"]
    actor: Literal["proposal_service", "human_reviewer"]
    timestamp: datetime


class Proposal(SafeModel):
    proposal_id: UUID
    action: Action
    evidence_references: tuple[str, ...]
    status: ProposalState
    created_at: datetime
    created_by: Literal["proposal_service"]
    decided_at: datetime | None
    decided_by: Literal["human_reviewer"] | None
    decision_reason: str | None
    audit: tuple[AuditEvent, ...]


class ExecutionParameters(SafeModel):
    service: Literal["banking-service"]


class ExecutionRequest(SafeModel):
    action: Literal["CHECK_SERVICE_HEALTH", "REFRESH_INCIDENT_EVIDENCE"]
    parameters: ExecutionParameters


class ExecutionAudit(SafeModel):
    event: Literal["RUNNING", "SUCCEEDED", "FAILED"]
    timestamp: datetime


class Execution(SafeModel):
    proposal_id: UUID
    action: Literal["CHECK_SERVICE_HEALTH", "REFRESH_INCIDENT_EVIDENCE"]
    parameters: ExecutionParameters
    status: Literal["RUNNING", "SUCCEEDED", "FAILED"]
    started_at: datetime
    completed_at: datetime | None
    outcome: Literal["service_up", "service_down", "evidence_refreshed", "evidence_partial",
                     "source_unavailable", "timeout", "cancelled", "internal_failure"] | None
    audit: tuple[ExecutionAudit, ...]
