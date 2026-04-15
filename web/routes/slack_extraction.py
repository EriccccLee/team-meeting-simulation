"""
GET  /api/slack/discover            — 채널에서 활성 유저 탐색
POST /api/slack/extract             — 스킬 추출 시작 (session_id 즉시 반환)
GET  /api/slack/stream/{session_id} — SSE 스트림 (기존 패턴과 동일)
"""
from __future__ import annotations

import asyncio
import json
import os
import queue as stdlib_queue
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import re as _re

from pydantic import BaseModel, field_validator

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# .env 로드 (이미 로드된 경우 덮어쓰지 않음)
load_dotenv(_ROOT / ".env", override=False)

from simulation.slack_collector import _run_extraction, discover_users

router = APIRouter()

_TEAM_SKILLS_DIR = _ROOT / "team-skills"
_sessions: dict[str, stdlib_queue.SimpleQueue] = {}


def _get_slack_config() -> tuple[str, list[str]]:
    """SLACK_BOT_TOKEN, SLACK_CHANNELS 읽기. 없으면 400 raise."""
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    channels_raw = os.getenv("SLACK_CHANNELS", "").strip()

    if not token:
        raise HTTPException(
            status_code=400,
            detail="SLACK_BOT_TOKEN이 .env에 설정되지 않았습니다.",
        )
    if not channels_raw:
        raise HTTPException(
            status_code=400,
            detail="SLACK_CHANNELS가 .env에 설정되지 않았습니다.",
        )

    channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    return token, channels


@router.get("/slack/discover")
def slack_discover() -> list[dict[str, Any]]:
    """채널에서 3개 이상 메시지를 보낸 유저 목록 반환."""
    token, channels = _get_slack_config()
    try:
        return discover_users(channels, token, min_messages=3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExtractMember(BaseModel):
    user_id: str
    slug: str
    display_name: str

    @field_validator("slug")
    @classmethod
    def slug_must_be_safe(cls, v: str) -> str:
        sanitized = _re.sub(r"[^a-z0-9_]", "", v.lower())
        if not sanitized:
            raise ValueError("slug must contain at least one alphanumeric character")
        return sanitized


@router.post("/slack/extract")
async def slack_extract(members: list[ExtractMember]) -> dict[str, str]:
    """추출 세션 시작. session_id 즉시 반환하고 백그라운드에서 추출 실행."""
    if not members:
        raise HTTPException(status_code=400, detail="추출할 팀원을 1명 이상 선택하세요.")

    token, channels = _get_slack_config()

    session_id = str(uuid.uuid4())
    q: stdlib_queue.SimpleQueue = stdlib_queue.SimpleQueue()
    _sessions[session_id] = q

    members_dicts = [m.model_dump() for m in members]

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        _run_extraction,
        members_dicts,
        token,
        channels,
        q,
        _TEAM_SKILLS_DIR,
    )

    return {"session_id": session_id}


@router.get("/slack/stream/{session_id}")
async def slack_stream(session_id: str) -> StreamingResponse:
    """SSE 스트림 — SimpleQueue 50ms 폴링 (기존 /api/stream 과 동일한 패턴)."""
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
        finally:
            _sessions.pop(session_id, None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
