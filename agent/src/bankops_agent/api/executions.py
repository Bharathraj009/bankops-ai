from fastapi import APIRouter, HTTPException, Request

from bankops_agent.api.approvals import authorize, body, identifier, storage
from bankops_agent.remediation.engine import RemediationEngine
from bankops_agent.remediation.execution_store import AlreadyExecuted, NotExecutable, ExecutionStore
from bankops_agent.remediation.models import Execution, ExecutionRequest

router = APIRouter(prefix="/remediation/proposals")


@router.post("/{proposal_id}/execute", response_model=Execution)
async def execute(proposal_id: str, request: Request):
    authorize(request, "reviewer")
    if not request.app.state.settings.remediation_enabled:
        raise HTTPException(503, "Remediation execution disabled")
    proposal_id = identifier(proposal_id)
    value = await body(request, ExecutionRequest)
    try:
        return await storage(RemediationEngine(request.app.state).execute, proposal_id, value)
    except (NotExecutable, AlreadyExecuted):
        raise HTTPException(409, "Proposal is not executable or was already executed") from None


@router.get("/{proposal_id}/execution", response_model=Execution)
async def review_execution(proposal_id: str, request: Request):
    approvals = authorize(request)
    return await storage(ExecutionStore(approvals).read, identifier(proposal_id))
