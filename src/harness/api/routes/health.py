"""Health endpoint as defined in docs/spec/03_API_CONTRACTS.md."""

from fastapi import APIRouter
from pydantic import BaseModel

import harness

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=harness.__version__)
