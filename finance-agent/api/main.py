"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import intelligence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Finance Agent API",
    description="AI-assisted financial analysis: earnings calls, screening, portfolio insights.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(intelligence.router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """Simple liveness check."""
    return {"status": "ok"}
