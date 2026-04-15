"""
GET /api/participants — 팀원 목록 반환
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

TEAM_SKILLS_DIR = Path(__file__).parent.parent.parent / "team-skills"

# 팀원별 아바타 색상 (디자인 시스템 확정값)
_COLORS: dict[str, str] = {
    "leecy":      "#FF4500",
    "jasonjoe":   "#2563EB",
    "philgineer": "#16A34A",
    "jmyeon":     "#9333EA",
    "rockmin":    "#DC2626",
}
_DEFAULT_COLORS = ["#FF4500", "#2563EB", "#16A34A", "#9333EA", "#DC2626", "#CA8A04"]


@router.get("/participants")
def get_participants() -> list[dict]:
    """team-skills/ 디렉터리를 스캔해 팀원 목록을 반환합니다."""
    result = []
    for i, member_dir in enumerate(sorted(TEAM_SKILLS_DIR.iterdir())):
        if not member_dir.is_dir():
            continue
        slug = member_dir.name
        meta_path = member_dir / "meta.json"
        meta: dict = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_name = meta.get("name", slug)
        name = raw_name.split("[")[0].strip()
        color = _COLORS.get(slug, _DEFAULT_COLORS[i % len(_DEFAULT_COLORS)])
        result.append({"slug": slug, "name": name, "color": color})
    return result
