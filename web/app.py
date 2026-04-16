"""
FastAPI 앱 진입점.

실행:
    uvicorn web.app:app --reload --port 8000
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import history, participants, simulation, slack_extraction

app = FastAPI(title="Team Meeting Simulation API")

cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
cors_origins = [origin.strip() for origin in cors_origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(participants.router, prefix="/api")
app.include_router(simulation.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(slack_extraction.router, prefix="/api")
