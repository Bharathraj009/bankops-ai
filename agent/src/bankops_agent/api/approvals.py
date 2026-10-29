"""Role-separated approval API. Approval records intent; it executes nothing."""

import asyncio
import hashlib
import hmac
import json
import inspect
import sqlite3
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from bankops_agent.rca.analysis import unique_object
from bankops_agent.remediation.models import ApprovalDecision, Proposal, ProposalCreate
from bankops_agent.remediation.store import AlreadyDecided, NotFound

router = APIRouter(prefix="/remediation/proposals")


def authorize(request, required=None):
    settings = request.app.state.settings
    if settings.approval_db_path is None:
        raise HTTPException(503, "Approval workflow unavailable")
    headers = request.headers.getlist("authorization")
    if len(headers) != 1 or not headers[0].startswith("Bearer "):
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    token = headers[0][7:]
    if not 32 <= len(token) <= 256 or any(not 33 <= ord(char) <= 126 for char in token):
        raise HTTPException(401, "Invalid credentials")
    digest = hashlib.sha256(token.encode()).hexdigest()
    proposer = hmac.compare_digest(digest, settings.approval_proposer_token_sha256.get_secret_value())
    reviewer = hmac.compare_digest(digest, settings.approval_reviewer_token_sha256.get_secret_value())
    if not (proposer or reviewer): raise HTTPException(401, "Invalid credentials")
    role = "proposer" if proposer else "reviewer"
    if required and role != required: raise HTTPException(403, "Permission denied")
    if request.query_params: raise HTTPException(400, "Query parameters are not supported")
    if request.app.state.approval_store is None:
        raise HTTPException(503, "Approval workflow unavailable")
    return request.app.state.approval_store


async def body(request, model):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 4096: raise HTTPException(413, "Request too large")
        data.extend(chunk)
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
        return model.model_validate(value)
    except (ValueError, TypeError, ValidationError, RecursionError):
        # Never echo request bodies, rejected values, or validation diagnostics.
        raise HTTPException(400, "Invalid approval request") from None


def identifier(value):
    try: return UUID(value)
    except ValueError: raise HTTPException(400, "Invalid proposal ID") from None


async def storage(call, *args):
    try:
        if inspect.iscoroutinefunction(call): return await call(*args)
        return await asyncio.to_thread(call, *args)
    except NotFound: raise HTTPException(404, "Proposal not found") from None
    except AlreadyDecided: raise HTTPException(409, "Proposal already decided") from None
    except (sqlite3.Error, OSError, ValidationError, ValueError):
        raise HTTPException(503, "Approval workflow unavailable") from None


@router.post("", response_model=Proposal, status_code=201)
async def create_proposal(request: Request):
    store = authorize(request, "proposer")
    proposal = await body(request, ProposalCreate)
    return await storage(store.create, proposal)


@router.get("/{proposal_id}", response_model=Proposal)
async def review_proposal(proposal_id: str, request: Request):
    store = authorize(request)
    return await storage(store.read, identifier(proposal_id))


@router.post("/{proposal_id}/approve", response_model=Proposal)
async def approve_proposal(proposal_id: str, request: Request):
    return await decision(proposal_id, request, "APPROVED")


@router.post("/{proposal_id}/reject", response_model=Proposal)
async def reject_proposal(proposal_id: str, request: Request):
    return await decision(proposal_id, request, "REJECTED")


async def decision(proposal_id, request, status):
    store = authorize(request, "reviewer")
    proposal_id = identifier(proposal_id)
    value = await body(request, ApprovalDecision)
    return await storage(store.decide, proposal_id, status, value.reason)
