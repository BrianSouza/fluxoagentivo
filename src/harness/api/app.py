"""FastAPI application factory."""

from fastapi import FastAPI

import harness
from harness.api.routes.health import router as health_router

API_V1_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic Knowledge & Assessment Harness",
        version=harness.__version__,
    )
    app.include_router(health_router, prefix=API_V1_PREFIX)
    return app
