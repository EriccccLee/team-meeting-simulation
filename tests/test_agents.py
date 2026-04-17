"""simulation/agents.py 단위 테스트."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.agents import AgentConfig, MeetingAgent, ModeratorAgent


# ── MeetingAgent ────────────────────────────────────────────────────────────


class TestMeetingAgentBuildSystemPrompt:
    """MeetingAgent.build_system_prompt 테스트."""

    def _make_agent(self) -> MeetingAgent:
        config = AgentConfig(
            slug="testuser",
            name="테스트유저",
            skill_md="# 테스트 스킬\n\n백엔드 엔지니어입니다.",
            persona_md="# 테스트 페르소나\n\n차분한 성격입니다.",
        )
        mock_client = MagicMock()
        return MeetingAgent(config, mock_client)

    def test_system_prompt_contains_skill_md(self):
        """system prompt에 SKILL.md 내용이 포함되어야 한다."""
        agent = self._make_agent()
        agent.build_system_prompt("AI 도입 회의", {})
        assert "테스트 스킬" in agent._system_prompt
        assert "백엔드 엔지니어입니다" in agent._system_prompt

    def test_system_prompt_contains_topic(self):
        """system prompt에 회의 안건이 포함되어야 한다."""
        agent = self._make_agent()
        agent.build_system_prompt("AI 도입 회의", {})
        assert "AI 도입 회의" in agent._system_prompt

    def test_system_prompt_contains_file_contents(self):
        """첨부 파일이 있으면 system prompt에 포함되어야 한다."""
        agent = self._make_agent()
        file_contents = {
            "report.md": "# 분기 보고서\n\n매출이 증가했습니다.",
            "data.csv": "name,value\nA,100",
        }
        agent.build_system_prompt("분기 리뷰", file_contents)
        assert "report.md" in agent._system_prompt
        assert "분기 보고서" in agent._system_prompt
        assert "data.csv" in agent._system_prompt

    def test_system_prompt_no_files_section_when_empty(self):
        """첨부 파일이 없으면 첨부 파일 섹션이 없어야 한다."""
        agent = self._make_agent()
        agent.build_system_prompt("회의 안건", {})
        assert "## 첨부 파일" not in agent._system_prompt

    def test_system_prompt_contains_meeting_guidelines(self):
        """system prompt에 회의 참여 지침이 포함되어야 한다."""
        agent = self._make_agent()
        agent.build_system_prompt("안건", {})
        assert "회의 참여 지침" in agent._system_prompt
        assert "간결하게 발언하세요" in agent._system_prompt


# ── Backward-compatible respond() tests (kept from prior version) ────────────


def _make_agent() -> MeetingAgent:
    config = AgentConfig(slug="test", name="테스터", skill_md="## SKILL", persona_md="")
    client = MagicMock()
    client.call.return_value = "응답"
    return MeetingAgent(config, client)


def test_respond_with_file_contents_builds_correct_prompt():
    """respond()에 file_contents 전달 시 시스템 프롬프트에 포함되어야 한다."""
    agent = _make_agent()
    file_contents = {"readme.md": "# 프로젝트 설명"}
    agent.respond("안건", [], "발언하세요", file_contents=file_contents)
    assert agent._system_prompt is not None
    assert "readme.md" in agent._system_prompt


def test_respond_without_file_contents_uses_empty_dict():
    """respond()에 file_contents 없으면 빈 dict로 동작해야 한다."""
    agent = _make_agent()
    agent.respond("안건", [], "발언하세요")
    assert agent._system_prompt is not None
    assert "첨부 파일" not in agent._system_prompt


# ── ModeratorAgent ──────────────────────────────────────────────────────────


class TestModeratorAgentSelectNextSpeaker:
    """ModeratorAgent.select_next_speaker 테스트."""

    def _make_moderator(self, slugs: list[str]) -> ModeratorAgent:
        mock_client = MagicMock()
        return ModeratorAgent(mock_client, slugs)

    def test_returns_valid_slug(self):
        """LLM이 유효한 slug를 반환하면 그대로 사용한다."""
        mod = self._make_moderator(["leecy", "jasonjoe", "philgineer"])
        mod.model_client.call.return_value = "jasonjoe"

        result = mod.select_next_speaker([], exclude=None)
        assert result == "jasonjoe"

    def test_excludes_specified_slug(self):
        """exclude 파라미터로 지정한 slug는 선택지에서 제외된다."""
        mod = self._make_moderator(["leecy", "jasonjoe"])
        mod.model_client.call.return_value = "leecy"

        result = mod.select_next_speaker([], exclude="jasonjoe")
        assert result == "leecy"

    def test_exclude_all_falls_back_to_full_list(self):
        """모든 참여자가 exclude되면 전체 목록으로 fallback한다."""
        mod = self._make_moderator(["leecy"])
        mod.model_client.call.return_value = "leecy"

        result = mod.select_next_speaker([], exclude="leecy")
        assert result == "leecy"

    def test_unknown_slug_falls_back_to_random(self):
        """LLM이 알 수 없는 slug를 반환하면 랜덤 fallback한다."""
        mod = self._make_moderator(["leecy", "jasonjoe"])
        mod.model_client.call.return_value = "unknown_person"

        result = mod.select_next_speaker([], exclude=None)
        assert result in ["leecy", "jasonjoe"]


class TestModeratorAgentAnnounceOpening:
    """ModeratorAgent.announce_opening 테스트."""

    def test_calls_model_with_topic(self):
        """announce_opening이 model_client.call을 호출하고 topic을 포함한다."""
        mock_client = MagicMock()
        mock_client.call.return_value = "회의를 시작하겠습니다."
        mod = ModeratorAgent(mock_client, ["leecy", "jasonjoe"])

        result = mod.announce_opening("AI 전환 전략", [])

        assert result == "회의를 시작하겠습니다."
        assert mock_client.call.called
        call_args = str(mock_client.call.call_args)
        assert "AI 전환 전략" in call_args

    def test_returns_model_output(self):
        """announce_opening은 model_client의 출력을 그대로 반환한다."""
        mock_client = MagicMock()
        expected = "오늘 안건은 분기 리뷰입니다."
        mock_client.call.return_value = expected
        mod = ModeratorAgent(mock_client, ["leecy"])

        result = mod.announce_opening("분기 리뷰", [])
        assert result == expected


def test_respond_with_retrieved_messages_injects_memory():
    """retrieved_messages가 있으면 __memory__ 메시지로 삽입되어야 한다."""
    agent = _make_agent()
    agent.respond("안건", [], "발언하세요", retrieved_messages=["과거 발언 A", "과거 발언 B"])
    call_args = agent.model_client.call.call_args
    messages_arg = call_args[0][1]  # positional: system_prompt, messages
    memory_msgs = [m for m in messages_arg if m.get("slug") == "__memory__"]
    assert len(memory_msgs) == 1
    assert "과거 발언 A" in memory_msgs[0]["content"]
    assert "과거 발언 B" in memory_msgs[0]["content"]


def test_respond_without_retrieved_messages_no_memory_injection():
    """retrieved_messages가 없으면 __memory__ 메시지가 삽입되지 않아야 한다."""
    agent = _make_agent()
    agent.respond("안건", [], "발언하세요")
    call_args = agent.model_client.call.call_args
    messages_arg = call_args[0][1]
    memory_msgs = [m for m in messages_arg if m.get("slug") == "__memory__"]
    assert len(memory_msgs) == 0
