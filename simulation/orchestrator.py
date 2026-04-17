"""
MeetingOrchestrator
───────────────────
3단계(Phase 1→2→3) 회의 흐름을 순서대로 실행하는 컨트롤러.

plan.md §4-4 참조.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .agents import MeetingAgent, ModeratorAgent
from .retriever import SlackRetriever
from .session import MeetingSession

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    phase2_rounds: int = 3          # Phase 2 총 발언 횟수
    max_tokens_per_turn: int = 500  # system prompt 지시용 (API 강제 아님)
    call_delay: float = 3.0         # 연속 claude 호출 간 대기 시간 (초). rate limit 방지.


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
        cancel_check: Callable[[], bool] | None = None,
        retriever: SlackRetriever | None = None,
    ) -> None:
        self.agents = agents
        self.moderator = moderator
        self.session = session
        self.config = config or OrchestratorConfig()
        self.history: list[dict] = []
        self._cancel_check = cancel_check or (lambda: False)
        self.retriever = retriever
        self._file_contents: dict[str, str] = {}  # run()에서 저장

    def run(self, topic: str, file_contents: dict[str, str]) -> MeetingResult:
        # file_contents를 저장 (Phase 진행 중 필요할 때 사용)
        self._file_contents = file_contents

        # build_system_prompt는 Phase 1에서 stance 결정 후에 호출합니다
        self._phase1(topic)
        if self._cancel_check():
            return MeetingResult(output_file=Path(os.devnull), consensus="", history=list(self.history))
        self._phase2(topic)
        if self._cancel_check():
            return MeetingResult(output_file=Path(os.devnull), consensus="", history=list(self.history))
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

        if not self.agents:
            return

        # 각 에이전트의 입장을 병렬로 결정합니다 (성능 최적화)
        logger.info("각 에이전트의 입장 결정 중... (병렬 처리)")

        # Step 1: 모든 에이전트의 stance를 병렬로 결정
        with ThreadPoolExecutor(max_workers=min(5, len(self.agents))) as executor:
            futures = {}
            for agent in self.agents:
                if self._cancel_check():
                    logger.info("시뮬레이션 취소 요청 — Phase 1 조기 종료")
                    return

                # BM25 검색 및 stance 결정을 병렬 작업으로 제출
                future = executor.submit(
                    self._determine_stance_for_agent, agent, topic
                )
                futures[agent.config.slug] = future

            # 모든 stance 결정이 완료될 때까지 대기
            for agent in self.agents:
                if self._cancel_check():
                    return
                future = futures[agent.config.slug]
                try:
                    future.result(timeout=self.config.call_delay * 3)  # 타임아웃: 24초
                except Exception as e:
                    logger.error("[%s] Stance 결정 실패: %s", agent.config.slug, e)

        # Step 2: Stance 결정 후 각 에이전트의 system prompt 구성
        logger.info("System prompt 구성 중...")
        for agent in self.agents:
            if self._cancel_check():
                logger.info("시뮬레이션 취소 요청 — Phase 1 조기 종료")
                return
            agent.build_system_prompt(topic, self._file_contents)

        instruction = (
            "이 안건에 대한 초기 의견을 밝혀주세요. "
            "당신의 실제 입장을 명확히 표현하세요."
        )
        # 순차 실행: 각 에이전트 응답이 완료되는 즉시 stream_message 호출
        # (병렬 실행 시 전원 완료 후 일괄 emit되어 스트리밍 UX가 깨짐)
        for i, agent in enumerate(self.agents):
            if self._cancel_check():
                logger.info("시뮬레이션 취소 요청 — Phase 1 조기 종료")
                return
            response = self._call_agent(agent, topic, self.history, instruction, skip_delay=(i == 0))
            if response:
                self.session.stream_message(agent.config.name, response, agent.config.slug)
                self._add_agent(agent, response, phase=1)

    def _phase2(self, topic: str) -> None:
        if len(self.agents) <= 1:
            # 참여자가 1명이면 자유 토론을 건너뜁니다 (화자 순환 불가)
            self.session.stream_phase("Phase 2: 자유 토론 (참여자 1명 — 건너뜀)")
            return

        self.session.stream_phase("Phase 2: 자유 토론")

        transition = self._call_moderator("announce_phase", phase=2, history=self.history, skip_delay=True)
        self.session.stream_moderator(transition)
        self._add_moderator(transition)

        agent_map = {a.config.slug: a for a in self.agents}
        instruction = (
            "지금까지의 의견을 바탕으로 당신의 입장을 명확히 하세요. "
            "동의한다면 구체적인 실행 방안을 제안하고, "
            "우려가 있다면 그 근거와 함께 반대 의견을 내세요. "
            "과거 팀 결정이나 당신의 경험에 비추어 판단하세요."
        )
        last_slug: str | None = None
        first_agent_call = True

        for _ in range(self.config.phase2_rounds):
            if self._cancel_check():
                logger.info("시뮬레이션 취소 요청 — Phase 2 조기 종료")
                return
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

            if self._cancel_check():
                logger.info("시뮬레이션 취소 요청 — Phase 2 에이전트 호출 전 조기 종료")
                return

            response = self._call_agent(agent, topic, self.history, instruction, skip_delay=first_agent_call)
            first_agent_call = False
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
        for i, agent in enumerate(self.agents):
            if self._cancel_check():
                logger.info("시뮬레이션 취소 요청 — Phase 3 조기 종료")
                return ""
            response = self._call_agent(agent, topic, self.history, instruction, skip_delay=(i == 0))
            if response:
                self.session.stream_message(agent.config.name, response, agent.config.slug)
                self._add_agent(agent, response, phase=3)

        consensus = self._call_moderator("draft_consensus", topic=topic, history=self.history)
        self.session.stream_moderator(consensus)
        self._add_moderator(consensus)
        return consensus

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _determine_stance_for_agent(self, agent: MeetingAgent, topic: str) -> None:
        """
        병렬 실행용: 에이전트의 BM25 검색 및 stance 결정을 수행합니다.
        """
        retrieved: list[str] = []
        if self.retriever is not None:
            try:
                retrieved = self.retriever.search(agent.config.slug, topic)
            except Exception as e:
                logger.warning("[%s] BM25 검색 실패: %s", agent.config.slug, e)

        agent.determine_stance(topic, retrieved)

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

        retrieved: list[str] = []
        if self.retriever is not None:
            recent_content = " ".join(
                msg["content"][:80]
                for msg in history[-3:]
                if msg.get("slug") not in ("__moderator__", "__memory__")
            )
            query = f"{topic} {recent_content}".strip()
            retrieved = self.retriever.search(agent.config.slug, query)

        def _on_tool_use(tool_info: dict) -> None:
            self.session.stream_tool_use(
                tool_name=tool_info.get("name", "Unknown"),
                tool_input=tool_info.get("input", {}),
                slug=agent.config.slug,
                speaker=agent.config.name,
                failed=tool_info.get("failed", False),
            )

        try:
            return agent.respond(
                topic, history, instruction,
                on_tool_use=_on_tool_use,
                retrieved_messages=retrieved,
            )
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
