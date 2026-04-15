"""simulation/agents.py — ModeratorAgent 단위 테스트."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.agents import ModeratorAgent


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
