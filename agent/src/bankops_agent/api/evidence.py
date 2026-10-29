from fastapi import APIRouter, Request

from bankops_agent.evidence.prometheus import PrometheusEvidence

router = APIRouter()


@router.get("/evidence/prometheus", response_model=PrometheusEvidence)
async def prometheus_evidence(request: Request) -> PrometheusEvidence:
    return await request.app.state.prometheus_collector.collect()
