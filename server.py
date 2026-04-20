"""
server.py - FastAPI-based inspector UI with Crawler Prompt Builder.

Usage:
    python server.py
    uvicorn server:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.browser_session import page_session_mgr, stop_browser
from backend.legacy_routes import router as legacy_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    page_session_mgr.close_all()
    stop_browser()

app = FastAPI(title="Page Inspector", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    return Path("templates/index.html").read_text(encoding="utf-8")

app.include_router(legacy_router)

def main(port: int = 8000):
    print(f"[*] Starting Page Inspector at http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=8000)
    args = parser.parse_args()
    main(port=args.port)
