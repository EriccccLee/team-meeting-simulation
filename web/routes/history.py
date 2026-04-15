"""
GET /api/history            — 저장된 회의 목록 (최신순)
GET /api/history/{session_id} — 특정 회의 전체 데이터
DELETE /api/history/{session_id} — 특정 회의 삭제
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

_ROOT = Path(__file__).parent.parent.parent
HISTORY_DIR = _ROOT / "outputs" / "history"


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
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="history not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{session_id}")
def delete_history(session_id: str) -> dict:
    """특정 회의 기록 삭제."""
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="history not found")
    path.unlink()
    return {"ok": True}
