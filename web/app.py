"""
FastAPI 앱 진입점.

실행:
    uvicorn web.app:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import history, participants, simulation

app = FastAPI(title="Team Meeting Simulation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(participants.router, prefix="/api")
app.include_router(simulation.router, prefix="/api")
app.include_router(history.router, prefix="/api")
