from fastapi import APIRouter, HTTPException, Request

from bankops_agent.detection.rules import DetectionResult
from bankops_agent.investigation import InvestigationReport, investigate, collect_detection

router = APIRouter()


@router.get("/incidents/investigate", response_model=InvestigationReport)
async def investigate_incident(request: Request) -> InvestigationReport:
    if request.query_params:
        raise HTTPException(status_code=400, detail="Query parameters are not supported")
    return await investigate(request.app.state)


@router.get("/incidents/detect", response_model=DetectionResult)
async def detect_incidents(request: Request) -> DetectionResult:
    return await collect_detection(request.app.state)
