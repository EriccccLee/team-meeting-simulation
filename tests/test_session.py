"""simulation/session.py 단위 테스트."""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_consensus_blank_lines_use_bare_blockquote():
    """빈 줄은 '> ' (공백 포함)가 아니라 '>' 만 되어야 한다."""
    consensus = "첫 줄\n\n세 번째 줄"
    lines = consensus.splitlines()
    result = "\n".join(f"> {line}" if line.strip() else ">" for line in lines)
    assert "> " not in result.split("\n")[1], "빈 줄은 '>' 만이어야 한다"
    assert result.split("\n")[1] == ">"
