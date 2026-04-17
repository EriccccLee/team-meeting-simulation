"""
MeetingSession
──────────────
실시간 터미널 출력 + 마크다운 회의록 파일 생성을 담당합니다.

plan.md §4-5 참조.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable


def _make_slug(text: str) -> str:
    """topic 텍스트를 ASCII 안전 파일명 slug로 변환."""
    try:
        from unidecode import unidecode
        text = unidecode(text)
    except ImportError:
        # unidecode 없으면 비ASCII 문자 제거
        text = re.sub(r"[^\x00-\x7F]+", "", text)
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:30] or "meeting"


class MeetingSession:
    """
    회의 중 발생하는 모든 출력을 담당합니다.

    - stream_phase    : Phase 전환 구분선 출력
    - stream_message  : 팀원 발언 출력
    - stream_moderator: 사회자 발언 출력
    - save            : outputs/ 에 마크다운 파일 저장

    emit 콜백이 주어지면 각 stream_* 호출 시 이벤트 dict 를 emit(event) 로 전달합니다.
    CLI 경로에서는 emit=None 으로 기존 동작이 유지됩니다.
    """

    def __init__(
        self,
        topic: str,
        participants: list[str],
        output_dir: str = "outputs",
        emit: Callable[[dict], None] | None = None,
    ) -> None:
        self.topic = topic
        self.participants = participants
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = datetime.now()
        self._emit = emit

        # 파일 저장용 버퍼 (마크다운 형식)
        self._sections: list[str] = []

    # ── 터미널 출력 ──────────────────────────────────────────────────────────

    def stream_phase(self, phase_name: str) -> None:
        bar = "=" * 40
        self._print(f"\n{bar}\n[{phase_name}]\n{bar}\n")
        self._sections.append(f"\n## {phase_name}\n")
        if self._emit:
            self._emit({"type": "phase", "label": phase_name})

    def stream_message(
        self,
        speaker: str,
        content: str,
        slug: str = "",
        evidence: list[str] | None = None,
    ) -> None:
        """팀원 발언 출력.

        Args:
            speaker: 발언자 이름
            content: 발언 내용
            slug: 발언자 식별자 (선택)
            evidence: 근거가 된 과거 Slack 메시지 목록 (선택) — 프론트엔드에서 tooltip으로 표시
        """
        label = f"[{speaker}]" + (f" ({slug})" if slug else "")
        self._print(f"\n{label}")
        self._print(content)

        md_heading = f"### {speaker}" + (f" ({slug})" if slug else "")
        self._sections.append(f"\n{md_heading}\n{content}\n")
        if self._emit:
            event = {"type": "message", "speaker": speaker, "slug": slug, "content": content}
            if evidence:
                event["evidence"] = evidence
            self._emit(event)

    def stream_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        slug: str,
        speaker: str,
        failed: bool = False,
    ) -> None:
        """도구 사용 이벤트를 SSE 로 전달합니다. CLI 경로에서는 아무것도 하지 않습니다."""
        if self._emit:
            self._emit({
                "type": "tool_use",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "slug": slug,
                "speaker": speaker,
                "failed": failed,
            })

    def stream_moderator(self, content: str) -> None:
        """사회자 발언 출력."""
        self._print(f"\n[사회자] {content}")
        self._sections.append(f"\n**[사회자]**: {content}\n")
        if self._emit:
            self._emit({"type": "moderator", "content": content})

    @staticmethod
    def _print(text: str) -> None:
        """유니코드 안전 출력 (cli.py 에서 stdout 을 UTF-8 로 재설정한 후 호출됨)."""
        print(text, flush=True)

    # ── 파일 저장 ─────────────────────────────────────────────────────────────

    def save(self, participants_info: list[dict], consensus: str) -> Path:
        """
        회의 전체 내용을 마크다운 파일로 저장하고 경로를 반환합니다.

        Args:
            participants_info: [{"name": "이창영", "slug": "leecy"}, …]
            consensus:         ModeratorAgent 가 작성한 합의안 전문
        """
        timestamp = self.started_at.strftime("%Y-%m-%d-%H-%M")
        topic_slug = _make_slug(self.topic)
        filename = f"{timestamp}-{topic_slug}.md"
        filepath = self.output_dir / filename

        participants_str = ", ".join(
            p.get("name") or p.get("slug", "?") for p in participants_info
        )

        header = (
            "# 팀 미팅 시뮬레이션\n\n"
            f"- **안건**: {self.topic}\n"
            f"- **일시**: {self.started_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"- **참석자**: {participants_str}\n\n"
            "---\n"
        )

        # 합의안은 인용 블록으로
        consensus_lines = "\n".join(
            f"> {line}" if line.strip() else ">"
            for line in consensus.splitlines()
        )
        consensus_section = f"\n## 합의안\n\n{consensus_lines}\n"

        body = "".join(self._sections)
        filepath.write_text(header + body + consensus_section, encoding="utf-8")

        self._print(f"\n[저장 완료] {filepath}")
        return filepath
