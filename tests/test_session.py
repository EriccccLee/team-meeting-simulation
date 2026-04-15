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
