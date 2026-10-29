from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["bankops-reliability-agent"] = "bankops-reliability-agent"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Process health only; no external systems are contacted."""
    return HealthResponse()
