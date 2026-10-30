from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["http_error_degradation", "latency_degradation", "transfer_failure_degradation",
               "service_unavailability", "database_call_degradation", "reconciliation_evidence_gap",
               "reconciliation_integrity_failure", "reconciliation_workflow_failure"]


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,47}$")
    title: str = Field(min_length=3, max_length=120)
    category: Literal["historical_incident", "troubleshooting"]
    data_classification: Literal["synthetic"]
    supports: tuple[Kind, ...] = Field(min_length=1, max_length=5)
    content: str = Field(min_length=20, max_length=12000)


class RetrievedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    reviewed: bool = False
    document_id: str
    title: str
    source: str
    category: Literal["historical_incident", "troubleshooting"]
    content: str
    sha256: str
    supports: tuple[Kind, ...]
    score: float


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["matched", "no_match", "unavailable"]
    method: Literal["bm25"] = "bm25"
    sources: tuple[RetrievedSource, ...] = ()
