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


def test_noise_custom_emoji_only():
    """커스텀 이모지만 있는 메시지는 노이즈."""
    assert _is_noise(":party-parrot: :tada:") is True


def test_noise_slack_channel_ref():
    """채널 링크만 있는 메시지는 노이즈."""
    assert _is_noise("<#C01234567|general>") is True


def test_noise_slack_url():
    """URL만 있는 메시지는 노이즈."""
    assert _is_noise("<https://example.com>") is True


def test_noise_mixed_real_text():
    """실제 텍스트 포함 시 노이즈가 아님."""
    assert _is_noise(":thumbsup: 수고했어요!") is False


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


from simulation.slack_collector import collect_user_messages, write_profile


def test_collect_user_messages_filters_by_user():
    """지정 user_id의 메시지만 수집한다."""
    mock_client = MagicMock()
    mock_client.call.return_value = {
        "messages": [
            {"type": "message", "user": "UA001", "text": "오늘 배포 일정 확인했어요"},
            {"type": "message", "user": "UB002", "text": "저도 확인했습니다"},
            {"type": "message", "user": "UA001", "text": "내일 오후로 확정입니다"},
        ],
        "response_metadata": {},
    }

    with patch("simulation.slack_collector.RateLimitedSlackClient", return_value=mock_client):
        result = collect_user_messages("UA001", "xoxb-fake", channels=["C001"])

    assert len(result) == 2
    assert all(isinstance(m, dict) for m in result)
    contents = [m["content"] for m in result]
    assert "오늘 배포 일정 확인했어요" in contents
    assert "내일 오후로 확정입니다" in contents


def test_collect_user_messages_filters_noise():
    """이모지·단순 멘션·짧은 메시지는 제외된다."""
    mock_client = MagicMock()
    mock_client.call.return_value = {
        "messages": [
            {"type": "message", "user": "UA001", "text": "👍"},
            {"type": "message", "user": "UA001", "text": "<@UB002>"},
            {"type": "message", "user": "UA001", "text": "배포 완료 확인했습니다"},
            {"type": "message", "user": "UA001", "text": "네"},
        ],
        "response_metadata": {},
    }

    with patch("simulation.slack_collector.RateLimitedSlackClient", return_value=mock_client):
        result = collect_user_messages("UA001", "xoxb-fake", channels=["C001"])

    assert all(isinstance(m, dict) for m in result)
    contents = [m["content"] for m in result]
    assert contents == ["배포 완료 확인했습니다"]


def test_collect_user_messages_aggregates_multiple_channels():
    """여러 채널의 메시지를 합산한다."""
    mock_client = MagicMock()

    def mock_call(method, **kwargs):
        channel = kwargs.get("channel", "")
        return {
            "messages": [
                {"type": "message", "user": "UA001", "text": f"{channel} 메시지입니다"}
            ],
            "response_metadata": {},
        }

    mock_client.call.side_effect = mock_call

    with patch("simulation.slack_collector.RateLimitedSlackClient", return_value=mock_client):
        result = collect_user_messages("UA001", "xoxb-fake", channels=["C001", "C002"])

    assert len(result) == 2


import json
import tempfile
from pathlib import Path


def test_write_profile_creates_all_files():
    """write_profile 이 5개 파일을 모두 생성한다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        team_dir = Path(tmpdir)
        result = write_profile(
            slug="testuser",
            display_name="테스트 유저",
            part_a="### 주요 업무 역할\n데이터 분석 담당",
            part_b="### Layer 0\n핵심 원칙",
            team_skills_dir=team_dir,
            raw_messages=[
                {"content": "메시지1", "ts": "1234.0", "channel": "C001", "is_thread_starter": False},
                {"content": "메시지2", "ts": "1235.0", "channel": "C001", "is_thread_starter": True},
            ],
        )

        assert result == team_dir / "testuser"
        assert (result / "SKILL.md").exists()
        assert (result / "work.md").exists()
        assert (result / "persona.md").exists()
        assert (result / "meta.json").exists()
        assert (result / "slack_messages.json").exists()


def test_write_profile_meta_json_fields():
    """meta.json 에 필수 필드가 있다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        team_dir = Path(tmpdir)
        write_profile("alice", "Alice", "partA", "partB", team_dir)
        meta = json.loads((team_dir / "alice" / "meta.json").read_text("utf-8"))

        assert meta["slug"] == "alice"
        assert meta["name"] == "Alice"
        assert meta["version"] == "v1"
        assert meta["corrections_count"] == 0
        assert meta["source"] == "slack"
        assert "created_at" in meta


def test_write_profile_skill_md_contains_both_parts():
    """SKILL.md 가 Part A 와 Part B 를 모두 포함한다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        team_dir = Path(tmpdir)
        write_profile("bob", "Bob", "PART_A_CONTENT", "PART_B_CONTENT", team_dir)
        skill_md = (team_dir / "bob" / "SKILL.md").read_text("utf-8")

        assert "PART_A_CONTENT" in skill_md
        assert "PART_B_CONTENT" in skill_md
        assert "PART A" in skill_md
        assert "PART B" in skill_md


def test_write_profile_slug_conflict_resolved():
    """슬러그 충돌 시 _2, _3 suffix 자동 부여."""
    with tempfile.TemporaryDirectory() as tmpdir:
        team_dir = Path(tmpdir)
        r1 = write_profile("alice", "Alice 1", "a", "b", team_dir)
        r2 = write_profile("alice", "Alice 2", "a", "b", team_dir)
        r3 = write_profile("alice", "Alice 3", "a", "b", team_dir)

        assert r1 == team_dir / "alice"
        assert r2 == team_dir / "alice_2"
        assert r3 == team_dir / "alice_3"


# ── RateLimitedSlackClient ────────────────────────────────────────────────────

from simulation.slack_collector import RateLimitedSlackClient


def test_rate_limited_client_retries_on_ratelimit():
    """429 ratelimited 응답 시 재시도 후 성공."""
    from slack_sdk.errors import SlackApiError

    # 첫 번째 호출은 ratelimited, 두 번째는 성공
    fake_response_ok = {"messages": ["hello"], "response_metadata": {}}
    rate_limit_exc = SlackApiError(
        message="ratelimited",
        response=MagicMock(
            status_code=429,
            data={"error": "ratelimited"},
            headers={"Retry-After": "1"},
            get=lambda k, d=None: {"error": "ratelimited"}.get(k, d),
        ),
    )
    mock_method = MagicMock(
        side_effect=[rate_limit_exc, MagicMock(data=fake_response_ok)]
    )
    mock_webclient = MagicMock()
    mock_webclient.conversations_history = mock_method

    with patch("simulation.slack_collector.WebClient", return_value=mock_webclient), \
         patch("time.sleep") as mock_sleep:
        client = RateLimitedSlackClient(token="xoxb-test")
        result = client.call("conversations_history", channel="C123", limit=10)

    assert result == fake_response_ok
    assert mock_method.call_count == 2
    mock_sleep.assert_called()  # 재시도 전 sleep 호출됨


def test_rate_limited_client_paginate_collects_all():
    """paginate()가 cursor를 따라 두 페이지를 수집한다."""
    mock_webclient = MagicMock()
    page1 = {"messages": ["a", "b"], "response_metadata": {"next_cursor": "cur1"}}
    page2 = {"messages": ["c"], "response_metadata": {}}
    mock_webclient.conversations_history.side_effect = [
        MagicMock(data=page1),
        MagicMock(data=page2),
    ]

    with patch("simulation.slack_collector.WebClient", return_value=mock_webclient):
        client = RateLimitedSlackClient(token="xoxb-test")
        result = client.paginate("conversations_history", "messages", channel="C123")

    assert result == ["a", "b", "c"]


# ── discover_channels_for_user ────────────────────────────────────────────────

from simulation.slack_collector import discover_channels_for_user, _format_messages_for_llm


def test_collect_user_messages_returns_dicts(tmp_path):
    """collect_user_messages가 list[dict]를 반환한다."""
    resp_data = {
        "messages": [
            {"type": "message", "user": "UA001", "text": "안녕하세요 반갑습니다", "ts": "1234.5678", "reply_count": 0},
        ],
        "response_metadata": {},
    }
    mock_client = MagicMock()
    mock_client.call.return_value = resp_data

    with patch("simulation.slack_collector.RateLimitedSlackClient", return_value=mock_client), \
         patch("simulation.slack_collector.discover_channels_for_user", return_value=["C001"]):
        from simulation.slack_collector import collect_user_messages
        result = collect_user_messages("UA001", "xoxb-test", channels=["C001"])

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert result[0]["content"] == "안녕하세요 반갑습니다"
    assert result[0]["channel"] == "C001"
    assert result[0]["ts"] == "1234.5678"
    assert result[0]["is_thread_starter"] is False


def test_format_messages_for_llm_sections():
    """_format_messages_for_llm이 thread_starter / long / short 섹션을 생성한다."""
    messages = [
        {"content": "짧은", "ts": "1", "channel": "C001", "is_thread_starter": False},
        {"content": "이것은 매우 긴 메시지입니다 50자 이상이 되어야 합니다 충분히 길어야 하므로 더 작성합니다", "ts": "2", "channel": "C001", "is_thread_starter": False},
        {"content": "스레드 시작 메시지입니다 중요도가 높습니다", "ts": "3", "channel": "C001", "is_thread_starter": True},
    ]
    result = _format_messages_for_llm(messages, max_messages=100)
    assert "토론 시작 메시지" in result
    assert "장문 메시지" in result
    assert "단문 메시지" in result


def test_discover_channels_for_user_filters_by_member():
    """Bot이 가입한 채널 중 user_id가 멤버인 채널 ID만 반환."""
    page1 = {
        "channels": [{"id": "C001", "is_member": True}, {"id": "C002", "is_member": False}],
        "response_metadata": {},
    }

    mock_client = MagicMock()
    mock_client.call.side_effect = [page1]
    # inner member-check now uses paginate() — return the member list directly
    mock_client.paginate.return_value = ["UA001", "UA002"]

    with patch("simulation.slack_collector.RateLimitedSlackClient", return_value=mock_client):
        result = discover_channels_for_user(user_id="UA001", token="xoxb-test")

    assert result == ["C001"]


from simulation.slack_collector import extract_work_patterns, build_work_md, extract_persona_patterns, build_persona_md


def test_extract_work_patterns_calls_llm_with_formatted_messages():
    """extract_work_patterns이 _format_messages_for_llm을 거쳐 LLM을 호출한다."""
    messages = [
        {"content": "Snowflake 쿼리 최적화 작업했어요", "ts": "1", "channel": "C001", "is_thread_starter": True},
    ]
    mock_client = MagicMock()
    mock_client.call.return_value = "분석 결과"

    result = extract_work_patterns(messages, mock_client, max_messages=10)

    assert result == "분석 결과"
    assert mock_client.call.called
    call_kwargs = mock_client.call.call_args
    assert "토론 시작 메시지" in str(call_kwargs)


def test_build_work_md_formats_with_name():
    """build_work_md가 display_name과 분석 결과를 LLM에 전달한다."""
    mock_client = MagicMock()
    mock_client.call.return_value = "# Work Profile"

    result = build_work_md("분석 결과", "홍길동", mock_client)

    assert result == "# Work Profile"
    assert mock_client.call.called
    call_kwargs = str(mock_client.call.call_args)
    assert "홍길동" in call_kwargs
    assert "분석 결과" in call_kwargs


def test_extract_persona_patterns_calls_llm_with_formatted_messages():
    """extract_persona_patterns이 _format_messages_for_llm을 거쳐 LLM을 호출한다."""
    messages = [
        {"content": "회의에서 의견을 명확하게 전달하는 편입니다", "ts": "1", "channel": "C001", "is_thread_starter": True},
    ]
    mock_client = MagicMock()
    mock_client.call.return_value = "페르소나 분석 결과"

    result = extract_persona_patterns(messages, mock_client, max_messages=10)

    assert result == "페르소나 분석 결과"
    assert mock_client.call.called
    call_kwargs = mock_client.call.call_args
    assert "토론 시작 메시지" in str(call_kwargs)


def test_build_persona_md_formats_with_name():
    """build_persona_md가 display_name과 분석 결과를 LLM에 전달한다."""
    mock_client = MagicMock()
    mock_client.call.return_value = "# Persona Profile"

    result = build_persona_md("페르소나 분석 결과", "김철수", mock_client)

    assert result == "# Persona Profile"
    assert mock_client.call.called
    call_kwargs = str(mock_client.call.call_args)
    assert "김철수" in call_kwargs
    assert "페르소나 분석 결과" in call_kwargs


def test_extract_work_patterns_appends_role_prompt():
    """role='backend'이면 역할별 추가 프롬프트가 포함된다."""
    messages = [
        {"content": "API 설계했어요", "ts": "1", "channel": "C001", "is_thread_starter": False},
    ]
    mock_client = MagicMock()
    mock_client.call.return_value = "분석"

    extract_work_patterns(messages, mock_client, max_messages=10, role="backend")

    call_args = str(mock_client.call.call_args)
    assert "백엔드 추가 분석" in call_args


def test_extract_work_patterns_general_no_role_prompt():
    """role='general'이면 역할별 추가 프롬프트가 없다."""
    messages = [
        {"content": "일반 작업했어요", "ts": "1", "channel": "C001", "is_thread_starter": False},
    ]
    mock_client = MagicMock()
    mock_client.call.return_value = "분석"

    extract_work_patterns(messages, mock_client, max_messages=10, role="general")

    call_args = str(mock_client.call.call_args)
    assert "추가 분석" not in call_args


def test_extract_persona_patterns_injects_impression():
    """impression이 있으면 프롬프트에 포함된다."""
    messages = [{"content": "열심히 일했어요", "ts": "1", "channel": "C001", "is_thread_starter": False}]
    mock_client = MagicMock()
    mock_client.call.return_value = "분석"

    extract_persona_patterns(messages, mock_client, max_messages=10, impression="꼼꼼하고 체계적")

    call_args = str(mock_client.call.call_args)
    assert "팀원 인상 메모" in call_args
    assert "꼼꼼하고 체계적" in call_args


def test_extract_persona_patterns_no_impression_block_when_empty():
    """impression이 빈 문자열이면 인상 메모 블록이 포함되지 않는다."""
    messages = [{"content": "열심히 일했어요", "ts": "1", "channel": "C001", "is_thread_starter": False}]
    mock_client = MagicMock()
    mock_client.call.return_value = "분석"

    extract_persona_patterns(messages, mock_client, max_messages=10, impression="")

    call_args = str(mock_client.call.call_args)
    assert "팀원 인상 메모" not in call_args


def test_extract_persona_patterns_whitespace_only_impression_suppressed():
    """impression이 공백만 있으면 인상 메모 블록이 포함되지 않는다."""
    messages = [{"content": "열심히 일했어요", "ts": "1", "channel": "C001", "is_thread_starter": False}]
    mock_client = MagicMock()
    mock_client.call.return_value = "분석"

    extract_persona_patterns(messages, mock_client, max_messages=10, impression="   ")

    call_args = str(mock_client.call.call_args)
    assert "팀원 인상 메모" not in call_args
