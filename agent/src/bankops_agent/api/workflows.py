from fastapi import APIRouter, HTTPException, Request

from bankops_agent.workflow import WorkflowReport, run_workflow

router = APIRouter()


@router.post("/workflows/investigate", response_model=WorkflowReport)
async def investigate_workflow(request: Request) -> WorkflowReport:
    if request.query_params:
        raise HTTPException(status_code=400, detail="Query parameters are not supported")
    async for chunk in request.stream():
        if chunk:
            raise HTTPException(status_code=400, detail="Request body is not supported")
    try:
        return await run_workflow(request.app.state.investigation_workflow)
    except Exception:
        raise HTTPException(status_code=503, detail="Investigation workflow unavailable") from None
