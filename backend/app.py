"""FastAPI application entrypoint for the crawler workflow backend."""

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from backend.api.assist_routes import router as assist_router
from backend.api.workflow_routes import router as workflow_router
from backend.core.api_response import api_response
from backend.core.app_logging import configure_logging
from backend.core.settings import get_settings


configure_logging()
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    pass


app = FastAPI(title="Scraper Flow Studio API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError):
    return api_response(
        status_code=422,
        success=False,
        error_code="request_validation_error",
        error="Request validation failed",
        meta={"detail": exc.errors()},
    )


@app.get("/")
def index():
    return {"message": "Scraper Flow Studio API - use /api/workflows/* for DSL endpoints"}


app.include_router(workflow_router)
app.include_router(assist_router)


def main(port: int | None = None):
    settings = get_settings()
    resolved_port = port or settings.backend_port
    print(f"[*] Starting Scraper Flow Studio API at http://{settings.backend_host}:{resolved_port}")
    uvicorn.run(app, host=settings.backend_host, port=resolved_port, reload=False)
