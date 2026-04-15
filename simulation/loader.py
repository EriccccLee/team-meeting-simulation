"""
simulation/loader.py — 에이전트 설정과 파일 내용 로딩 유틸리티.

cli.py와 web/routes/simulation.py 양쪽에서 공유하는 로더 함수.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
TEAM_SKILLS_DIR = _ROOT / "team-skills"


def _strip_frontmatter(text: str) -> str:
    """YAML front matter(--- ... ---) 제거."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1:]).lstrip("\n")
    return text


def load_agent_config(slug: str):
    """
    team-skills/{slug}/ 에서 AgentConfig 로드.
    Raises: FileNotFoundError if SKILL.md missing.
    """
    from simulation.agents import AgentConfig  # 지연 import (순환 방지)

    member_dir = TEAM_SKILLS_DIR / slug
    skill_path = member_dir / "SKILL.md"
    persona_path = member_dir / "persona.md"
    meta_path = member_dir / "meta.json"

    if not skill_path.exists():
        raise FileNotFoundError(f"SKILL.md 없음: '{slug}'")

    meta: dict = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    raw_name = meta.get("name", slug)
    name = raw_name.split("[")[0].strip()

    skill_md = _strip_frontmatter(skill_path.read_text(encoding="utf-8"))
    persona_md = (
        _strip_frontmatter(persona_path.read_text(encoding="utf-8"))
        if persona_path.exists()
        else ""
    )
    return AgentConfig(slug=slug, name=name, skill_md=skill_md, persona_md=persona_md)


def load_file_contents(file_paths: list[str]) -> dict[str, str]:
    """
    파일 경로 목록에서 텍스트 내용 로드.
    PDF는 claude -p로 마크다운 변환. 누락 파일은 스킵.
    """
    from simulation.model_client import run_claude_prompt  # 지연 import

    contents: dict[str, str] = {}
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            print(f"[경고] 첨부 파일을 찾을 수 없습니다: {fp}", file=sys.stderr)
            continue
        try:
            if path.suffix.lower() == ".pdf":
                print(f"[PDF 변환 중] {path.name} → claude 로 마크다운 변환 중... (최대 5분 소요)")
                abs_path = path.resolve()
                prompt = (
                    f"다음 PDF 파일을 읽고 전체 내용을 마크다운으로 변환해주세요: {abs_path}\n\n"
                    "변환 규칙:\n"
                    "- 제목/소제목 계층을 # ## ### 로 유지\n"
                    "- 표/데이터는 마크다운 표(| col | col |) 형식으로 재구성\n"
                    "- 로드맵·간트차트·타임라인은 마크다운 표나 번호 목록으로 표현\n"
                    "- 이미지/다이어그램은 [이미지: 내용 설명] 형식으로 의미를 텍스트화\n"
                    "- 내용을 요약하지 말고 전체를 변환\n"
                    "- 마크다운 코드블록 래퍼(```markdown) 없이 바로 마크다운 내용만 출력"
                )
                md = run_claude_prompt(
                    [
                        "-p", prompt,
                        "--output-format", "text",
                        "--allowedTools", "Read",
                        "--add-dir", str(abs_path.parent),
                        "--no-session-persistence",
                    ],
                    timeout=300,
                )
                print(f"[PDF 변환 완료] {len(md)}자 추출")
                contents[path.stem + ".md"] = md
            else:
                contents[path.name] = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[경고] {path.name} 처리 실패: {e} — 건너뜁니다.", file=sys.stderr)
    return contents
