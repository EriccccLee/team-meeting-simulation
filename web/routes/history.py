"""
GET /api/history            — 저장된 회의 목록 (최신순)
GET /api/history/{session_id} — 특정 회의 전체 데이터
DELETE /api/history/{session_id} — 특정 회의 삭제
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter()

_ROOT = Path(__file__).parent.parent.parent
HISTORY_DIR = _ROOT / "outputs" / "history"

_TEAM_SKILLS_DIR = _ROOT / "team-skills"


def _resolve_name(slug: str) -> str:
    """team-skills/{slug}/meta.json 에서 display name 조회, 없으면 slug 반환."""
    meta_path = _TEAM_SKILLS_DIR / slug / "meta.json"
    if not meta_path.exists():
        return slug
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw = meta.get("name", slug)
        return raw.split("[")[0].strip()
    except Exception:
        return slug


def _feed_to_markdown(data: dict) -> str:
    """히스토리 JSON 데이터를 구조화된 마크다운 문자열로 변환."""
    topic = data.get("topic", "")
    participants = data.get("participants", [])
    timestamp = data.get("timestamp", "")
    feed = data.get("feed", [])

    names = {s: _resolve_name(s) for s in participants}
    participant_str = ", ".join(names.get(s, s) for s in participants)

    lines: list[str] = [
        "# 이전 회의 기록",
        "",
        f"- **안건:** {topic}",
        f"- **참여자:** {participant_str}",
        f"- **일시:** {timestamp}",
        "",
        "---",
        "",
    ]

    # 마지막 moderator 메시지 인덱스 찾기 (합의안)
    last_mod_idx = -1
    for i in range(len(feed) - 1, -1, -1):
        if feed[i].get("type") == "moderator":
            last_mod_idx = i
            break

    for i, event in enumerate(feed):
        t = event.get("type")
        if t == "phase":
            lines.append(f"## {event.get('label', '')}")
            lines.append("")
        elif t == "moderator":
            content = event.get("content", "")
            if i == last_mod_idx:
                lines.append("## 최종 합의안")
                lines.append("")
                lines.append(content)
                lines.append("")
            else:
                lines.append(f"> *사회자: {content}*")
                lines.append("")
        elif t == "message":
            speaker = event.get("speaker", "")
            slug = event.get("slug", "")
            content = event.get("content", "")
            lines.append(f"**{speaker} ({slug}):**")
            lines.append(content)
            lines.append("")

    return "\n".join(lines)


_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


def _validate_session_id(session_id: str) -> None:
    if not _UUID_RE.fullmatch(session_id):
        raise HTTPException(status_code=400, detail="invalid session_id format")


def _read_meta(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "session_id": data["session_id"],
            "topic": data["topic"],
            "participants": data.get("participants", []),
            "timestamp": data["timestamp"],
        }
    except Exception:
        return None


@router.get("/history")
def list_history() -> list[dict]:
    """저장된 회의 목록 반환 (최신순)."""
    if not HISTORY_DIR.exists():
        return []
    files = sorted(HISTORY_DIR.glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for p in files:
        meta = _read_meta(p)
        if meta:
            result.append(meta)
    return result


@router.get("/history/{session_id}")
def get_history(session_id: str) -> dict:
    """특정 회의의 전체 데이터(피드 포함) 반환."""
    _validate_session_id(session_id)
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="history not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}/markdown")
def get_history_markdown(session_id: str) -> PlainTextResponse:
    """특정 회의를 마크다운 텍스트로 반환 (후속 회의 참조용)."""
    _validate_session_id(session_id)
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="history not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    md = _feed_to_markdown(data)
    return PlainTextResponse(md, media_type="text/plain; charset=utf-8")


@router.delete("/history/{session_id}")
def delete_history(session_id: str) -> dict:
    """특정 회의 기록 삭제."""
    _validate_session_id(session_id)
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="history not found")
    path.unlink()
    return {"ok": True}
