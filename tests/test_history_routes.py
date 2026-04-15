"""web/routes/history.py 라우트 테스트."""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _client():
    from fastapi.testclient import TestClient
    from web.app import app
    return TestClient(app, raise_server_exceptions=False)


def test_get_history_invalid_session_id_returns_400():
    """비-UUID 문자열은 400을 반환해야 한다.

    {session_id} 단순 파라미터는 슬래시를 포함하는 경로를 받지 않으므로
    슬래시 없는 잘못된 ID를 사용한다 — 멀티 세그먼트 경로는 어차피 404로 라우팅된다.
    """
    res = _client().get("/api/history/invalid-id-not-a-uuid")
    assert res.status_code == 400


def test_delete_history_invalid_session_id_returns_400():
    res = _client().delete("/api/history/invalid-id-not-a-uuid")
    assert res.status_code == 400


def test_get_history_not_found_returns_404():
    """유효한 UUID이지만 존재하지 않는 session은 404."""
    res = _client().get("/api/history/00000000-0000-4000-8000-000000000000")
    assert res.status_code == 404


def test_delete_history_not_found_returns_404():
    res = _client().delete("/api/history/00000000-0000-4000-8000-000000000000")
    assert res.status_code == 404


def test_get_history_uppercase_uuid_returns_400():
    """UUID regex는 소문자만 허용 — 대문자는 400."""
    res = _client().get("/api/history/00000000-0000-4000-8000-AABBCCDDEEFF")
    assert res.status_code == 400
