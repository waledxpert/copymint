"""Liveness endpoints that reveal no secrets or dependency details."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.domain.release import RELEASE_EXECUTION_CEILING

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    execution_ceiling: Literal["paper"]


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(version=__version__, execution_ceiling=RELEASE_EXECUTION_CEILING.value)


@router.get("/health/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    # Dependency-specific readiness probes are added with their adapters.
    return HealthResponse(version=__version__, execution_ceiling=RELEASE_EXECUTION_CEILING.value)
