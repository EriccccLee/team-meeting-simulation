"""simulation/retriever.py 단위 테스트."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.retriever import SlackRetriever


def _make_team_dir(tmp_path: Path, members: dict[str, list[str]]) -> Path:
    """임시 team-skills 디렉토리 생성. members = {slug: [message, ...]}"""
    for slug, messages in members.items():
        member_dir = tmp_path / slug
        member_dir.mkdir()
        data = {"messages": [{"content": m} for m in messages]}
        (member_dir / "slack_messages.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    return tmp_path


class TestSlackRetrieverLoad:
    def test_loads_messages_for_known_slug(self, tmp_path):
        """알려진 slug의 메시지를 로드해야 한다."""
        team_dir = _make_team_dir(tmp_path, {
            "alice": ["RAG 시스템 구축 중입니다", "Neo4j 연동 테스트 완료"]
        })
        retriever = SlackRetriever(team_dir)
        assert "alice" in retriever._indexes

    def test_unknown_slug_returns_empty(self, tmp_path):
        """존재하지 않는 slug는 빈 리스트를 반환해야 한다."""
        team_dir = _make_team_dir(tmp_path, {"alice": ["메시지"]})
        retriever = SlackRetriever(team_dir)
        result = retriever.search("nobody", "RAG")
        assert result == []

    def test_skips_member_without_json(self, tmp_path):
        """slack_messages.json 없는 멤버 디렉토리는 건너뛰어야 한다."""
        (tmp_path / "ghost").mkdir()  # json 파일 없음
        retriever = SlackRetriever(tmp_path)
        assert "ghost" not in retriever._indexes

    def test_skips_empty_messages(self, tmp_path):
        """content가 비어있는 메시지는 인덱싱하지 않아야 한다."""
        team_dir = _make_team_dir(tmp_path, {"alice": ["", "   "]})
        retriever = SlackRetriever(team_dir)
        assert "alice" not in retriever._indexes


class TestSlackRetrieverSearch:
    def test_returns_relevant_message(self, tmp_path):
        """쿼리와 관련된 메시지를 반환해야 한다."""
        team_dir = _make_team_dir(tmp_path, {
            "bob": [
                "RAG 파이프라인 설계 완료했습니다",
                "오늘 점심 뭐 먹을까요",
                "벡터 DB는 Qdrant 쓰면 좋을 것 같아요",
            ]
        })
        retriever = SlackRetriever(team_dir)
        results = retriever.search("bob", "RAG 벡터 DB")
        assert len(results) > 0
        assert any("RAG" in r or "벡터" in r for r in results)

    def test_returns_at_most_top_k(self, tmp_path):
        """top_k 이상 반환하지 않아야 한다."""
        messages = [f"메시지 {i}" for i in range(20)]
        team_dir = _make_team_dir(tmp_path, {"carol": messages})
        retriever = SlackRetriever(team_dir)
        results = retriever.search("carol", "메시지", top_k=3)
        assert len(results) <= 3

    def test_empty_query_returns_empty(self, tmp_path):
        """빈 쿼리는 빈 리스트를 반환해야 한다."""
        team_dir = _make_team_dir(tmp_path, {"alice": ["hello world"]})
        retriever = SlackRetriever(team_dir)
        results = retriever.search("alice", "")
        assert results == []

    def test_no_match_returns_empty(self, tmp_path):
        """전혀 관련 없는 쿼리는 빈 리스트를 반환해야 한다."""
        team_dir = _make_team_dir(tmp_path, {
            "dave": ["오늘 날씨가 맑네요", "점심은 비빔밥"]
        })
        retriever = SlackRetriever(team_dir)
        results = retriever.search("dave", "kubernetes docker ci")
        assert results == []


class TestSlackRetrieverTokenize:
    def test_tokenizes_by_whitespace(self):
        """공백으로 토큰화해야 한다."""
        tokens = SlackRetriever._tokenize("RAG 시스템 구축")
        assert tokens == ["rag", "시스템", "구축"]

    def test_lowercases_english(self):
        """영어를 소문자로 변환해야 한다."""
        tokens = SlackRetriever._tokenize("Neo4j RAG Vector")
        assert tokens == ["neo4j", "rag", "vector"]

    def test_empty_string_returns_empty_list(self):
        """빈 문자열은 빈 리스트를 반환해야 한다."""
        assert SlackRetriever._tokenize("") == []
