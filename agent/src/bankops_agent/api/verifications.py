from fastapi import APIRouter, HTTPException, Request

from bankops_agent.api.approvals import authorize, body, identifier, storage
from bankops_agent.remediation.verification import AlreadyVerified, Verification, VerificationRequest, VerificationStore

router = APIRouter(prefix="/remediation/proposals")


@router.post("/{proposal_id}/verify", response_model=Verification, status_code=201)
async def verify(proposal_id: str, request: Request):
    approvals = authorize(request, "reviewer")
    proposal_id = identifier(proposal_id)
    await body(request, VerificationRequest)
    try:
        return await storage(VerificationStore(approvals).create, proposal_id)
    except AlreadyVerified:
        raise HTTPException(409, "Execution already verified") from None


@router.get("/{proposal_id}/verification", response_model=Verification)
async def review(proposal_id: str, request: Request):
    approvals = authorize(request)
    return await storage(VerificationStore(approvals).read, identifier(proposal_id))
