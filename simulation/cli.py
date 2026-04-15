"""
진입점 — argparse 기반 CLI

사용법:
    python -m simulation.cli --topic "RAG 아키텍처 Neo4j vs 벡터DB"
    python -m simulation.cli --topic "기획서 검토" --files proposal.md
    python -m simulation.cli --topic "배포 전략" --participants leecy jasonjoe --rounds 5

plan.md §4-6 참조.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Windows cp949 터미널에서도 한글/유니코드를 올바르게 출력하기 위해
# stdout/stderr 를 UTF-8 로 재설정합니다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .agents import MeetingAgent, ModeratorAgent
from .loader import load_agent_config as _load_agent_config, load_file_contents as _load_file_contents
from .model_client import ClaudeCodeModelClient, run_claude_prompt
from .orchestrator import MeetingOrchestrator, OrchestratorConfig
from .session import MeetingSession

TEAM_SKILLS_DIR = Path(__file__).parent.parent / "team-skills"

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)


# ── Loaders ───────────────────────────────────────────────────────────────────

def _all_slugs() -> list[str]:
    return sorted(p.name for p in TEAM_SKILLS_DIR.iterdir() if p.is_dir())


def _pdf_to_md_via_claude(path: Path, timeout: int = 300) -> str:
    """
    `claude -p` 의 Read 도구를 사용해 PDF를 마크다운으로 변환합니다.

    라이브러리(pypdf/fitz) 방식과 달리 표·다이어그램·이미지도 의미 있게 변환합니다.
    변환된 마크다운은 PDF 와 같은 폴더에 <파일명>.converted.md 로 저장됩니다.

    Args:
        path:    PDF 파일 경로
        timeout: subprocess 타임아웃 (초). 대용량 PDF 는 길게 설정 필요.
    """
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

    try:
        md = run_claude_prompt(
            [
                "-p", prompt,
                "--output-format", "text",
                "--allowedTools", "Read",
                "--add-dir", str(abs_path.parent),
                "--no-session-persistence",
            ],
            timeout=timeout,
        )
    except TimeoutError:
        raise RuntimeError(f"PDF 변환 타임아웃 ({timeout}초 초과): {path.name}")
    except RuntimeError as e:
        raise RuntimeError(f"PDF → MD 변환 실패: {e}") from e

    # 변환 결과를 파일로 저장 (재사용 및 내용 확인용)
    md_path = abs_path.with_suffix(".converted.md")
    md_path.write_text(md, encoding="utf-8")
    print(f"[변환 파일 저장] {md_path}")

    return md


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    all_slugs = _all_slugs()

    parser = argparse.ArgumentParser(
        prog="python -m simulation.cli",
        description="팀원 페르소나 기반 팀 미팅 시뮬레이션",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="회의 주제 (필수)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        metavar="FILE",
        help="첨부 파일 경로들",
    )
    parser.add_argument(
        "--participants",
        nargs="*",
        default=all_slugs,
        metavar="SLUG",
        help=f"참여 팀원 slug (기본: 전원). 가능한 값: {', '.join(all_slugs)}",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="Phase 2 발언 횟수 (기본: 3)",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="결과 파일 저장 경로 (기본: outputs/)",
    )

    args = parser.parse_args()

    # 팀원 slug 검증
    invalid = [s for s in args.participants if s not in all_slugs]
    if invalid:
        print(f"[오류] 알 수 없는 팀원 slug: {', '.join(invalid)}", file=sys.stderr)
        print(f"사용 가능한 slug: {', '.join(all_slugs)}", file=sys.stderr)
        sys.exit(1)

    if not args.participants:
        print("[오류] 참여 팀원이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 컴포넌트 초기화
    model_client = ClaudeCodeModelClient()  # 기본 120초
    file_contents = _load_file_contents(args.files)

    agents: list[MeetingAgent] = []
    for slug in args.participants:
        try:
            config = _load_agent_config(slug)
            agents.append(MeetingAgent(config, model_client))
        except FileNotFoundError as e:
            print(f"[경고] {e} — 이 팀원은 제외합니다.", file=sys.stderr)

    if not agents:
        print("[오류] 유효한 참여 팀원이 없습니다.", file=sys.stderr)
        sys.exit(1)

    participant_slugs = [a.config.slug for a in agents]
    moderator = ModeratorAgent(model_client, participant_slugs)
    session = MeetingSession(args.topic, participant_slugs, output_dir=args.output_dir)
    config = OrchestratorConfig(phase2_rounds=args.rounds)
    orchestrator = MeetingOrchestrator(agents, moderator, session, config)

    # 시뮬레이션 실행
    def safe_print(text: str) -> None:
        try:
            print(text, flush=True)
        except UnicodeEncodeError:
            print(text.encode("utf-8", errors="replace").decode("ascii", errors="replace"), flush=True)

    safe_print("\n팀 미팅 시뮬레이션 시작")
    safe_print(f"안건: {args.topic}")
    safe_print(f"참석자: {', '.join(a.config.name for a in agents)}")
    if file_contents:
        safe_print(f"첨부 파일: {', '.join(file_contents.keys())}")
    safe_print("")

    result = orchestrator.run(args.topic, file_contents)
    safe_print(f"\n회의록이 저장되었습니다: {result.output_file}")


if __name__ == "__main__":
    main()
