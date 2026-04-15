"""
MeetingAgent  — 팀원 1명을 대표하는 에이전트
ModeratorAgent — 중립 사회자 에이전트

plan.md §4-2, §4-3 참조.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass

from .model_client import ClaudeCodeModelClient

logger = logging.getLogger(__name__)


# ── MeetingAgent ──────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    slug: str        # "leecy"
    name: str        # "이창영"
    skill_md: str    # SKILL.md 전체 내용 (frontmatter 제거)
    persona_md: str  # persona.md 전체 내용


class MeetingAgent:
    """
    팀원 한 명을 대표. SKILL.md 를 system prompt 로 사용해
    페르소나를 유지한 채 응답을 생성합니다.
    """

    def __init__(self, config: AgentConfig, model_client: ClaudeCodeModelClient) -> None:
        self.config = config
        self.model_client = model_client
        self._system_prompt: str | None = None

    def build_system_prompt(self, topic: str, file_contents: dict[str, str]) -> None:
        """topic 과 첨부 파일을 반영해 system prompt 를 구성하고 캐시합니다."""
        file_section = ""
        if file_contents:
            parts = ["## 첨부 파일\n"]
            for filename, content in file_contents.items():
                parts.append(f"### {filename}\n\n{content}\n")
            file_section = "\n".join(parts)

        self._system_prompt = (
            f"{self.config.skill_md}\n\n"
            "---\n\n"
            "## 회의 참여 지침\n\n"
            f"지금 당신은 팀 미팅에 참여 중입니다.\n"
            f"안건: {topic}\n"
            f"{file_section}\n"
            "위 정체성과 말투를 유지하며 회의에 참여하세요.\n"
            "다른 팀원의 발언에 반응할 때도 본인 캐릭터를 일관되게 유지하세요.\n"
            "간결하게 발언하세요 (3~5문장 권장)."
        )

    def respond(
        self,
        topic: str,
        history: list[dict],
        instruction: str,
        file_contents: dict[str, str] | None = None,
    ) -> str:
        """
        현재 대화 히스토리와 사회자 지시를 받아 이 팀원의 발언을 생성합니다.

        Args:
            topic:         회의 안건
            history:       현재까지의 전체 대화 히스토리
            instruction:   사회자가 이 팀원에게 내리는 지시
            file_contents: 첨부 파일 내용 {파일명: 내용} (선택)

        Returns:
            생성된 발언 텍스트
        """
        if self._system_prompt is None:
            self.build_system_prompt(topic, file_contents or {})

        messages = list(history)
        messages.append({
            "slug": "__moderator__",
            "speaker": "[사회자]",
            "content": instruction,
        })

        return self.model_client.call(self._system_prompt, messages)


# ── ModeratorAgent ────────────────────────────────────────────────────────────

class ModeratorAgent:
    """
    중립 사회자. 팀원 페르소나 없이 회의 진행만 담당합니다.

    역할:
      - announce_opening   : 회의 개회 선언
      - announce_phase     : Phase 전환 선언
      - select_next_speaker: Phase 2 다음 발언자 선택
      - draft_consensus    : Phase 3 합의안 작성
    """

    _SYSTEM_PROMPT = (
        "당신은 팀 미팅의 중립적인 사회자입니다.\n"
        "팀원들의 의견을 정리하고, 토론을 구조적으로 진행하며, "
        "최종 합의안을 도출합니다.\n"
        "간결하고 명확하게 말하세요."
    )

    def __init__(
        self,
        model_client: ClaudeCodeModelClient,
        participant_slugs: list[str],
    ) -> None:
        self.model_client = model_client
        self.participant_slugs = list(participant_slugs)

    # ── Phase actions ─────────────────────────────────────────────────────────

    def announce_opening(self, topic: str, history: list[dict]) -> str:
        instruction = (
            f"팀 미팅을 시작합니다. 오늘 안건은 다음과 같습니다:\n\n"
            f"**{topic}**\n\n"
            "안건을 간략히 정리하고 Phase 1 (초기 의견 수집)을 시작한다고 선언하세요."
        )
        return self.model_client.call(
            self._SYSTEM_PROMPT,
            [{"slug": "__moderator__", "speaker": "[사회자]", "content": instruction}],
        )

    def announce_phase(self, phase: int, history: list[dict]) -> str:
        phase_names = {
            2: "Phase 2: 자유 토론",
            3: "Phase 3: 최종 입장 및 합의 도출",
        }
        instruction = (
            f"{phase_names.get(phase, f'Phase {phase}')}으로 넘어가겠습니다. "
            "지금까지의 논의를 한 줄로 요약하고, 이 단계의 목적을 안내하세요."
        )
        return self.model_client.call(
            self._SYSTEM_PROMPT,
            history + [{"slug": "__moderator__", "speaker": "[사회자]", "content": instruction}],
        )

    def select_next_speaker(
        self, history: list[dict], exclude: str | None = None
    ) -> str:
        """
        Phase 2에서 다음 발언자 slug를 선택합니다.
        exclude: 직전 발언자 slug — 이 사람은 선택하지 않음.
        파싱 실패 시 참여자 중 랜덤 선택으로 fallback.
        """
        available = [s for s in self.participant_slugs if s != exclude]
        if not available:
            available = list(self.participant_slugs)  # 전원이 exclude되면 무시

        slugs_str = ", ".join(available)
        history_summary = self._summarize_history(history)
        instruction = (
            f"다음 발언자를 선택하세요.\n"
            f"선택지: {slugs_str}\n\n"
            f"현재까지 대화 흐름:\n{history_summary}\n\n"
            "가장 기여할 수 있는 사람 1명의 slug만 출력하세요. "
            "다른 텍스트 없이 slug 만 출력하세요."
        )
        response = self.model_client.call(
            self._SYSTEM_PROMPT,
            [{"slug": "__moderator__", "speaker": "[사회자]", "content": instruction}],
        ).strip()

        slug = self._parse_slug(response, available)
        if slug not in available:
            logger.warning(
                "ModeratorAgent returned unknown slug %r — falling back to random", slug
            )
            slug = random.choice(available)
        return slug

    def draft_consensus(self, topic: str, history: list[dict]) -> str:
        instruction = (
            f"안건 **{topic}**에 대한 팀 토론이 끝났습니다.\n"
            "지금까지의 모든 발언을 바탕으로 팀의 합의안을 작성하세요.\n"
            "형식: 마크다운. 결정 사항, 주요 합의 포인트, 보류/추가 검토 사항을 포함하세요."
        )
        return self.model_client.call(
            self._SYSTEM_PROMPT,
            history + [{"slug": "__moderator__", "speaker": "[사회자]", "content": instruction}],
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse_slug(self, text: str, available: list[str] | None = None) -> str:
        """텍스트에서 알려진 slug 를 추출. 없으면 첫 번째 단어 반환."""
        candidates = available if available is not None else self.participant_slugs
        for slug in candidates:
            if slug in text:
                return slug
        match = re.search(r"\b([a-z][a-z0-9_-]+)\b", text)
        return match.group(1) if match else ""

    @staticmethod
    def _summarize_history(history: list[dict], max_entries: int = 10) -> str:
        """히스토리 최근 N개를 '화자: 내용(80자)...' 형식으로 요약."""
        recent = history[-max_entries:]
        lines: list[str] = []
        for msg in recent:
            if msg.get("slug") == "__moderator__":
                speaker = "[사회자]"
            else:
                speaker = msg.get("speaker") or msg.get("slug") or "?"
            preview = msg["content"][:80].replace("\n", " ")
            lines.append(f"{speaker}: {preview}…")
        return "\n".join(lines)
