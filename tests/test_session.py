"""simulation/session.py 단위 테스트."""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.session import MeetingSession, _make_slug


# ── 기존 회귀 테스트 (보존) ────────────────────────────────────────────────────

def test_consensus_blank_lines_use_bare_blockquote(tmp_path):
    """빈 줄은 '> ' (공백 포함)가 아니라 '>' 만 되어야 한다 — save()를 실제로 호출해 검증."""
    sess = MeetingSession(topic="test 안건", participants=[], output_dir=tmp_path)
    consensus = "첫 줄\n\n세 번째 줄"
    filepath = sess.save(participants_info=[], consensus=consensus)
    content = filepath.read_text(encoding="utf-8")
    blockquote_lines = [ln for ln in content.splitlines() if ln.startswith(">")]
    blank_blockquotes = [ln for ln in blockquote_lines if ln == ">"]
    assert blank_blockquotes, "빈 줄은 '>' 만이어야 한다"
    assert not any(ln == "> " for ln in blockquote_lines), "trailing space 있으면 안 된다"


def test_make_slug_korean_topic():
    """한글 topic은 ASCII 안전 slug로 변환되어야 한다."""
    result = _make_slug("RAG 아키텍처 선택")
    assert all(c.isascii() for c in result), f"Non-ASCII chars in slug: {result}"
    assert result, "slug should not be empty"


def test_make_slug_english_topic():
    """영어 topic은 소문자 ASCII slug로 변환."""
    result = _make_slug("Cloud Architecture Review")
    assert result == "cloud-architecture-review"


def test_make_slug_empty():
    """빈 문자열은 'meeting' 기본값."""
    assert _make_slug("") == "meeting"
    assert _make_slug("!!!") == "meeting"


# ── TestMakeSlug ───────────────────────────────────────────────────────────────

class TestMakeSlug:
    def test_ascii_text(self):
        assert _make_slug("Hello World") == "hello-world"

    def test_truncates_at_30(self):
        long = "a" * 50
        assert len(_make_slug(long)) <= 30

    def test_empty_fallback(self):
        assert _make_slug("") == "meeting"

    def test_special_characters(self):
        result = _make_slug("AI/ML Strategy & Planning!")
        assert "/" not in result
        assert "&" not in result
        assert "!" not in result


# ── TestMeetingSessionSave ────────────────────────────────────────────────────

class TestMeetingSessionSave:
    def test_creates_markdown_file(self, tmp_path):
        session = MeetingSession(
            topic="AI 도입 전략",
            participants=["leecy", "jasonjoe"],
            output_dir=str(tmp_path),
        )
        session.stream_phase("Phase 1: 초기 의견 수집")
        session.stream_message("이창영", "AI 도입이 필요합니다.", slug="leecy")
        session.stream_moderator("좋은 의견입니다.")

        filepath = session.save(
            participants_info=[
                {"name": "이창영", "slug": "leecy"},
                {"name": "조성훈", "slug": "jasonjoe"},
            ],
            consensus="## 합의 결과\n\nAI 도입을 진행합니다.",
        )

        assert filepath.exists()
        assert filepath.suffix == ".md"

    def test_markdown_contains_header(self, tmp_path):
        session = MeetingSession(
            topic="분기 리뷰",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )

        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의안입니다.",
        )

        content = filepath.read_text(encoding="utf-8")
        assert "# 팀 미팅 시뮬레이션" in content
        assert "분기 리뷰" in content
        assert "이창영" in content

    def test_markdown_contains_phase_sections(self, tmp_path):
        session = MeetingSession(
            topic="테스트",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )
        session.stream_phase("Phase 1: 초기 의견 수집")
        session.stream_phase("Phase 2: 자유 토론")

        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의안",
        )

        content = filepath.read_text(encoding="utf-8")
        assert "## Phase 1: 초기 의견 수집" in content
        assert "## Phase 2: 자유 토론" in content

    def test_markdown_contains_messages(self, tmp_path):
        session = MeetingSession(
            topic="테스트",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )
        session.stream_message("이창영", "테스트 발언입니다.", slug="leecy")

        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의안",
        )

        content = filepath.read_text(encoding="utf-8")
        assert "### 이창영 (leecy)" in content
        assert "테스트 발언입니다." in content

    def test_markdown_contains_consensus(self, tmp_path):
        session = MeetingSession(
            topic="테스트",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )

        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            # consensus lines are rendered as blockquotes: "> text"
            consensus="AI 도입을 진행합니다.\n구체적 일정은 추후 결정합니다.",
        )

        content = filepath.read_text(encoding="utf-8")
        assert "## 합의안" in content
        # save() wraps each line with "> " prefix; the text still appears in the file
        assert "AI 도입을 진행합니다." in content

    def test_filename_contains_topic(self, tmp_path):
        session = MeetingSession(
            topic="Weekly Sync",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )

        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의안",
        )

        assert "weekly-sync" in filepath.name
        assert filepath.name.endswith(".md")

    def test_emit_callback_called(self, tmp_path):
        events = []
        session = MeetingSession(
            topic="테스트",
            participants=["leecy"],
            output_dir=str(tmp_path),
            emit=lambda e: events.append(e),
        )

        session.stream_phase("Phase 1")
        session.stream_message("이창영", "발언", slug="leecy")
        session.stream_moderator("사회자 발언")

        assert len(events) == 3
        assert events[0] == {"type": "phase", "label": "Phase 1"}
        assert events[1]["type"] == "message"
        assert events[1]["speaker"] == "이창영"
        assert events[1]["slug"] == "leecy"
        assert events[2]["type"] == "moderator"
        assert events[2]["content"] == "사회자 발언"

    def test_save_returns_path(self, tmp_path):
        session = MeetingSession(
            topic="Return Type Check",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )
        result = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의안",
        )
        assert isinstance(result, Path)

    def test_consensus_rendered_as_blockquote(self, tmp_path):
        """save()는 합의안 각 줄을 '> ' 블록인용으로 감싼다."""
        session = MeetingSession(
            topic="블록인용 테스트",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )
        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의 내용입니다.",
        )
        content = filepath.read_text(encoding="utf-8")
        assert "> 합의 내용입니다." in content

    def test_moderator_message_in_markdown(self, tmp_path):
        """stream_moderator() 발언이 마크다운에 사회자 표시와 함께 저장된다."""
        session = MeetingSession(
            topic="사회자 테스트",
            participants=["leecy"],
            output_dir=str(tmp_path),
        )
        session.stream_moderator("다음 안건으로 넘어갑니다.")

        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의안",
        )
        content = filepath.read_text(encoding="utf-8")
        assert "사회자" in content
        assert "다음 안건으로 넘어갑니다." in content

    def test_emit_not_called_when_none(self, tmp_path):
        """emit=None 이면 stream_* 호출 시 오류 없이 동작한다."""
        session = MeetingSession(
            topic="emit None 테스트",
            participants=["leecy"],
            output_dir=str(tmp_path),
            emit=None,
        )
        # Should not raise
        session.stream_phase("Phase 1")
        session.stream_message("이창영", "발언")
        session.stream_moderator("사회자")
        filepath = session.save(
            participants_info=[{"name": "이창영", "slug": "leecy"}],
            consensus="합의안",
        )
        assert filepath.exists()
