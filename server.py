"""
server.py - FastAPI entrypoint for the crawler workflow system.

Usage:
    python server.py
    uvicorn server:app --reload
"""

from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from backend.core.api_response import api_response
from backend.core.app_logging import configure_logging
from backend.async_bridge import run_blocking
from backend.browser_session import page_session_mgr, stop_browser
from backend.core.settings import get_settings
from backend.assist_routes import router as assist_router
from backend.workflow_routes import router as workflow_router

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await run_blocking(lambda: (page_session_mgr.close_all(), stop_browser()))

app = FastAPI(title="Crawler Workflow API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    return {"message": "Crawler Workflow API - use /api/workflows/* for DSL endpoints"}

app.include_router(workflow_router)
app.include_router(assist_router)

def main(port: int | None = None):
    settings = get_settings()
    resolved_port = port or settings.backend_port
    print(f"[*] Starting Crawler Workflow API at http://{settings.backend_host}:{resolved_port}")
    uvicorn.run(app, host=settings.backend_host, port=resolved_port, reload=False)

if __name__ == "__main__":
    import argparse
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=settings.backend_port)
    args = parser.parse_args()
    main(port=args.port)
