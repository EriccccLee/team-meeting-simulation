# Slack Skill Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slack 채널 대화 로그를 기반으로 팀원 SKILL.md 프로필을 자동 생성하고, team-skills/가 비어있을 때 UI에서 추출 흐름을 안내한다.

**Architecture:** `.env`의 Slack 토큰 + 채널 목록을 읽어 `/api/slack/discover`로 활성 유저(3개 이상 메시지)를 탐색하고, 사용자가 선택 후 `/api/slack/extract`를 호출하면 백그라운드 스레드에서 멤버별 수집→LLM분석→파일 생성을 순차 실행하면서 기존 SSE 패턴으로 진행 상황을 프론트에 스트리밍한다.

**Tech Stack:** `slack-sdk`, `python-dotenv`, `unidecode`, FastAPI SSE (기존 SimpleQueue 패턴), Vue 3 Composition API

---

## 파일 맵

| 작업 | 파일 | 신규/수정 |
|------|------|---------|
| Task 1 | `requirements.txt`, `.env.example`, `.gitignore` | 수정/신규 |
| Task 2 | `simulation/slack_collector.py` (slug + noise) | 신규 |
| Task 2 | `tests/__init__.py`, `tests/test_slack_collector.py` | 신규 |
| Task 3 | `simulation/slack_collector.py` (discover_users) | 추가 |
| Task 4 | `simulation/slack_collector.py` (collect_user_messages) | 추가 |
| Task 5 | `simulation/slack_collector.py` (analyze_work, analyze_persona) | 추가 |
| Task 6 | `simulation/slack_collector.py` (write_profile, _unique_slug) | 추가 |
| Task 7 | `simulation/slack_collector.py` (_run_extraction) | 추가 |
| Task 8 | `web/routes/slack_extraction.py` | 신규 |
| Task 8 | `tests/test_slack_extraction_routes.py` | 신규 |
| Task 9 | `web/app.py` | 수정 |
| Task 10 | `frontend/src/views/ExtractionView.vue` | 신규 |
| Task 11 | `frontend/src/router/index.js`, `frontend/src/views/SetupView.vue` | 수정 |

---

## Task 1: 의존성 + 환경 설정

**Files:**
- Modify: `requirements.txt`
- Create: `.env.example`
- Modify: `.gitignore` (있으면) 또는 신규 생성

- [ ] **Step 1: requirements.txt에 의존성 추가**

`requirements.txt`의 기존 내용 아래에 다음을 추가하라:

```
# Slack skill extraction
slack-sdk>=3.27.0
python-dotenv>=1.0.0
unidecode>=1.3.0
```

- [ ] **Step 2: .env.example 생성**

```
# Slack Bot Token (xoxb-로 시작)
# 필요 스코프: users:read, channels:read, channels:history, groups:read, groups:history
SLACK_BOT_TOKEN=xoxb-your-token-here

# 수집 대상 채널 ID 목록 (쉼표 구분, 채널 ID는 C로 시작)
# 예: SLACK_CHANNELS=C01234567,C08901234
SLACK_CHANNELS=C01234567,C08901234
```

파일 경로: `team-meeting-simulation/.env.example`

- [ ] **Step 3: .gitignore에 .env 추가 확인**

```bash
grep -q "^\.env$" .gitignore 2>/dev/null || echo ".env" >> .gitignore
```

예상: `.gitignore`에 `.env` 항목이 있거나 추가됨.

- [ ] **Step 4: 의존성 설치**

```bash
pip install slack-sdk>=3.27.0 python-dotenv>=1.0.0 unidecode>=1.3.0
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example .gitignore
git commit -m "chore: add slack extraction dependencies and env config"
```

---

## Task 2: slug 생성 + 노이즈 필터 (TDD)

**Files:**
- Create: `simulation/slack_collector.py`
- Create: `tests/__init__.py`
- Create: `tests/test_slack_collector.py`

- [ ] **Step 1: 테스트 파일 작성 (failing)**

`tests/__init__.py` 생성 (빈 파일):
```python
```

`tests/test_slack_collector.py` 생성:

```python
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
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
python -m pytest tests/test_slack_collector.py -v
```

예상: `ModuleNotFoundError: No module named 'simulation.slack_collector'`

- [ ] **Step 3: slack_collector.py 파일 뼈대 + generate_slug + _is_noise 구현**

`simulation/slack_collector.py` 생성:

```python
"""
Slack 메시지 기반 팀원 SKILL.md 자동 추출 파이프라인.

주요 함수:
  generate_slug(display_name)         → 슬러그 문자열
  _is_noise(text)                     → 노이즈 여부 bool
  discover_users(channels, token)     → 후보 유저 목록
  collect_user_messages(user_id, ...) → 유저 메시지 목록
  analyze_work(messages, client)      → Part A 마크다운
  analyze_persona(messages, client)   → Part B 마크다운
  write_profile(slug, ...)            → 생성된 디렉터리 Path
  _run_extraction(members, ...)       → None (SSE emit 포함)
"""
from __future__ import annotations

import json
import queue as stdlib_queue
import re
from datetime import datetime, timezone
from pathlib import Path

# ── 상수 ──────────────────────────────────────────────────────────────────────

# 이모지 유니코드 범위 (주요 블록)
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"  # Misc symbols, pictographs, emoticons
    "\U00002600-\U000027BF"  # Misc symbols, dingbats
    "\U0001F900-\U0001F9FF"  # Supplemental symbols
    "\u2600-\u26FF"          # Misc symbols
    "]+",
    flags=re.UNICODE,
)

# Slack 멘션 패턴: <@UXXX> 또는 <@UXXX|name>
_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")


# ── slug 생성 ──────────────────────────────────────────────────────────────────

def generate_slug(display_name: str) -> str:
    """display_name → 소문자 알파뉴메릭 슬러그.

    한글/중국어 등 비ASCII는 unidecode로 로마자 변환 후 처리.
    변환 결과가 빈 문자열이면 "member" 반환.
    """
    try:
        from unidecode import unidecode
        text = unidecode(display_name)
    except ImportError:
        text = display_name

    slug = re.sub(r"[^a-z0-9]", "", text.lower())
    return slug if slug else "member"


# ── 노이즈 필터 ───────────────────────────────────────────────────────────────

def _is_noise(text: str) -> bool:
    """순수 이모지·단순 멘션·너무 짧은 메시지이면 True 반환."""
    stripped = text.strip()
    if not stripped:
        return True

    # 멘션 제거 후 남은 텍스트 확인
    no_mentions = _MENTION_RE.sub("", stripped).strip()
    if not no_mentions:
        return True  # 멘션만으로 구성된 메시지

    # 이모지 제거 후 남은 텍스트 확인
    no_emoji = _EMOJI_RE.sub("", no_mentions).strip()
    if not no_emoji:
        return True  # 이모지만으로 구성된 메시지

    # 너무 짧으면 노이즈 (2자 이하)
    if len(no_emoji) <= 2:
        return True

    return False
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
python -m pytest tests/test_slack_collector.py -v
```

예상:
```
test_generate_slug_english_spaces PASSED
test_generate_slug_english_dots PASSED
test_generate_slug_korean PASSED
test_generate_slug_mixed PASSED
test_generate_slug_fallback_empty PASSED
test_is_noise_empty PASSED
test_is_noise_pure_emoji PASSED
test_is_noise_bare_mention_only PASSED
test_is_noise_mention_with_text PASSED
test_is_noise_too_short PASSED
test_is_noise_normal_message PASSED
11 passed
```

- [ ] **Step 5: Commit**

```bash
git add simulation/slack_collector.py tests/__init__.py tests/test_slack_collector.py
git commit -m "feat: add generate_slug and _is_noise with tests"
```

---

## Task 3: discover_users (TDD)

**Files:**
- Modify: `simulation/slack_collector.py` (함수 추가)
- Modify: `tests/test_slack_collector.py` (테스트 추가)

- [ ] **Step 1: 테스트 추가 (failing)**

`tests/test_slack_collector.py` 아래에 추가:

```python
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

    def users_info_side_effect(user):
        return {"user": {**profile}}

    mock_client = MagicMock()
    mock_client.conversations_history.return_value = {
        "messages": [
            {"type": "message", "user": "UA", "text": f"m{i}"} for i in range(5)
        ] + [
            {"type": "message", "user": "UB", "text": f"n{i}"} for i in range(10)
        ],
        "response_metadata": {},
    }
    mock_client.users_info.side_effect = users_info_side_effect

    with patch("simulation.slack_collector.WebClient", return_value=mock_client):
        result = discover_users(["C001"], "xoxb-fake", min_messages=3)

    assert len(result) == 2
    assert result[0]["message_count"] >= result[1]["message_count"]
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
python -m pytest tests/test_slack_collector.py::test_discover_users_filters_min_messages -v
```

예상: `ImportError: cannot import name 'discover_users'`

- [ ] **Step 3: discover_users 구현**

`simulation/slack_collector.py`에 import 추가 및 함수 추가.

파일 상단 import 블록에 추가:

```python
import logging

logger = logging.getLogger(__name__)
```

파일 끝에 추가:

```python
# ── Slack API: 유저 탐색 ───────────────────────────────────────────────────────

def discover_users(
    channels: list[str],
    token: str,
    min_messages: int = 3,
) -> list[dict]:
    """지정 채널에서 min_messages 이상 발화한 유저를 탐색해 반환.

    Returns:
        [{"user_id", "display_name", "message_count", "suggested_slug"}, ...]
        메시지 수 내림차순 정렬.
    """
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=token)
    user_counts: dict[str, int] = {}

    for channel_id in channels:
        try:
            cursor = None
            while True:
                resp = client.conversations_history(
                    channel=channel_id,
                    cursor=cursor,
                    limit=200,
                )
                for msg in resp.get("messages", []):
                    if (
                        msg.get("type") == "message"
                        and "user" in msg
                        and not msg.get("bot_id")
                        and not msg.get("subtype")
                    ):
                        uid = msg["user"]
                        user_counts[uid] = user_counts.get(uid, 0) + 1

                next_cursor = (
                    resp.get("response_metadata", {}).get("next_cursor") or ""
                )
                if next_cursor:
                    cursor = next_cursor
                else:
                    break
        except SlackApiError as e:
            logger.warning("채널 %s 접근 불가 (스킵): %s", channel_id, e)

    qualified = {
        uid: cnt for uid, cnt in user_counts.items() if cnt >= min_messages
    }

    result: list[dict] = []
    for user_id, count in qualified.items():
        try:
            user_info = client.users_info(user=user_id)["user"]
        except SlackApiError as e:
            logger.warning("users_info 실패 (user=%s, 스킵): %s", user_id, e)
            continue

        if user_info.get("is_bot") or user_info.get("deleted"):
            continue

        profile = user_info.get("profile", {})
        display_name = (
            profile.get("display_name")
            or profile.get("real_name")
            or user_info.get("name", user_id)
        )
        result.append(
            {
                "user_id": user_id,
                "display_name": display_name,
                "message_count": count,
                "suggested_slug": generate_slug(display_name),
            }
        )

    return sorted(result, key=lambda x: x["message_count"], reverse=True)
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
python -m pytest tests/test_slack_collector.py -k "discover" -v
```

예상: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add simulation/slack_collector.py tests/test_slack_collector.py
git commit -m "feat: add discover_users with Slack API integration"
```

---

## Task 4: collect_user_messages (TDD)

**Files:**
- Modify: `simulation/slack_collector.py`
- Modify: `tests/test_slack_collector.py`

- [ ] **Step 1: 테스트 추가 (failing)**

`tests/test_slack_collector.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
python -m pytest tests/test_slack_collector.py -k "collect" -v
```

예상: `ImportError: cannot import name 'collect_user_messages'`

- [ ] **Step 3: collect_user_messages 구현**

`simulation/slack_collector.py` 끝에 추가:

```python
# ── Slack API: 메시지 수집 ────────────────────────────────────────────────────

def collect_user_messages(
    user_id: str,
    channels: list[str],
    token: str,
) -> list[str]:
    """지정 user_id가 보낸 메시지 중 노이즈를 제거한 텍스트 목록 반환.

    여러 채널을 순회하며 수집하고, _is_noise() 필터를 적용한다.
    """
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=token)
    messages: list[str] = []

    for channel_id in channels:
        try:
            cursor = None
            while True:
                resp = client.conversations_history(
                    channel=channel_id,
                    cursor=cursor,
                    limit=200,
                )
                for msg in resp.get("messages", []):
                    if (
                        msg.get("type") == "message"
                        and msg.get("user") == user_id
                        and not msg.get("bot_id")
                        and not msg.get("subtype")
                    ):
                        text = msg.get("text", "").strip()
                        if text and not _is_noise(text):
                            messages.append(text)

                next_cursor = (
                    resp.get("response_metadata", {}).get("next_cursor") or ""
                )
                if next_cursor:
                    cursor = next_cursor
                else:
                    break
        except SlackApiError as e:
            logger.warning(
                "채널 %s 메시지 수집 실패 (user=%s, 스킵): %s",
                channel_id,
                user_id,
                e,
            )

    return messages
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
python -m pytest tests/test_slack_collector.py -v
```

예상: 전체 PASS (14개)

- [ ] **Step 5: Commit**

```bash
git add simulation/slack_collector.py tests/test_slack_collector.py
git commit -m "feat: add collect_user_messages with noise filtering"
```

---

## Task 5: LLM 분석 함수 (analyze_work, analyze_persona)

**Files:**
- Modify: `simulation/slack_collector.py`

이 함수들은 `claude -p` subprocess에 의존하므로 단위 테스트 없이 구현 후 수동 연기 검증.

- [ ] **Step 1: 인라인 프롬프트 상수 + analyze_work, analyze_persona 추가**

`simulation/slack_collector.py` 끝에 추가:

```python
# ── LLM 분석 프롬프트 (colleague-skill 기반) ──────────────────────────────────

_WORK_SYSTEM = "당신은 팀원 분석 전문가입니다. Slack 메시지를 기반으로 업무 프로필을 작성합니다."

WORK_ANALYSIS_PROMPT = """\
다음은 한 팀원이 Slack에서 보낸 메시지 목록입니다.
이 메시지들을 분석해 해당 팀원의 업무 역량 프로필(Part A)을 **한국어**로 작성하세요.

## 출력 형식

다음 항목을 포함하는 마크다운 문서를 작성하세요:

### 주요 업무 역할
이 팀원이 실제로 담당하는 업무 영역을 구체적으로 서술하세요.

### 기술 스택
언급되거나 사용되는 언어, 도구, 프레임워크, 플랫폼을 나열하세요.

### 업무 처리 스타일
문제 접근 방식, 작업 선호도, 실행 패턴을 서술하세요.

### 업무 커뮤니케이션 패턴
업무 관련 소통 방식, 보고 스타일, 협업 패턴을 서술하세요.

## 주의사항
- 메시지에서 명확히 드러나는 내용만 작성하세요
- 추측이나 과장 없이 사실에 기반하세요
- 마크다운 코드블록 래퍼(```markdown) 없이 바로 마크다운 내용만 출력하세요
"""

_PERSONA_SYSTEM = "당신은 팀원 분석 전문가입니다. Slack 메시지를 기반으로 페르소나를 작성합니다."

PERSONA_ANALYSIS_PROMPT = """\
다음은 한 팀원이 Slack에서 보낸 메시지 목록입니다.
이 메시지들을 분석해 해당 팀원의 페르소나 프로필(Part B)을 **한국어**로 작성하세요.

## 출력 형식

다음 5개 레이어 구조로 마크다운 문서를 작성하세요:

### Layer 0: 절대 행동 원칙
이 사람의 non-negotiable한 성격적 특성. 어떤 상황에서도 변하지 않는 핵심 행동 패턴.

### Layer 1: 핵심 정체성
이 사람이 스스로를 어떻게 인식하는지, 무엇을 중요하게 여기는지.

### Layer 2: 표현 스타일
말투, 글쓰기 특성, 자주 쓰는 표현, 어투. 가능하면 실제 메시지 패턴을 인용하세요.

### Layer 3: 의사결정 및 문제해결 패턴
어떻게 문제에 접근하고, 결정을 내리고, 의견을 표현하는지.

### Layer 4: 대인관계 패턴
다른 사람들과 어떻게 상호작용하는지, 협업 스타일, 갈등 처리 방식.

### 실행 규칙
이 페르소나로 시뮬레이션할 때 지켜야 할 규칙 목록 (3~5개 불릿).

## 주의사항
- 메시지에서 명확히 드러나는 패턴만 작성하세요
- 마크다운 코드블록 래퍼(```markdown) 없이 바로 마크다운 내용만 출력하세요
"""

_MAX_MESSAGES_FOR_ANALYSIS = 100  # LLM에 전달할 최대 메시지 수


# ── LLM 분석 ──────────────────────────────────────────────────────────────────

def analyze_work(
    messages: list[str],
    model_client,  # ClaudeCodeModelClient — 순환 임포트 방지로 타입 힌트 생략
) -> str:
    """수집된 메시지로 Part A (업무 프로필) 마크다운 생성."""
    sample = messages[:_MAX_MESSAGES_FOR_ANALYSIS]
    msg_block = "\n---\n".join(sample)
    prompt = WORK_ANALYSIS_PROMPT + f"\n\n## Slack 메시지 목록\n\n{msg_block}"
    return model_client.call(
        system_prompt=_WORK_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )


def analyze_persona(
    messages: list[str],
    model_client,
) -> str:
    """수집된 메시지로 Part B (페르소나) 마크다운 생성."""
    sample = messages[:_MAX_MESSAGES_FOR_ANALYSIS]
    msg_block = "\n---\n".join(sample)
    prompt = PERSONA_ANALYSIS_PROMPT + f"\n\n## Slack 메시지 목록\n\n{msg_block}"
    return model_client.call(
        system_prompt=_PERSONA_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )
```

- [ ] **Step 2: import 확인**

```bash
python -c "from simulation.slack_collector import analyze_work, analyze_persona; print('OK')"
```

예상: `OK`

- [ ] **Step 3: Commit**

```bash
git add simulation/slack_collector.py
git commit -m "feat: add analyze_work and analyze_persona with inline prompts"
```

---

## Task 6: write_profile + _unique_slug (TDD)

**Files:**
- Modify: `simulation/slack_collector.py`
- Modify: `tests/test_slack_collector.py`

- [ ] **Step 1: 테스트 추가 (failing)**

`tests/test_slack_collector.py` 끝에 추가:

```python
import json
import tempfile
from pathlib import Path
from simulation.slack_collector import write_profile


def test_write_profile_creates_all_files():
    """write_profile 이 4개 파일을 모두 생성한다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        team_dir = Path(tmpdir)
        result = write_profile(
            slug="testuser",
            display_name="테스트 유저",
            part_a="### 주요 업무 역할\n데이터 분석 담당",
            part_b="### Layer 0\n핵심 원칙",
            team_skills_dir=team_dir,
            raw_messages=["메시지1", "메시지2"],
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
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
python -m pytest tests/test_slack_collector.py -k "write_profile" -v
```

예상: `ImportError: cannot import name 'write_profile'`

- [ ] **Step 3: _unique_slug + write_profile 구현**

`simulation/slack_collector.py` 끝에 추가:

```python
# ── 파일 쓰기 ─────────────────────────────────────────────────────────────────

def _unique_slug(slug: str, team_skills_dir: Path) -> str:
    """슬러그 디렉터리가 이미 존재하면 _2, _3, ... suffix를 붙여 반환."""
    if not (team_skills_dir / slug).exists():
        return slug
    n = 2
    while (team_skills_dir / f"{slug}_{n}").exists():
        n += 1
    return f"{slug}_{n}"


def write_profile(
    slug: str,
    display_name: str,
    part_a: str,
    part_b: str,
    team_skills_dir: Path,
    raw_messages: list[str] | None = None,
) -> Path:
    """팀원 프로필 파일 세트를 team-skills/{slug}/ 에 생성.

    Returns:
        생성된 멤버 디렉터리 Path
    """
    unique = _unique_slug(slug, team_skills_dir)
    member_dir = team_skills_dir / unique
    member_dir.mkdir(parents=True, exist_ok=True)

    # SKILL.md — Part A + Part B 결합
    skill_md = (
        f"# {display_name} — SKILL.md\n\n"
        f"## PART A — Technical Profile\n\n{part_a}\n\n"
        f"---\n\n"
        f"## PART B — Persona Layers\n\n{part_b}\n"
    )
    (member_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # work.md, persona.md
    (member_dir / "work.md").write_text(part_a, encoding="utf-8")
    (member_dir / "persona.md").write_text(part_b, encoding="utf-8")

    # meta.json
    now = datetime.now(timezone.utc).isoformat()
    meta = {
        "slug": unique,
        "name": display_name,
        "version": "v1",
        "source": "slack",
        "created_at": now,
        "updated_at": now,
        "corrections_count": 0,
    }
    (member_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # slack_messages.json — 원본 메시지 보존
    if raw_messages is not None:
        messages_data = {"messages": raw_messages}
        (member_dir / "slack_messages.json").write_text(
            json.dumps(messages_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return member_dir
```

- [ ] **Step 4: 전체 테스트 실행 — PASS 확인**

```bash
python -m pytest tests/test_slack_collector.py -v
```

예상: 전체 PASS (18개)

- [ ] **Step 5: Commit**

```bash
git add simulation/slack_collector.py tests/test_slack_collector.py
git commit -m "feat: add write_profile with slug conflict resolution"
```

---

## Task 7: _run_extraction 오케스트레이터

**Files:**
- Modify: `simulation/slack_collector.py`

- [ ] **Step 1: _run_extraction 구현**

`simulation/slack_collector.py` 끝에 추가:

```python
# ── 추출 오케스트레이터 ───────────────────────────────────────────────────────

def _run_extraction(
    members: list[dict],    # [{"user_id", "slug", "display_name"}, ...]
    token: str,
    channels: list[str],
    q: stdlib_queue.SimpleQueue,
    team_skills_dir: Path,
) -> None:
    """팀원 목록을 순차 처리하며 SSE 이벤트를 q에 emit.

    각 팀원당: 수집 → 업무분석 → 페르소나분석 → 파일생성
    오류 발생 시 해당 멤버 스킵 후 다음 멤버 계속 진행.
    마지막에 None sentinel을 q에 넣어 SSE generator 종료 신호 전달.
    """
    # 임포트를 함수 내부에서 해서 순환 임포트 방지
    from simulation.model_client import ClaudeCodeModelClient

    model_client = ClaudeCodeModelClient(timeout=180)
    total = len(members)

    def emit(event: dict) -> None:
        q.put(event)

    try:
        for i, member in enumerate(members, start=1):
            user_id = member["user_id"]
            slug = member["slug"]
            display_name = member["display_name"]

            # 1. 메시지 수집
            emit({"type": "collecting", "slug": slug, "current": i, "total": total})
            try:
                messages = collect_user_messages(user_id, channels, token)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 메시지 수집 실패 — {e}", "slug": slug})
                continue

            if not messages:
                emit({"type": "error", "message": f"{slug}: 필터링 후 메시지가 없습니다.", "slug": slug})
                continue

            # 2. 업무 분석
            emit({"type": "analyzing", "slug": slug, "step": "work", "current": i, "total": total})
            try:
                part_a = analyze_work(messages, model_client)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 업무 분석 실패 — {e}", "slug": slug})
                continue

            # 3. 페르소나 분석
            emit({"type": "analyzing", "slug": slug, "step": "persona", "current": i, "total": total})
            try:
                part_b = analyze_persona(messages, model_client)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 페르소나 분석 실패 — {e}", "slug": slug})
                continue

            # 4. 파일 생성
            emit({"type": "writing", "slug": slug, "current": i, "total": total})
            try:
                write_profile(slug, display_name, part_a, part_b, team_skills_dir, raw_messages=messages)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 파일 저장 실패 — {e}", "slug": slug})
                continue

            emit({"type": "member_done", "slug": slug, "current": i, "total": total})

        emit({"type": "done"})

    except Exception as e:
        emit({"type": "error", "message": str(e)})
    finally:
        q.put(None)  # SSE generator 종료 신호
```

- [ ] **Step 2: import 확인**

```bash
python -c "from simulation.slack_collector import _run_extraction; print('OK')"
```

예상: `OK`

- [ ] **Step 3: Commit**

```bash
git add simulation/slack_collector.py
git commit -m "feat: add _run_extraction orchestrator with SSE emit"
```

---

## Task 8: API 라우트 (slack_extraction.py)

**Files:**
- Create: `web/routes/slack_extraction.py`
- Create: `tests/test_slack_extraction_routes.py`

- [ ] **Step 1: 테스트 파일 작성 (failing)**

`tests/test_slack_extraction_routes.py` 생성:

```python
"""web/routes/slack_extraction.py 라우트 테스트."""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client_with_env(monkeypatch):
    """SLACK_BOT_TOKEN, SLACK_CHANNELS 환경변수가 설정된 TestClient."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_CHANNELS", "C001,C002")
    # 모듈 재로드 없이 패치만으로 테스트
    from web.app import app
    return TestClient(app, raise_server_exceptions=False)


def test_discover_missing_token(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("SLACK_CHANNELS", "C001")
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/slack/discover")
    assert res.status_code == 400
    assert "SLACK_BOT_TOKEN" in res.json()["detail"]


def test_discover_missing_channels(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.delenv("SLACK_CHANNELS", raising=False)
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/api/slack/discover")
    assert res.status_code == 400
    assert "SLACK_CHANNELS" in res.json()["detail"]


def test_discover_returns_user_list(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNELS", "C001")
    mock_users = [
        {
            "user_id": "UA001",
            "display_name": "홍길동",
            "message_count": 5,
            "suggested_slug": "honggildong",
        }
    ]
    with patch("web.routes.slack_extraction.discover_users", return_value=mock_users):
        from web.app import app
        client = TestClient(app, raise_server_exceptions=False)
        res = client.get("/api/slack/discover")

    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["user_id"] == "UA001"


def test_extract_returns_session_id(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNELS", "C001")

    with patch("web.routes.slack_extraction._run_extraction"):
        from web.app import app
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post(
            "/api/slack/extract",
            json=[{"user_id": "UA001", "slug": "honggildong", "display_name": "홍길동"}],
        )

    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert len(data["session_id"]) == 36  # UUID 형식


def test_extract_empty_list_returns_400(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNELS", "C001")
    from web.app import app
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post("/api/slack/extract", json=[])
    assert res.status_code == 400
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
python -m pytest tests/test_slack_extraction_routes.py -v
```

예상: `ImportError` 또는 `404` (라우트 미등록)

- [ ] **Step 3: slack_extraction.py 구현**

`web/routes/slack_extraction.py` 생성:

```python
"""
GET  /api/slack/discover            — 채널에서 활성 유저 탐색
POST /api/slack/extract             — 스킬 추출 시작 (session_id 즉시 반환)
GET  /api/slack/stream/{session_id} — SSE 스트림 (기존 패턴과 동일)
"""
from __future__ import annotations

import asyncio
import json
import os
import queue as stdlib_queue
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# .env 로드 (이미 로드된 경우 덮어쓰지 않음)
load_dotenv(_ROOT / ".env", override=False)

from simulation.slack_collector import _run_extraction, discover_users

router = APIRouter()

_TEAM_SKILLS_DIR = _ROOT / "team-skills"
_sessions: dict[str, stdlib_queue.SimpleQueue] = {}


# ── 환경변수 검증 헬퍼 ────────────────────────────────────────────────────────

def _get_slack_config() -> tuple[str, list[str]]:
    """SLACK_BOT_TOKEN, SLACK_CHANNELS 읽기. 없으면 400 raise."""
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    channels_raw = os.getenv("SLACK_CHANNELS", "").strip()

    if not token:
        raise HTTPException(
            status_code=400,
            detail="SLACK_BOT_TOKEN이 .env에 설정되지 않았습니다.",
        )
    if not channels_raw:
        raise HTTPException(
            status_code=400,
            detail="SLACK_CHANNELS가 .env에 설정되지 않았습니다.",
        )

    channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    return token, channels


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/slack/discover")
def slack_discover() -> list[dict[str, Any]]:
    """채널에서 3개 이상 메시지를 보낸 유저 목록 반환."""
    token, channels = _get_slack_config()
    try:
        return discover_users(channels, token, min_messages=3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExtractMember(BaseModel):
    user_id: str
    slug: str
    display_name: str


@router.post("/slack/extract")
async def slack_extract(members: list[ExtractMember]) -> dict[str, str]:
    """추출 세션 시작. session_id 즉시 반환하고 백그라운드에서 추출 실행."""
    if not members:
        raise HTTPException(status_code=400, detail="추출할 팀원을 1명 이상 선택하세요.")

    token, channels = _get_slack_config()

    session_id = str(uuid.uuid4())
    q: stdlib_queue.SimpleQueue = stdlib_queue.SimpleQueue()
    _sessions[session_id] = q

    members_dicts = [m.model_dump() for m in members]

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        _run_extraction,
        members_dicts,
        token,
        channels,
        q,
        _TEAM_SKILLS_DIR,
    )

    return {"session_id": session_id}


@router.get("/slack/stream/{session_id}")
async def slack_stream(session_id: str) -> StreamingResponse:
    """SSE 스트림 — 기존 /api/stream/{session_id} 와 동일한 SimpleQueue 폴링 패턴."""
    q = _sessions.get(session_id)
    if q is None:
        raise HTTPException(status_code=404, detail="session not found")

    async def generate():
        try:
            while True:
                try:
                    event = q.get_nowait()
                except stdlib_queue.Empty:
                    await asyncio.sleep(0.05)
                    continue

                if event is None:
                    yield 'data: {"type": "end"}\n\n'
                    break

                data = json.dumps(event, ensure_ascii=False)
                yield f"data: {data}\n\n"
        finally:
            _sessions.pop(session_id, None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
python -m pytest tests/test_slack_extraction_routes.py -v
```

예상: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add web/routes/slack_extraction.py tests/test_slack_extraction_routes.py
git commit -m "feat: add slack extraction API routes with tests"
```

---

## Task 9: app.py에 라우터 등록

**Files:**
- Modify: `web/app.py`

- [ ] **Step 1: slack_extraction 라우터 import + 등록**

`web/app.py`를 다음과 같이 수정:

```python
# 기존 import 라인:
from .routes import history, participants, simulation

# 변경 후:
from .routes import history, participants, simulation, slack_extraction
```

`app.include_router(history.router, prefix="/api")` 아래에 추가:

```python
app.include_router(slack_extraction.router, prefix="/api")
```

- [ ] **Step 2: 동작 확인**

```bash
python -c "from web.app import app; print('routes:', [r.path for r in app.routes if hasattr(r, 'path')])" 2>&1 | grep slack
```

예상: `/api/slack/discover`, `/api/slack/extract`, `/api/slack/stream/{session_id}` 가 출력됨.

- [ ] **Step 3: Commit**

```bash
git add web/app.py
git commit -m "feat: register slack_extraction router in FastAPI app"
```

---

## Task 10: ExtractionView.vue

**Files:**
- Create: `frontend/src/views/ExtractionView.vue`

- [ ] **Step 1: ExtractionView.vue 생성**

```vue
<template>
  <div class="extract-page">
    <!-- 헤더 -->
    <header class="header">
      <span class="logo-square" />
      <span class="logo-text">SLACK SKILL EXTRACTION</span>
      <button class="back-btn" @click="router.push('/')">← 돌아가기</button>
    </header>

    <!-- Step 1: 탐색 시작 -->
    <main v-if="step === 1" class="main">
      <div class="intro">
        <p class="hint">
          <code>.env</code>에 설정된 Slack 채널에서 3개 이상 메시지를 보낸 팀원을 자동으로 탐색합니다.
        </p>
      </div>
      <div v-if="discoverError" class="error-msg">{{ discoverError }}</div>
      <footer class="footer">
        <button class="btn btn-start" :disabled="isDiscovering" @click="doDiscover">
          {{ isDiscovering ? '탐색 중...' : '채널 탐색 시작 ──────────' }}
        </button>
      </footer>
    </main>

    <!-- Step 2: 후보 확인 + slug 편집 -->
    <main v-else-if="step === 2" class="main">
      <p class="section-label">발견된 팀원 ({{ candidates.length }}명, 메시지 3개 이상 기준)</p>
      <ul class="candidate-list">
        <li
          v-for="c in candidates"
          :key="c.user_id"
          class="candidate-item"
          :class="{ selected: selectedIds.includes(c.user_id) }"
        >
          <input type="checkbox" :value="c.user_id" v-model="selectedIds" />
          <div class="cand-info">
            <span class="cand-name">{{ c.display_name }}</span>
            <span class="cand-badge">{{ c.message_count }}개</span>
          </div>
          <div class="slug-group">
            <label class="slug-label">slug</label>
            <input
              class="slug-input"
              v-model="slugMap[c.user_id]"
              spellcheck="false"
              :class="{ invalid: !slugMap[c.user_id]?.trim() && selectedIds.includes(c.user_id) }"
            />
          </div>
        </li>
      </ul>
      <div v-if="extractError" class="error-msg">{{ extractError }}</div>
      <footer class="footer">
        <button
          class="btn btn-start"
          :disabled="!canExtract || isExtracting"
          @click="doExtract"
        >
          {{ isExtracting
            ? '시작 중...'
            : `선택한 ${selectedIds.length}명 스킬 추출 시작 ──────────` }}
        </button>
      </footer>
    </main>

    <!-- Step 3: 추출 진행 중 (SSE) -->
    <main v-else-if="step === 3" class="main step3">
      <p class="section-label">추출 진행 중 ({{ doneCount }}/{{ members.length }})</p>
      <div
        v-for="m in members"
        :key="m.slug"
        class="member-card"
        :class="{
          active: m.slug === currentSlug,
          done: m.done,
          errored: m.errored
        }"
      >
        <div class="member-header">
          <div class="member-title">
            <span class="member-name">{{ m.display_name }}</span>
            <span class="member-slug">{{ m.slug }}</span>
          </div>
          <span class="member-idx">[{{ m.index }}/{{ members.length }}]</span>
        </div>
        <!-- 현재 처리 중이거나 완료/오류 상태인 경우 스텝 표시 -->
        <div v-if="m.slug === currentSlug || m.done || m.errored" class="member-steps">
          <div
            v-for="s in m.steps"
            :key="s.key"
            class="step-row"
            :class="{ 'step-done': s.done, 'step-active': s.active }"
          >
            <span class="step-icon">{{ s.done ? '✓' : s.active ? '⟳' : '○' }}</span>
            <span class="step-text">{{ s.label }}</span>
          </div>
          <div v-if="m.errored" class="member-error">{{ m.errorMsg }}</div>
        </div>
      </div>

      <div v-if="isDone" class="done-banner">
        ✓ 모든 팀원 스킬 추출 완료! 잠시 후 메인 화면으로 이동합니다...
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// ── 상태 ──────────────────────────────────────────────────────────────────────
const step = ref(1)
const candidates = ref([])      // discover 결과
const selectedIds = ref([])     // 선택된 user_id 배열
const slugMap = reactive({})    // user_id → slug 매핑

const members = ref([])         // Step 3용 멤버 진행 상태
const currentSlug = ref(null)
const isDone = ref(false)
const doneCount = computed(() => members.value.filter(m => m.done).length)

const isDiscovering = ref(false)
const isExtracting = ref(false)
const discoverError = ref('')
const extractError = ref('')

const canExtract = computed(
  () =>
    selectedIds.value.length > 0 &&
    selectedIds.value.every(id => slugMap[id]?.trim())
)

// ── Step 1: 탐색 ──────────────────────────────────────────────────────────────
async function doDiscover() {
  isDiscovering.value = true
  discoverError.value = ''

  try {
    const res = await fetch('/api/slack/discover')
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `서버 오류 (${res.status})`)
    }
    candidates.value = await res.json()

    if (!candidates.value.length) {
      discoverError.value =
        '3개 이상 메시지를 보낸 팀원을 찾지 못했습니다. 채널 설정을 확인하세요.'
      return
    }

    // 전체 선택 + slug 초기화
    selectedIds.value = candidates.value.map(c => c.user_id)
    candidates.value.forEach(c => {
      slugMap[c.user_id] = c.suggested_slug
    })

    step.value = 2
  } catch (e) {
    discoverError.value = e.message
  } finally {
    isDiscovering.value = false
  }
}

// ── Step 2: 추출 시작 ─────────────────────────────────────────────────────────
async function doExtract() {
  isExtracting.value = true
  extractError.value = ''

  const selected = candidates.value.filter(c =>
    selectedIds.value.includes(c.user_id)
  )
  const body = selected.map(c => ({
    user_id: c.user_id,
    slug: slugMap[c.user_id].trim(),
    display_name: c.display_name,
  }))

  // 멤버 진행 상태 초기화
  members.value = body.map((m, i) => ({
    slug: m.slug,
    display_name: m.display_name,
    index: i + 1,
    done: false,
    errored: false,
    errorMsg: '',
    steps: [
      { key: 'collecting', label: '메시지 수집',     done: false, active: false },
      { key: 'work',       label: '업무 스킬 분석',  done: false, active: false },
      { key: 'persona',    label: '페르소나 분석',   done: false, active: false },
      { key: 'writing',    label: '파일 생성',       done: false, active: false },
    ],
  }))

  try {
    const res = await fetch('/api/slack/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `서버 오류 (${res.status})`)
    }
    const { session_id } = await res.json()
    step.value = 3
    subscribeSSE(session_id)
  } catch (e) {
    extractError.value = e.message
    isExtracting.value = false
  }
}

// ── Step 3: SSE 구독 ──────────────────────────────────────────────────────────
function subscribeSSE(sessionId) {
  const es = new EventSource(`/api/slack/stream/${sessionId}`)

  es.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (data.type === 'end') {
      es.close()
      return
    }

    const member = members.value.find(m => m.slug === data.slug)

    if (data.type === 'collecting') {
      currentSlug.value = data.slug
      if (member) activateStep(member, 'collecting')

    } else if (data.type === 'analyzing') {
      if (member) {
        const prevKey = data.step === 'work' ? 'collecting' : 'work'
        completeStep(member, prevKey)
        activateStep(member, data.step)
      }

    } else if (data.type === 'writing') {
      if (member) {
        completeStep(member, 'persona')
        activateStep(member, 'writing')
      }

    } else if (data.type === 'member_done') {
      if (member) {
        completeStep(member, 'writing')
        member.done = true
      }
      currentSlug.value = null

    } else if (data.type === 'done') {
      isDone.value = true
      setTimeout(() => router.push('/'), 3000)

    } else if (data.type === 'error' && data.slug) {
      const m = members.value.find(m => m.slug === data.slug)
      if (m) {
        m.errored = true
        m.errorMsg = data.message
      }
    }
  }

  es.onerror = () => es.close()
}

function activateStep(member, key) {
  const s = member.steps.find(s => s.key === key)
  if (s) { s.active = true; s.done = false }
}

function completeStep(member, key) {
  const s = member.steps.find(s => s.key === key)
  if (s) { s.done = true; s.active = false }
}
</script>

<style scoped>
.extract-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 0 40px;
}

/* 헤더 */
.header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 28px 0 24px;
  border-bottom: 1px solid var(--gray-200);
}
.logo-square {
  width: 14px; height: 14px;
  background: var(--orange);
  display: inline-block;
}
.logo-text {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--black);
  flex: 1;
}
.back-btn {
  background: none;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gray-600);
  padding: 6px 12px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.back-btn:hover { border-color: var(--black); color: var(--black); }

/* 공통 */
.main {
  display: flex;
  flex-direction: column;
  padding: 36px 0 24px;
  flex: 1;
  max-width: 640px;
}
.section-label {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--gray-600);
  text-transform: uppercase;
  margin-bottom: 16px;
}
.hint {
  font-size: 14px;
  color: var(--gray-600);
  line-height: 1.7;
  margin-bottom: 32px;
}
.hint code {
  font-family: var(--font-mono);
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 12px;
}
.error-msg { color: #DC2626; font-size: 13px; margin-bottom: 16px; }

/* 푸터 */
.footer {
  padding: 20px 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.btn {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.05em;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-start {
  background: var(--black);
  color: #fff;
  padding: 14px 28px;
  text-align: left;
}
.btn-start:hover:not(:disabled) { background: #222; }

/* Step 2: 후보 목록 */
.candidate-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.candidate-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  transition: border-color 0.2s, background 0.2s;
}
.candidate-item.selected { border-color: var(--black); }
.candidate-item input[type="checkbox"] { accent-color: var(--orange); flex-shrink: 0; }
.cand-info { display: flex; align-items: center; gap: 8px; flex: 1; }
.cand-name { font-size: 14px; font-weight: 500; }
.cand-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  padding: 2px 8px;
  color: var(--gray-600);
}
.slug-group { display: flex; align-items: center; gap: 6px; }
.slug-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--gray-400);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.slug-input {
  width: 120px;
  padding: 5px 8px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
}
.slug-input:focus { border-color: var(--black); }
.slug-input.invalid { border-color: #DC2626; }

/* Step 3: 멤버 카드 */
.step3 { max-width: 540px; }
.member-card {
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  margin-bottom: 10px;
  overflow: hidden;
  transition: border-color 0.2s;
}
.member-card.active { border-color: var(--orange); }
.member-card.done { border-color: #16A34A; }
.member-card.errored { border-color: #DC2626; }

.member-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--gray-50);
}
.member-title { display: flex; align-items: center; gap: 8px; }
.member-name { font-size: 14px; font-weight: 500; }
.member-slug {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gray-400);
}
.member-idx {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gray-400);
}

.member-steps { padding: 10px 16px 12px; }
.step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  color: var(--gray-400);
  font-size: 13px;
}
.step-row.step-done { color: #16A34A; }
.step-row.step-active { color: var(--black); font-weight: 500; }
.step-icon { font-family: var(--font-mono); width: 16px; }

.member-error {
  margin-top: 8px;
  font-size: 12px;
  color: #DC2626;
  font-family: var(--font-mono);
}

.done-banner {
  margin-top: 24px;
  padding: 16px 20px;
  background: #F0FDF4;
  border: 1px solid #16A34A;
  border-radius: 4px;
  font-size: 14px;
  color: #15803D;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/ExtractionView.vue
git commit -m "feat: add ExtractionView with 3-step Slack skill extraction UI"
```

---

## Task 11: 라우터 + SetupView 연결

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/SetupView.vue`

- [ ] **Step 1: router/index.js에 /extract 라우트 추가**

`frontend/src/router/index.js` 전체:

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import SetupView from '../views/SetupView.vue'
import MeetingView from '../views/MeetingView.vue'
import HistoryView from '../views/HistoryView.vue'
import ExtractionView from '../views/ExtractionView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: SetupView },
    { path: '/meeting', component: MeetingView },
    { path: '/history/:sessionId', component: HistoryView },
    { path: '/extract', component: ExtractionView },
  ],
})
```

- [ ] **Step 2: SetupView.vue — 빈 team-skills 감지 + 헤더 링크**

`frontend/src/views/SetupView.vue`에서 두 곳을 수정.

**수정 1: 헤더에 재추출 링크 추가**

기존:
```html
    <header class="header">
      <span class="logo-square" />
      <span class="logo-text">TEAM MEETING SIMULATION</span>
    </header>
```

변경 후:
```html
    <header class="header">
      <span class="logo-square" />
      <span class="logo-text">TEAM MEETING SIMULATION</span>
      <button class="extract-link" @click="router.push('/extract')">팀원 재추출</button>
    </header>
```

**수정 2: onMounted에서 빈 team-skills 감지 → /extract 리다이렉트**

기존 `onMounted` 시작 부분:
```javascript
onMounted(async () => {
  try {
    const res = await fetch('/api/participants')
    allParticipants.value = await res.json()
    selectedSlugs.value = allParticipants.value.map(p => p.slug)
  } catch (e) {
    error.value = '팀원 목록을 불러오지 못했습니다.'
  } finally {
    loadingParticipants.value = false
  }
```

변경 후:
```javascript
onMounted(async () => {
  try {
    const res = await fetch('/api/participants')
    allParticipants.value = await res.json()

    // team-skills가 비어있으면 추출 화면으로 안내
    if (allParticipants.value.length === 0) {
      router.push('/extract')
      return
    }

    selectedSlugs.value = allParticipants.value.map(p => p.slug)
  } catch (e) {
    error.value = '팀원 목록을 불러오지 못했습니다.'
  } finally {
    loadingParticipants.value = false
  }
```

**수정 3: 헤더 `.extract-link` CSS 추가**

`<style scoped>` 블록의 `.logo-text` 스타일 아래에 추가:

```css
.extract-link {
  margin-left: auto;
  background: none;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gray-600);
  padding: 6px 12px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.extract-link:hover { border-color: var(--black); color: var(--black); }
```

- [ ] **Step 3: 프론트엔드 빌드 확인**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

예상: `✓ built in ...` (오류 없음)

- [ ] **Step 4: 수동 E2E 테스트**

서버를 실행하고 브라우저에서 확인:

```bash
# 터미널 1: FastAPI
uvicorn web.app:app --reload --port 8000

# 터미널 2: Vite dev server
cd frontend && npm run dev
```

체크리스트:
- [ ] `http://localhost:5173/` 접속 시 `team-skills/`에 멤버가 있으면 SetupView 정상 표시
- [ ] 헤더 우측 "팀원 재추출" 버튼 클릭 시 `/extract`로 이동
- [ ] `/extract` 페이지에서 "채널 탐색 시작" 클릭 시 `.env` 미설정이면 오류 메시지 표시
- [ ] `.env`에 유효한 토큰+채널 설정 후 탐색 시 후보 유저 목록 표시
- [ ] slug 편집 가능, 체크박스로 제외 가능
- [ ] "추출 시작" 후 Step 3 진행 카드에서 단계별 상태 변화 확인
- [ ] 완료 후 3초 뒤 `/`로 자동 이동

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/index.js frontend/src/views/SetupView.vue
git commit -m "feat: add /extract route and empty-team redirect in SetupView"
```

---

## 전체 테스트 실행

```bash
python -m pytest tests/ -v
```

예상:
```
tests/test_slack_collector.py::test_generate_slug_english_spaces PASSED
... (18개 PASSED)
tests/test_slack_extraction_routes.py::test_discover_missing_token PASSED
... (5개 PASSED)
23 passed
```
