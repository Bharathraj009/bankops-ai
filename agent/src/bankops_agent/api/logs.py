"""Read-only log evidence; callers cannot select a filesystem source."""

from fastapi import APIRouter, HTTPException, Request

from bankops_agent.evidence.logs import LogEvidence

router = APIRouter()


@router.get("/evidence/logs", response_model=LogEvidence)
async def logs(request: Request) -> LogEvidence:
    if request.query_params:
        raise HTTPException(status_code=400, detail="Query parameters are not supported")
    return await request.app.state.log_collector.collect()
