"""simulation/agents.py 단위 테스트."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.agents import MeetingAgent, AgentConfig


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
