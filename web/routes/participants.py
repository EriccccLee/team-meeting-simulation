"""
GET /api/participants — 팀원 목록 반환
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

TEAM_SKILLS_DIR = Path(__file__).parent.parent.parent / "team-skills"

_PALETTE = [
    "#FF4500", "#2563EB", "#16A34A", "#9333EA", "#DC2626",
    "#0891B2", "#059669", "#7C3AED", "#DB2777", "#CA8A04",
]


def _color_for_slug(slug: str) -> str:
    """slug 해시 기반으로 팔레트에서 색상 결정론적 선택."""
    idx = int(hashlib.md5(slug.encode()).hexdigest(), 16)
    return _PALETTE[idx % len(_PALETTE)]


class Participant(BaseModel):
    slug: str
    name: str
    color: str


@router.get("/participants", response_model=list[Participant])
def get_participants() -> list[Participant]:
    """team-skills/ 디렉터리를 스캔해 팀원 목록을 반환합니다."""
    result = []
    for member_dir in sorted(TEAM_SKILLS_DIR.iterdir()):
        if not member_dir.is_dir():
            continue
        slug = member_dir.name
        meta_path = member_dir / "meta.json"
        meta: dict = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        raw_name = meta.get("name", slug)
        name = raw_name.split("[")[0].strip()
        color = _color_for_slug(slug)
        result.append(Participant(slug=slug, name=name, color=color))
    return result
