"""
MeetingOrchestrator
───────────────────
3단계(Phase 1→2→3) 회의 흐름을 순서대로 실행하는 컨트롤러.

plan.md §4-4 참조.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .agents import MeetingAgent, ModeratorAgent
from .session import MeetingSession

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    phase2_rounds: int = 3          # Phase 2 총 발언 횟수
    max_tokens_per_turn: int = 500  # system prompt 지시용 (API 강제 아님)
    call_delay: float = 8.0         # 연속 claude 호출 간 대기 시간 (초). rate limit 방지.


@dataclass
class MeetingResult:
    output_file: Path
    consensus: str
    history: list[dict] = field(default_factory=list)


class MeetingOrchestrator:
    """
    3단계 회의 흐름을 실행합니다.

    Phase 1: 초기 의견 수집 — 참여자 순서대로 1번씩 발언
    Phase 2: 자유 토론     — Moderator 가 다음 발언자 선택 × phase2_rounds
    Phase 3: 합의 도출     — 최종 입장 수집 → Moderator 합의안 작성
    """

    def __init__(
        self,
        agents: list[MeetingAgent],
        moderator: ModeratorAgent,
        session: MeetingSession,
        config: OrchestratorConfig | None = None,
    ) -> None:
        self.agents = agents
        self.moderator = moderator
        self.session = session
        self.config = config or OrchestratorConfig()
        self.history: list[dict] = []

    def run(self, topic: str, file_contents: dict[str, str]) -> MeetingResult:
        # 각 에이전트의 system prompt 에 topic + 첨부 파일 주입
        for agent in self.agents:
            agent.build_system_prompt(topic, file_contents)

        self._phase1(topic)
        self._phase2(topic)
        consensus = self._phase3(topic)

        participants_info = [
            {"name": a.config.name, "slug": a.config.slug}
            for a in self.agents
        ]
        output_file = self.session.save(participants_info, consensus)
        return MeetingResult(
            output_file=output_file,
            consensus=consensus,
            history=list(self.history),
        )

    # ── Phases ────────────────────────────────────────────────────────────────

    def _phase1(self, topic: str) -> None:
        self.session.stream_phase("Phase 1: 초기 의견 수집")

        opening = self._call_moderator("announce_opening", topic=topic, history=self.history, skip_delay=True)
        self.session.stream_moderator(opening)
        self._add_moderator(opening)

        instruction = "이 안건에 대한 초기 의견을 밝혀주세요."
        for agent in self.agents:
            response = self._call_agent(agent, topic, self.history, instruction)
            if response:
                self.session.stream_message(agent.config.name, response, agent.config.slug)
                self._add_agent(agent, response, phase=1)

    def _phase2(self, topic: str) -> None:
        self.session.stream_phase("Phase 2: 자유 토론")

        transition = self._call_moderator("announce_phase", phase=2, history=self.history, skip_delay=True)
        self.session.stream_moderator(transition)
        self._add_moderator(transition)

        agent_map = {a.config.slug: a for a in self.agents}
        instruction = "다른 팀원의 의견에 반응하거나 새 논점을 제시하세요."
        last_slug: str | None = None

        for _ in range(self.config.phase2_rounds):
            try:
                slug = self.moderator.select_next_speaker(
                    self.history, exclude=last_slug
                )
            except Exception as e:
                logger.error("select_next_speaker 실패: %s — 건너뜁니다", e)
                continue

            agent = agent_map.get(slug)
            if agent is None:
                logger.warning("선택된 slug %r 가 참여자 목록에 없습니다 — 건너뜁니다", slug)
                continue

            response = self._call_agent(agent, topic, self.history, instruction)
            if response:
                self.session.stream_message(agent.config.name, response, agent.config.slug)
                self._add_agent(agent, response, phase=2)
                last_slug = slug  # only track successful speakers; failed turns don't block re-selection

    def _phase3(self, topic: str) -> str:
        self.session.stream_phase("Phase 3: 최종 입장 및 합의 도출")

        transition = self._call_moderator("announce_phase", phase=3, history=self.history, skip_delay=True)
        self.session.stream_moderator(transition)
        self._add_moderator(transition)

        instruction = (
            "최종 입장을 밝혀주세요: 동의/수정 요청/반대 중 하나와 이유를 말해주세요."
        )
        for agent in self.agents:
            response = self._call_agent(agent, topic, self.history, instruction)
            if response:
                self.session.stream_message(agent.config.name, response, agent.config.slug)
                self._add_agent(agent, response, phase=3)

        consensus = self._call_moderator("draft_consensus", topic=topic, history=self.history)
        self.session.stream_moderator(consensus)
        self._add_moderator(consensus)
        return consensus

    # ── History management ────────────────────────────────────────────────────

    def _add_agent(self, agent: MeetingAgent, content: str, phase: int) -> None:
        self.history.append({
            "role": "assistant",
            "speaker": agent.config.name,
            "slug": agent.config.slug,
            "phase": phase,
            "content": content,
        })

    def _add_moderator(self, content: str) -> None:
        self.history.append({
            "role": "assistant",
            "speaker": "[사회자]",
            "slug": "__moderator__",
            "phase": 0,
            "content": content,
        })

    # ── Error-safe wrappers (plan.md §7) ──────────────────────────────────────

    def _call_agent(
        self,
        agent: MeetingAgent,
        topic: str,
        history: list[dict],
        instruction: str,
        *,
        skip_delay: bool = False,
    ) -> str | None:
        """
        오류 처리:
          - TimeoutError  → stderr 로그 후 스킵 (회의 계속 진행)
          - RuntimeError  → stderr 로그 후 스킵
        rate limit 방지를 위해 호출 전 call_delay 초 대기합니다.
        skip_delay=True 이면 대기를 건너뜁니다 (Phase 첫 호출 등).
        """
        if not skip_delay:
            time.sleep(self.config.call_delay)
        try:
            return agent.respond(topic, history, instruction)
        except TimeoutError:
            logger.error("[%s] 타임아웃 재시도 실패 — 이번 발언을 건너뜁니다", agent.config.slug)
            return None
        except RuntimeError as e:
            logger.error("[%s] claude -p 실패: %s — 건너뜁니다", agent.config.slug, e)
            return None

    def _call_moderator(self, method: str, *, skip_delay: bool = False, **kwargs) -> str:
        """ModeratorAgent 호출. 실패 시 플레이스홀더 문자열 반환."""
        if not skip_delay:
            time.sleep(self.config.call_delay)
        try:
            return getattr(self.moderator, method)(**kwargs)
        except Exception as e:
            logger.error("ModeratorAgent.%s 실패: %s", method, e)
            return f"[사회자 오류: {method}]"
