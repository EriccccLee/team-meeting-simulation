"""simulation/loader.py 단위 테스트."""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest


def test_load_agent_config_missing_skill_raises():
    """존재하지 않는 slug는 FileNotFoundError."""
    from simulation.loader import load_agent_config
    with pytest.raises(FileNotFoundError):
        load_agent_config("__nonexistent_slug__")


def test_load_file_contents_missing_file_returns_empty():
    """존재하지 않는 파일은 빈 dict 반환."""
    from simulation.loader import load_file_contents
    result = load_file_contents(["/nonexistent/file.txt"])
    assert result == {}
