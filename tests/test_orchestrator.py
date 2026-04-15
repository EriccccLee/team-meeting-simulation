"""simulation/agents.py — ModeratorAgent 단위 테스트."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.agents import AgentConfig, MeetingAgent, ModeratorAgent
from simulation.orchestrator import MeetingOrchestrator, OrchestratorConfig


def _mock_client(return_value: str) -> MagicMock:
    client = MagicMock()
    client.call.return_value = return_value
    return client


def test_select_next_speaker_excludes_last_speaker():
    """exclude로 지정한 slug는 선택되지 않아야 한다."""
    slugs = ["leecy", "jasonjoe", "philgineer"]
    # LLM이 항상 "leecy" 를 반환하도록 mock
    client = _mock_client("leecy")
    mod = ModeratorAgent(client, slugs)

    # leecy를 exclude하면 leecy가 아닌 다른 사람이 선택되어야 함
    result = mod.select_next_speaker([], exclude="leecy")
    assert result != "leecy"
    assert result in slugs


def test_select_next_speaker_no_exclude():
    """exclude 없으면 LLM 응답 slug를 그대로 반환."""
    slugs = ["leecy", "jasonjoe"]
    client = _mock_client("jasonjoe")
    mod = ModeratorAgent(client, slugs)
    result = mod.select_next_speaker([], exclude=None)
    assert result == "jasonjoe"


def test_select_next_speaker_fallback_when_all_excluded():
    """exclude가 전체 목록과 겹치면 랜덤 선택(exclude 제외) fallback."""
    slugs = ["leecy"]
    client = _mock_client("leecy")
    mod = ModeratorAgent(client, slugs)
    # 유일한 참여자를 exclude 해도 함수는 오류 없이 반환해야 함
    result = mod.select_next_speaker([], exclude="leecy")
    # 선택지가 없으면 exclude 무시하고 전체에서 선택
    assert result in slugs


def test_select_next_speaker_excludes_in_two_person_team():
    """2인 팀에서 exclude가 작동해야 한다."""
    slugs = ["alice", "bob"]
    # LLM이 항상 "alice" 를 반환하도록 mock — alice가 exclude되어 있으므로 bob이 선택되어야 함
    client = _mock_client("alice")
    mod = ModeratorAgent(client, slugs)
    result = mod.select_next_speaker([], exclude="alice")
    assert result == "bob"


# ── _make_orchestrator helper ──────────────────────────────────────────────────

def _make_orchestrator(delay: float = 5.0) -> MeetingOrchestrator:
    config = AgentConfig(name="테스터", slug="tester", skill_md="# skill", persona_md="# persona")
    agent = MeetingAgent(config, _mock_client("response"))
    mod_client = _mock_client("moderator response")
    moderator = ModeratorAgent(mod_client, participant_slugs=["tester"])
    session = MagicMock()
    session.stream_phase = MagicMock()
    session.stream_moderator = MagicMock()
    session.stream_message = MagicMock()
    orch = MeetingOrchestrator(
        agents=[agent],
        moderator=moderator,
        session=session,
        config=OrchestratorConfig(call_delay=delay, phase2_rounds=0),
    )
    return orch


# ── skip_delay tests ───────────────────────────────────────────────────────────

def test_call_agent_skip_delay_true_does_not_sleep():
    orch = _make_orchestrator(delay=5.0)
    agent = orch.agents[0]
    with patch("time.sleep") as mock_sleep, \
         patch.object(agent, "respond", return_value="response"):
        orch._call_agent(agent, "topic", [], "instruction", skip_delay=True)
    mock_sleep.assert_not_called()


def test_call_agent_skip_delay_false_sleeps():
    orch = _make_orchestrator(delay=5.0)
    agent = orch.agents[0]
    with patch("time.sleep") as mock_sleep, \
         patch.object(agent, "respond", return_value="response"):
        orch._call_agent(agent, "topic", [], "instruction", skip_delay=False)
    mock_sleep.assert_called_once_with(5.0)


def test_call_moderator_skip_delay_true_does_not_sleep():
    orch = _make_orchestrator(delay=5.0)
    with patch("time.sleep") as mock_sleep, \
         patch.object(orch.moderator, "announce_opening", return_value="opening"):
        orch._call_moderator("announce_opening", topic="t", history=[], skip_delay=True)
    mock_sleep.assert_not_called()


def test_phase1_calls_all_agents_in_order():
    """Phase 1에서 모든 에이전트가 호출되고 결과가 올바른 순서로 스트리밍된다."""
    config_a = AgentConfig(name="Alice", slug="alice", skill_md="# a", persona_md="# p")
    config_b = AgentConfig(name="Bob", slug="bob", skill_md="# b", persona_md="# p")
    agent_a = MeetingAgent(config_a, MagicMock())
    agent_b = MeetingAgent(config_b, MagicMock())
    mod_config = MagicMock()
    moderator = ModeratorAgent(MagicMock(), participant_slugs=["alice", "bob"])
    session = MagicMock()
    orch = MeetingOrchestrator(
        agents=[agent_a, agent_b],
        moderator=moderator,
        session=session,
        config=OrchestratorConfig(call_delay=0, phase2_rounds=0),
    )
    with patch.object(moderator, "announce_opening", return_value="opening"), \
         patch.object(agent_a, "respond", return_value="alice says"), \
         patch.object(agent_b, "respond", return_value="bob says"), \
         patch("time.sleep"):
        orch._phase1("topic")

    # stream_message: alice → bob 순서 보장
    calls = [c.args for c in session.stream_message.call_args_list]
    assert len(calls) == 2
    assert calls[0][2] == "alice"
    assert calls[1][2] == "bob"
