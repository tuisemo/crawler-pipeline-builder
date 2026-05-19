"""FastAPI application entrypoint for the crawler workflow backend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from api.auth_routes import router as auth_router
from api.assist_routes import router as assist_router
from api.task_routes import router as task_router
from api.workflow_routes import router as workflow_router
from core.api_response import api_response
from core.app_logging import configure_logging
from core.settings import get_settings
from database import close_connection, ensure_schema
from auth.redis_client import close_redis

configure_logging()
logger = logging.getLogger(__name__)
SERVER_ROOT = Path(__file__).resolve().parents[1]

# Ensure runtime directories exist at startup
_STATIC_DIR = SERVER_ROOT / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database
    ensure_schema()
    yield
    # Shutdown: close connections
    close_connection()
    close_redis()


app = FastAPI(title="Scraper Flow Studio API", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError):
    return api_response(
        status_code=422,
        success=False,
        error_code="request_validation_error",
        error="Request validation failed",
        meta={"detail": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException):
    return api_response(
        status_code=exc.status_code,
        success=False,
        error_code="http_error",
        error=str(exc.detail) if exc.detail else "Request failed",
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return api_response(
        status_code=500,
        success=False,
        error_code="internal_error",
        error="An unexpected error occurred. Please try again later.",
    )


@app.get("/")
def index():
    return {"message": "Scraper Flow Studio API - use /api/workflows/* for DSL endpoints"}


app.include_router(workflow_router)
app.include_router(assist_router)
app.include_router(task_router)
app.include_router(auth_router)


def main(host: str | None = None, port: int | None = None):
    settings = get_settings()
    resolved_host = host if host is not None else settings.backend_host
    resolved_port = port if port is not None else settings.backend_port
    logger.info("Starting Scraper Flow Studio API at http://%s:%s", resolved_host, resolved_port)
    uvicorn.run(app, host=resolved_host, port=resolved_port, reload=False)
