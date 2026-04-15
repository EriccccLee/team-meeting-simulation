"""simulation/model_client.py 단위 테스트."""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.model_client import decode_bytes


def test_decode_bytes_utf8():
    assert decode_bytes("안녕".encode("utf-8")) == "안녕"


def test_decode_bytes_cp949():
    assert decode_bytes("안녕".encode("cp949")) == "안녕"


def test_decode_bytes_none():
    assert decode_bytes(None) == ""


def test_decode_bytes_empty():
    assert decode_bytes(b"") == ""
