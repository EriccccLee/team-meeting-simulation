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
    with patch("web.routes.slack_extraction._run_extraction"):
        from fastapi.testclient import TestClient
        from web.app import app
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/slack/extract",
            json=[{"user_id": "UA001", "slug": "honggildong", "display_name": "홍길동"}],
        )

    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert len(data["session_id"]) == 36  # UUID4


def test_extract_empty_list_returns_400():
    from fastapi.testclient import TestClient
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post("/api/slack/extract", json=[])
    assert res.status_code == 400
