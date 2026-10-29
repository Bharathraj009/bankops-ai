from fastapi import APIRouter, Request

from bankops_agent.evidence.jaeger import JaegerEvidence

router = APIRouter()


@router.get("/evidence/traces", response_model=JaegerEvidence)
async def trace_evidence(request: Request) -> JaegerEvidence:
    return await request.app.state.jaeger_collector.collect()
