"""simulation/slack_collector.py 단위 테스트"""
import pytest
from simulation.slack_collector import generate_slug, _is_noise


# ── generate_slug ─────────────────────────────────────────────────────────────

def test_generate_slug_english_spaces():
    assert generate_slug("John Kim") == "johnkim"


def test_generate_slug_english_dots():
    assert generate_slug("john.kim") == "johnkim"


def test_generate_slug_korean():
    result = generate_slug("이창영")
    # unidecode 변환 결과 — 영소문자+숫자만 남아야 함
    assert result.isalnum()
    assert result == result.lower()
    assert len(result) > 0


def test_generate_slug_mixed():
    result = generate_slug("홍 Gil-dong")
    assert result.isalnum()
    assert result == result.lower()


def test_generate_slug_fallback_empty():
    # 변환 후 알파뉴메릭이 없으면 "member" 반환
    assert generate_slug("!!!") == "member"
    assert generate_slug("   ") == "member"


# ── _is_noise ─────────────────────────────────────────────────────────────────

def test_is_noise_empty():
    assert _is_noise("") is True
    assert _is_noise("   ") is True


def test_is_noise_pure_emoji():
    assert _is_noise("👍") is True
    assert _is_noise("😊😊😊") is True
    assert _is_noise("🎉🎊") is True


def test_is_noise_bare_mention_only():
    assert _is_noise("<@U012AB3CD>") is True
    assert _is_noise("<@U012AB3CD> <@U999XYZ>") is True


def test_is_noise_mention_with_text():
    # 멘션 + 실질 텍스트가 있으면 노이즈가 아님
    assert _is_noise("<@U012AB3CD> 확인했습니다") is False


def test_is_noise_too_short():
    assert _is_noise("네") is True   # 2자
    assert _is_noise("ok") is True   # 2자


def test_is_noise_normal_message():
    assert _is_noise("오늘 배포 일정 확인했어요") is False
    assert _is_noise("내일 오후로 확정입니다") is False


from unittest.mock import MagicMock, patch
from simulation.slack_collector import discover_users


def _make_mock_client(messages_by_channel, user_profile):
    """conversations_history + users_info 를 모킹한 Slack WebClient."""
    mock = MagicMock()

    def conversations_history(channel, cursor=None, limit=200):
        msgs = messages_by_channel.get(channel, [])
        return {"messages": msgs, "response_metadata": {}}

    mock.conversations_history.side_effect = conversations_history
    mock.users_info.return_value = {"user": user_profile}
    return mock


def test_discover_users_filters_min_messages():
    """3개 이상 메시지를 보낸 유저만 반환한다."""
    profile = {
        "is_bot": False,
        "deleted": False,
        "profile": {"display_name": "Alice", "real_name": "Alice"},
    }
    mock_client = _make_mock_client(
        messages_by_channel={
            "C001": [
                {"type": "message", "user": "UA001", "text": "hello"},
                {"type": "message", "user": "UA001", "text": "world"},
                {"type": "message", "user": "UA001", "text": "test"},
                {"type": "message", "user": "UB002", "text": "hi"},
                {"type": "message", "user": "UB002", "text": "bye"},
            ]
        },
        user_profile=profile,
    )

    with patch("simulation.slack_collector.WebClient", return_value=mock_client):
        result = discover_users(["C001"], "xoxb-fake", min_messages=3)

    # UA001 has 3 (meets threshold), UB002 has 2 (excluded)
    assert len(result) == 1
    assert result[0]["user_id"] == "UA001"
    assert result[0]["message_count"] == 3


def test_discover_users_excludes_bots():
    """is_bot=True 인 유저는 제외된다."""
    bot_profile = {
        "is_bot": True,
        "deleted": False,
        "profile": {"display_name": "Slackbot", "real_name": "Slackbot"},
    }
    mock_client = _make_mock_client(
        messages_by_channel={
            "C001": [
                {"type": "message", "user": "UBOT01", "text": f"msg{i}"}
                for i in range(5)
            ]
        },
        user_profile=bot_profile,
    )

    with patch("simulation.slack_collector.WebClient", return_value=mock_client):
        result = discover_users(["C001"], "xoxb-fake", min_messages=3)

    assert result == []


def test_discover_users_sorted_by_count_desc():
    """메시지 수 내림차순으로 정렬된다."""
    profile = {
        "is_bot": False,
        "deleted": False,
        "profile": {"display_name": "User", "real_name": "User"},
    }

    mock_client = MagicMock()
    mock_client.conversations_history.return_value = {
        "messages": [
            {"type": "message", "user": "UA", "text": f"m{i}"} for i in range(5)
        ] + [
            {"type": "message", "user": "UB", "text": f"n{i}"} for i in range(10)
        ],
        "response_metadata": {},
    }
    mock_client.users_info.return_value = {"user": profile}

    with patch("simulation.slack_collector.WebClient", return_value=mock_client):
        result = discover_users(["C001"], "xoxb-fake", min_messages=3)

    assert len(result) == 2
    assert result[0]["message_count"] >= result[1]["message_count"]


from simulation.slack_collector import collect_user_messages


def test_collect_user_messages_filters_by_user():
    """지정 user_id의 메시지만 수집한다."""
    mock_client = MagicMock()
    mock_client.conversations_history.return_value = {
        "messages": [
            {"type": "message", "user": "UA001", "text": "오늘 배포 일정 확인했어요"},
            {"type": "message", "user": "UB002", "text": "저도 확인했습니다"},
            {"type": "message", "user": "UA001", "text": "내일 오후로 확정입니다"},
        ],
        "response_metadata": {},
    }

    with patch("simulation.slack_collector.WebClient", return_value=mock_client):
        result = collect_user_messages("UA001", ["C001"], "xoxb-fake")

    assert len(result) == 2
    assert "오늘 배포 일정 확인했어요" in result
    assert "내일 오후로 확정입니다" in result


def test_collect_user_messages_filters_noise():
    """이모지·단순 멘션·짧은 메시지는 제외된다."""
    mock_client = MagicMock()
    mock_client.conversations_history.return_value = {
        "messages": [
            {"type": "message", "user": "UA001", "text": "👍"},
            {"type": "message", "user": "UA001", "text": "<@UB002>"},
            {"type": "message", "user": "UA001", "text": "배포 완료 확인했습니다"},
            {"type": "message", "user": "UA001", "text": "네"},
        ],
        "response_metadata": {},
    }

    with patch("simulation.slack_collector.WebClient", return_value=mock_client):
        result = collect_user_messages("UA001", ["C001"], "xoxb-fake")

    assert result == ["배포 완료 확인했습니다"]


def test_collect_user_messages_aggregates_multiple_channels():
    """여러 채널의 메시지를 합산한다."""
    mock_client = MagicMock()

    def conversations_history(channel, cursor=None, limit=200):
        return {
            "messages": [
                {"type": "message", "user": "UA001", "text": f"{channel} 메시지입니다"}
            ],
            "response_metadata": {},
        }

    mock_client.conversations_history.side_effect = conversations_history

    with patch("simulation.slack_collector.WebClient", return_value=mock_client):
        result = collect_user_messages("UA001", ["C001", "C002"], "xoxb-fake")

    assert len(result) == 2
