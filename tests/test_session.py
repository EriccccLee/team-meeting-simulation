"""simulation/session.py 단위 테스트."""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_consensus_blank_lines_use_bare_blockquote(tmp_path):
    """빈 줄은 '> ' (공백 포함)가 아니라 '>' 만 되어야 한다 — save()를 실제로 호출해 검증."""
    from simulation.session import MeetingSession
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
    from simulation.session import _make_slug
    result = _make_slug("RAG 아키텍처 선택")
    assert all(c.isascii() for c in result), f"Non-ASCII chars in slug: {result}"
    assert result, "slug should not be empty"


def test_make_slug_english_topic():
    """영어 topic은 소문자 ASCII slug로 변환."""
    from simulation.session import _make_slug
    result = _make_slug("Cloud Architecture Review")
    assert result == "cloud-architecture-review"


def test_make_slug_empty():
    """빈 문자열은 'meeting' 기본값."""
    from simulation.session import _make_slug
    assert _make_slug("") == "meeting"
    assert _make_slug("!!!") == "meeting"
