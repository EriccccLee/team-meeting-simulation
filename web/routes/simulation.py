"""
POST /api/run       — 시뮬레이션 시작, session_id 반환
GET  /api/stream/{session_id} — SSE 이벤트 스트림
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

# simulation 패키지가 상위 디렉터리에 있으므로 sys.path 조정
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.agents import MeetingAgent, ModeratorAgent
from simulation.model_client import ClaudeCodeModelClient
from simulation.orchestrator import MeetingOrchestrator, OrchestratorConfig
from simulation.session import MeetingSession
from simulation.cli import _load_agent_config, _load_file_contents

router = APIRouter()

# session_id → asyncio.Queue 매핑
_sessions: dict[str, asyncio.Queue] = {}


# ── 시뮬레이션 실행 (동기, 별도 스레드에서 호출됨) ────────────────────────────

def _run_simulation(
    session_id: str,
    topic: str,
    participant_slugs: list[str],
    rounds: int,
    file_contents: dict[str, str],
    loop: asyncio.AbstractEventLoop,
) -> None:
    """orchestrator.run() 을 동기 스레드에서 실행하고 결과를 SSE queue 에 push 합니다."""
    queue = _sessions[session_id]

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    try:
        model_client = ClaudeCodeModelClient()
        agents: list[MeetingAgent] = []
        for slug in participant_slugs:
            config = _load_agent_config(slug)
            agents.append(MeetingAgent(config, model_client))

        moderator = ModeratorAgent(model_client, participant_slugs)
        session = MeetingSession(
            topic,
            participant_slugs,
            output_dir=str(_ROOT / "outputs"),
            emit=emit,
        )
        config = OrchestratorConfig(phase2_rounds=rounds)
        orchestrator = MeetingOrchestrator(agents, moderator, session, config)
        result = orchestrator.run(topic, file_contents)

        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "done", "output_file": str(result.output_file)},
        )
    except Exception as e:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "error", "message": str(e)},
        )
    finally:
        # 스트림 종료 신호 (sentinel)
        loop.call_soon_threadsafe(queue.put_nowait, None)


# ── API 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("/run")
async def run_simulation(
    topic: Annotated[str, Form()],
    participants: Annotated[list[str], Form()],
    rounds: Annotated[int, Form()] = 3,
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """시뮬레이션을 백그라운드 스레드에서 시작하고 session_id 를 즉시 반환합니다."""
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _sessions[session_id] = queue
    loop = asyncio.get_running_loop()

    # 업로드된 파일을 임시 디렉터리에 저장
    file_contents: dict[str, str] = {}
    for upload in files:
        raw = await upload.read()
        if upload.filename and upload.filename.lower().endswith(".pdf"):
            # PDF는 임시 파일로 저장 후 _load_file_contents 로 변환
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".pdf", delete=False, dir=str(_ROOT)
                ) as tmp:
                    tmp.write(raw)
                    tmp_path = tmp.name
                loaded = _load_file_contents([tmp_path])
                file_contents.update(loaded)
            finally:
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)
        else:
            name = upload.filename or "attachment.txt"
            try:
                file_contents[name] = raw.decode("utf-8")
            except UnicodeDecodeError:
                file_contents[name] = raw.decode("cp949", errors="replace")

    # 동기 orchestrator 를 별도 스레드에서 실행
    # Future를 ensure_future로 감싸 unhandled exception 경고 방지
    future = loop.run_in_executor(
        None,
        _run_simulation,
        session_id,
        topic,
        participants,
        rounds,
        file_contents,
        loop,
    )
    asyncio.ensure_future(future)

    return {"session_id": session_id}


@router.get("/stream/{session_id}")
async def stream_events(session_id: str) -> StreamingResponse:
    """SSE 스트림 — 시뮬레이션 이벤트를 실시간으로 전송합니다."""
    queue = _sessions.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="session not found")

    async def generate():
        try:
            while True:
                event = await queue.get()
                if event is None:  # sentinel — 스트림 종료
                    yield 'data: {"type": "end"}\n\n'
                    break
                data = json.dumps(event, ensure_ascii=False)
                yield f"data: {data}\n\n"
        finally:
            _sessions.pop(session_id, None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
