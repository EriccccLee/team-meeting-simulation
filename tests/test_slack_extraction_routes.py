"""web/routes/slack_extraction.py 라우트 테스트."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def set_slack_env(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_CHANNELS", "C001,C002")


def test_discover_missing_token(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    from fastapi.testclient import TestClient
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/slack/discover")
    assert res.status_code == 400
    assert "SLACK_BOT_TOKEN" in res.json()["detail"]


def test_discover_missing_channels(monkeypatch):
    monkeypatch.delenv("SLACK_CHANNELS", raising=False)
    from fastapi.testclient import TestClient
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/slack/discover")
    assert res.status_code == 400
    assert "SLACK_CHANNELS" in res.json()["detail"]


def test_discover_returns_user_list():
    mock_users = [
        {
            "user_id": "UA001",
            "display_name": "홍길동",
            "message_count": 5,
            "suggested_slug": "honggildong",
        }
    ]
    with patch("web.routes.slack_extraction.discover_users", return_value=mock_users):
        from fastapi.testclient import TestClient
        from web.app import app
        client = TestClient(app, raise_server_exceptions=False)
        res = client.get("/api/slack/discover")

    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["user_id"] == "UA001"


def test_extract_returns_session_id():
    """올바른 형식으로 요청 시 session_id 반환."""
    with patch("web.routes.slack_extraction._run_extraction"):
        from fastapi.testclient import TestClient
        from web.app import app
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/slack/extract",
            json={
                "members": [{"user_id": "UA001", "slug": "honggildong", "display_name": "홍길동"}],
                "max_collect": 2000,
                "max_messages": 300,
            },
        )
    assert res.status_code == 200
    assert "session_id" in res.json()
    assert len(res.json()["session_id"]) == 36


def test_extract_empty_members_returns_400():
    """members가 빈 리스트이면 400을 반환해야 한다."""
    from fastapi.testclient import TestClient
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post("/api/slack/extract", json={"members": [], "max_collect": 2000, "max_messages": 300})
    assert res.status_code == 400


def test_stream_invalid_session_id_returns_400():
    """path traversal 시도는 400을 반환해야 한다."""
    from fastapi.testclient import TestClient
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/slack/stream/invalid-id-not-a-uuid")
    assert res.status_code == 400


def test_extract_invalid_body_returns_422():
    """리스트를 직접 전송하면 422."""
    from fastapi.testclient import TestClient
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post("/api/slack/extract", json=[{"user_id": "UA001"}])
    assert res.status_code == 422


def test_extract_missing_user_id_returns_422():
    """members 항목에 user_id가 없으면 422."""
    from fastapi.testclient import TestClient
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post(
        "/api/slack/extract",
        json={
            "members": [{"slug": "test", "display_name": "Test"}],
            "max_collect": 2000,
            "max_messages": 300,
        },
    )
    assert res.status_code == 422


def test_extract_slug_sanitized():
    """slug에 특수문자가 포함되면 sanitize된 값으로 저장된다."""
    from web.routes.slack_extraction import ExtractMember
    m = ExtractMember(user_id="UA001", slug="Test-User.123", display_name="Test")
    # re.sub(r"[^a-z0-9_]", "", v.lower()) 적용
    assert m.slug == "testuser123"


def test_extract_member_role_coerces_invalid_to_general():
    from web.routes.slack_extraction import ExtractMember
    m = ExtractMember(user_id="UA001", slug="test", display_name="Test", role="engineer")
    assert m.role == "general"


def test_extract_member_accepts_all_valid_roles():
    from web.routes.slack_extraction import ExtractMember
    for valid_role in ("backend", "frontend", "ml", "pm", "data", "general"):
        m = ExtractMember(user_id="UA001", slug=f"test{valid_role}", display_name="Test", role=valid_role)
        assert m.role == valid_role


def test_extract_member_model_dump_includes_role_and_impression():
    from web.routes.slack_extraction import ExtractMember
    m = ExtractMember(user_id="UA001", slug="test", display_name="Test", role="ml", impression="신중함")
    d = m.model_dump()
    assert d["role"] == "ml"
    assert d["impression"] == "신중함"
