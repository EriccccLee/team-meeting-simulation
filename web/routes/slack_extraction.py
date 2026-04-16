"""
GET  /api/slack/discover            — 채널에서 활성 유저 탐색
POST /api/slack/extract             — 스킬 추출 시작 (session_id 즉시 반환)
GET  /api/slack/stream/{session_id} — SSE 스트림
"""
from __future__ import annotations

import asyncio
import json
import os
import queue as stdlib_queue
import re
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

_ROOT = Path(__file__).parent.parent.parent

load_dotenv(_ROOT / ".env", override=False)

from simulation.slack_collector import _run_extraction, discover_users

router = APIRouter()

_TEAM_SKILLS_DIR = _ROOT / "team-skills"
_sessions: dict[str, stdlib_queue.SimpleQueue] = {}

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


def _validate_session_id(session_id: str) -> None:
    if not _UUID_RE.fullmatch(session_id):
        raise HTTPException(status_code=400, detail="invalid session_id format")


def _get_slack_config() -> tuple[str, list[str] | None]:
    """SLACK_BOT_TOKEN 필수, SLACK_CHANNELS 선택(없으면 None — 자동 탐색)."""
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status_code=400,
            detail="SLACK_BOT_TOKEN이 .env에 설정되지 않았습니다.",
        )
    channels_raw = os.getenv("SLACK_CHANNELS", "").strip()
    if not channels_raw:
        return token, None  # collect_user_messages에서 자동 탐색
    channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    return token, channels


@router.get("/slack/discover")
def slack_discover() -> list[dict[str, Any]]:
    token, channels = _get_slack_config()
    if channels is None:
        raise HTTPException(
            status_code=400,
            detail="SLACK_CHANNELS가 .env에 설정되지 않았습니다. 채널 탐색에는 SLACK_CHANNELS가 필요합니다.",
        )
    try:
        return discover_users(channels, token, min_messages=3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExtractMember(BaseModel):
    user_id: str
    slug: str
    display_name: str
    role: str = "general"
    impression: str = ""

    @field_validator("slug")
    @classmethod
    def slug_must_be_safe(cls, v: str) -> str:
        sanitized = re.sub(r"[^a-z0-9_]", "", v.lower())
        if not sanitized:
            raise ValueError("slug must contain at least one alphanumeric character")
        return sanitized

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        # Tolerant: unknown roles fall back to "general" rather than rejecting the request.
        valid = {"backend", "frontend", "ml", "pm", "data", "general"}
        return v if v in valid else "general"


class ExtractRequest(BaseModel):
    members: list[ExtractMember]
    max_collect: int = 2000
    max_messages: int = 300


@router.post("/slack/extract")
async def slack_extract(req: ExtractRequest) -> dict[str, str]:
    if not req.members:
        raise HTTPException(status_code=400, detail="추출할 팀원을 1명 이상 선택하세요.")

    token, channels = _get_slack_config()

    session_id = str(uuid.uuid4())
    q: stdlib_queue.SimpleQueue = stdlib_queue.SimpleQueue()
    _sessions[session_id] = q

    members_dicts = [m.model_dump() for m in req.members]

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        _run_extraction,
        members_dicts,
        token,
        channels,
        q,
        _TEAM_SKILLS_DIR,
        req.max_collect,
        req.max_messages,
    )

    return {"session_id": session_id}


@router.get("/slack/stream/{session_id}")
async def slack_stream(session_id: str) -> StreamingResponse:
    _validate_session_id(session_id)

    q = _sessions.get(session_id)
    if q is None:
        raise HTTPException(status_code=404, detail="session not found")

    async def generate():
        try:
            while True:
                try:
                    event = q.get_nowait()
                except stdlib_queue.Empty:
                    await asyncio.sleep(0.05)
                    continue

                if event is None:
                    yield 'data: {"type": "end"}\n\n'
                    break

                data = json.dumps(event, ensure_ascii=False)
                yield f"data: {data}\n\n"
                await asyncio.sleep(0)  # 이벤트 루프에 제어권 반환 → uvicorn TCP flush
        finally:
            _sessions.pop(session_id, None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
