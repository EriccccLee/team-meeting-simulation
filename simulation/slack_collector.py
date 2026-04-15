"""
Slack 메시지 기반 팀원 SKILL.md 자동 추출 파이프라인.

주요 함수:
  generate_slug(display_name)              → 슬러그 문자열
  _is_noise(text)                          → 노이즈 여부 bool
  RateLimitedSlackClient(token)            → rate-limit 안전 Slack 클라이언트
  discover_channels_for_user(user_id, ...) → Bot이 가입한 채널 중 user 채널 목록
  discover_users(channels, token)          → 후보 유저 목록
  collect_user_messages(user_id, ...)      → list[dict] 유저 메시지 목록
  _format_messages_for_llm(messages, ...)  → LLM 입력용 가중치 포맷 문자열
  extract_work_patterns(messages, ...)     → Stage 1: 업무 패턴 구조화 추출
  build_work_md(analysis, ...)             → Stage 2: 업무 프로필 마크다운
  extract_persona_patterns(messages, ...)  → Stage 1: 페르소나 패턴 구조화 추출
  build_persona_md(analysis, ...)          → Stage 2: 페르소나 마크다운
  write_profile(slug, ...)                 → 생성된 디렉터리 Path
  _run_extraction(members, ...)            → None (SSE emit 포함)
"""
from __future__ import annotations

import json
import logging
import os
import queue as stdlib_queue
import re
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:  # slack_sdk optional at import time; used only in discover_users
    WebClient = None  # type: ignore[assignment,misc]
    SlackApiError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

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

# 커스텀 이모지: :custom-emoji:
_SLACK_CUSTOM_EMOJI_RE = re.compile(r":[a-z0-9_\-+]{2,}:", re.IGNORECASE)  # min 2 chars, case-insensitive

# Slack URL: <http://...> 또는 <https://...>
_SLACK_LINK_RE = re.compile(r"<https?://[^>]+>")

# Slack 채널 참조: <#CXXX|name> 또는 <#CXXX>
_SLACK_CHAN_RE = re.compile(r"<#[A-Z0-9]+(?:\|[^>]*)?>")


# ── Rate-limited Slack client ──────────────────────────────────────────────────

_MAX_RETRIES = 5
_RETRY_MAX_WAIT = 60.0


class RateLimitedSlackClient:
    """Slack API 호출을 래핑해 ratelimited 오류 시 Retry-After 기반 재시도."""

    def __init__(self, token: str) -> None:
        self._client = WebClient(token=token)

    def call(self, method: str, **kwargs) -> dict:
        """단일 API 메서드를 호출하고 응답 data를 반환."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return getattr(self._client, method)(**kwargs).data
            except SlackApiError as e:
                if e.response.get("error") == "ratelimited":
                    try:
                        retry_after = float(e.response.headers.get("Retry-After", attempt))
                    except (TypeError, ValueError):
                        retry_after = float(attempt)
                    wait = min(retry_after, _RETRY_MAX_WAIT)
                    logger.warning(
                        "Rate limited — %.0fs 대기 (시도 %d/%d)",
                        wait, attempt, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"Slack API {method} — {_MAX_RETRIES}회 재시도 후 실패")

    def paginate(self, method: str, result_key: str, **kwargs) -> list:
        """cursor 기반 페이지네이션으로 result_key 항목 전체를 수집.

        Note: 'cursor' must not be passed in kwargs — it is managed internally.
        """
        kwargs.pop("cursor", None)  # guard against accidental cursor kwarg
        items: list = []
        cursor = None
        while True:
            extra = {"cursor": cursor} if cursor else {}
            data = self.call(method, **kwargs, **extra)
            items.extend(data.get(result_key, []))
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return items


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

    # 채널 링크, URL, 커스텀 이모지 제거 후 남은 텍스트 확인
    no_chan = _SLACK_CHAN_RE.sub("", no_mentions).strip()
    no_url = _SLACK_LINK_RE.sub("", no_chan).strip()
    no_custom = _SLACK_CUSTOM_EMOJI_RE.sub("", no_url).strip()
    no_emoji = _EMOJI_RE.sub("", no_custom).strip()
    if not no_emoji:
        return True  # 이모지만으로 구성된 메시지

    # 너무 짧으면 노이즈 (2자 이하)
    if len(no_emoji) <= 2:
        return True

    return False


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
        # 슬러그: "[leecy]" 브라켓 안 값 우선 사용, 없으면 이름 로마자 변환
        bracket_match = re.search(r"\[([^\]]+)\]", display_name)
        if bracket_match:
            suggested_slug = bracket_match.group(1).strip().lower()
        else:
            slug_name = re.sub(r"\s*\[.*?\]\s*$", "", display_name).strip()
            suggested_slug = generate_slug(slug_name)
        result.append(
            {
                "user_id": user_id,
                "display_name": display_name,
                "message_count": count,
                "suggested_slug": suggested_slug,
            }
        )

    return sorted(result, key=lambda x: x["message_count"], reverse=True)


# ── 메시지 한도 상수 (프론트엔드 기본값과 동기화) ────────────────────────────

_DEFAULT_MAX_COLLECT = 2000   # Slack API 수집 상한
_DEFAULT_MAX_MESSAGES = 300   # LLM 전달 상한

# ── Slack API: 채널 자동 탐색 ─────────────────────────────────────────────────

def discover_channels_for_user(
    user_id: str,
    token: str,
    channel_limit: int = 50,
) -> list[str]:
    """Bot이 가입한 채널 중 user_id가 멤버인 채널 ID 목록 반환.

    채널 자동 탐색이 필요할 때 collect_user_messages에서 내부 호출된다.
    """
    client = RateLimitedSlackClient(token)
    channels: list[dict] = []
    cursor = None
    while len(channels) < channel_limit:
        extra = {"cursor": cursor} if cursor else {}
        data = client.call(
            "conversations_list",
            types="public_channel,private_channel,mpim",
            exclude_archived=True,
            limit=200,
            **extra,
        )
        for ch in data.get("channels", []):
            if ch.get("is_member"):
                channels.append(ch)
                if len(channels) >= channel_limit:
                    break
        cursor = (data.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break

    channels = channels[:channel_limit]
    result = []
    for ch in channels:
        try:
            members = client.paginate("conversations_members", "members", channel=ch["id"], limit=200)
            if user_id in members:
                result.append(ch["id"])
        except SlackApiError:
            continue
    return result


# ── Slack API: 메시지 수집 ────────────────────────────────────────────────────

def collect_user_messages(
    user_id: str,
    token: str,
    channels: list[str] | None = None,
    max_collect: int = _DEFAULT_MAX_COLLECT,
) -> list[dict]:
    """지정 user_id가 보낸 메시지 중 노이즈를 제거한 메시지 딕셔너리 목록 반환.

    Returns:
        [{"content": str, "ts": str, "channel": str, "is_thread_starter": bool}, ...]
    channels=None이면 discover_channels_for_user()로 자동 탐색.
    """
    if channels is None:
        channels = discover_channels_for_user(user_id, token)

    client = RateLimitedSlackClient(token)
    messages: list[dict] = []

    for channel_id in channels:
        try:
            cursor = None
            while True:
                extra = {"cursor": cursor} if cursor else {}
                resp = client.call("conversations_history", channel=channel_id, limit=200, **extra)
                for msg in resp.get("messages", []):
                    if (
                        msg.get("type") == "message"
                        and msg.get("user") == user_id
                        and not msg.get("bot_id")
                        and not msg.get("subtype")
                    ):
                        text = msg.get("text", "").strip()
                        if text and not _is_noise(text):
                            messages.append({
                                "content": text,
                                "ts": msg.get("ts", ""),
                                "channel": channel_id,
                                "is_thread_starter": bool(msg.get("reply_count", 0)),
                            })
                next_cursor = (resp.get("response_metadata") or {}).get("next_cursor") or ""
                if next_cursor and len(messages) < max_collect:
                    cursor = next_cursor
                else:
                    break
        except SlackApiError as e:
            logger.warning(
                "채널 %s 메시지 수집 실패 (user=%s, 스킵): %s",
                channel_id, user_id, e,
            )
        if len(messages) >= max_collect:
            break

    return messages


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



# ── LLM 분석 ──────────────────────────────────────────────────────────────────

def _format_messages_for_llm(
    messages: list[dict],
    max_messages: int = _DEFAULT_MAX_MESSAGES,
) -> str:
    """메시지를 중요도 기준으로 분류해 LLM 입력 형식으로 포맷팅.

    thread_starter(40%) → long >50자(40%) → short(20%) 비율 적용.
    """
    if max_messages <= 0 or not messages:
        return ""

    thread_msgs = [m for m in messages if m.get("is_thread_starter")]
    long_msgs   = [m for m in messages if not m.get("is_thread_starter") and len(m["content"]) > 50]
    short_msgs  = [m for m in messages if not m.get("is_thread_starter") and len(m["content"]) <= 50]

    t_budget = max_messages * 4 // 10
    l_budget = max_messages * 4 // 10

    t_n = min(len(thread_msgs), t_budget)
    # Long gets its budget + any unused thread slots
    l_n = min(len(long_msgs), l_budget + (t_budget - t_n))
    # Short gets all remaining slots; if short is scarce, long absorbs the rest
    s_n = min(len(short_msgs), max_messages - t_n - l_n)
    l_n = min(len(long_msgs), max_messages - t_n - s_n)

    def fmt(m: dict) -> str:
        return f"[{m.get('ts', '')}][{m.get('channel', '')}] {m['content']}"

    lines = [
        "## 토론 시작 메시지 (관점·결정·기술 공유 — 분석 우선)",
        *[fmt(m) for m in thread_msgs[:t_n]],
        "",
        "## 장문 메시지 (논의·방안 — 업무 역량 파악용)",
        *[fmt(m) for m in long_msgs[:l_n]],
        "",
        "## 단문 메시지 (말투·스타일 참고용)",
        *[fmt(m) for m in short_msgs[:s_n]],
    ]
    return "\n".join(lines)


# ── Stage 1: 패턴 추출 프롬프트 ───────────────────────────────────────────────

_WORK_EXTRACT_PROMPT = """\
다음 팀원의 Slack 메시지를 분석해 아래 4개 차원의 패턴을 **구조화된 데이터**로 추출하세요.
이 출력은 두 번째 단계에서 마크다운 프로필로 변환됩니다.

출력 형식:
[업무 역할] 이 사람이 실제로 담당하는 업무 영역 (구체적 예시 포함)
[기술 스택] 언급된 언어·도구·플랫폼 목록
[업무 스타일] 문제 접근 방식, 실행 패턴, 선호하는 작업 방식
[소통 패턴] 보고 방식, 협업 스타일, 피드백 방식

각 항목에 실제 메시지를 인용해 근거를 제시하세요.
"""

ROLE_SPECIFIC_PROMPTS: dict[str, str] = {
    "backend": """\
[백엔드 추가 분석]
- 명명 규범: 함수·변수·API 네이밍 패턴
- 인터페이스 설계 선호도: REST vs GraphQL, 동기 vs 비동기
- DB 조작 방식: ORM 선호 여부, 쿼리 최적화 접근
- Code Review 스타일: 어떤 점을 주로 지적하는가
""",
    "frontend": """\
[프론트엔드 추가 분석]
- 컴포넌트 설계 패턴: 재사용성 vs 특화, 상태 관리 방식
- 번들 최적화 관심도: 성능 지표 언급 빈도
- 접근성·UX 감수성: 사용자 경험 관련 발언
""",
    "ml": """\
[AI/ML 추가 분석]
- 실험 설계 방식: 가설 설정, 지표 정의, 재현성 관리
- 모델 배포 관심도: MLOps, 모니터링, A/B 테스트
- 데이터 품질에 대한 태도: 데이터 검증, 전처리 선호
""",
    "pm": """\
[PM 추가 분석]
- PRD 구조화 방식: 문제 정의 vs 솔루션 우선
- 우선순위 산정 방법: 데이터 기반 vs 직관, 스테이크홀더 조율
- 데이터 활용도: 지표 언급, 분석 요청 빈도
""",
    "data": """\
[데이터 분석 추가 분석]
- SQL 스타일: 복잡 쿼리 선호, 서브쿼리 vs CTE
- 분석 프레임워크: 가설 검증 방식, 통계적 사고
- 시각화 선호: 도구 선택(Tableau, plotly 등), 청중 의식
""",
    "general": "",
}

_WORK_BUILD_PROMPT = """\
다음은 한 팀원의 Slack 메시지 분석 결과입니다. 이를 바탕으로 '{name}'의 업무 역량 프로필(Part A)을 **한국어 마크다운**으로 작성하세요.

분석 결과:
{analysis}

출력 형식: ### 주요 업무 역할 / ### 기술 스택 / ### 업무 처리 스타일 / ### 업무 커뮤니케이션 패턴
마크다운 코드블록 래퍼 없이 마크다운 내용만 출력하세요.
"""

_PERSONA_EXTRACT_PROMPT = """\
다음 팀원의 Slack 메시지를 분석해 아래 6개 차원의 페르소나 패턴을 **구조화된 데이터**로 추출하세요.

[표현 스타일] 고빈도 단어, 문장 길이, 이모지 사용, 공식성(1-5)
[의사결정 패턴] 행동 유발 요인, 회피 유발 요인, 반대 표현 방식(실제 메시지 인용)
[대인관계] 상사/동료/부하에게 각각 어떻게 다르게 행동하는가
[절대 원칙] 어떤 상황에서도 변하지 않는 행동 3-5가지 (형용사 금지, 구체적 행동)
[핵심 정체성] 스스로를 어떻게 인식하는가, 무엇을 중요하게 여기는가
[압박 반응] 마감·비판·책임 전가 상황에서의 구체적 행동 변화

모든 주장에 실제 메시지를 인용해 근거를 제시하세요.
"""

_PERSONA_BUILD_PROMPT = """\
다음은 한 팀원의 Slack 메시지 페르소나 분석 결과입니다. '{name}'의 페르소나 프로필(Part B)을 **한국어 마크다운**으로 작성하세요.

분석 결과:
{analysis}

출력 형식: Layer 0 절대 행동 원칙 / Layer 1 핵심 정체성 / Layer 2 표현 스타일 / Layer 3 의사결정·문제해결 / Layer 4 대인관계 패턴 / 실행 규칙
마크다운 코드블록 래퍼 없이 마크다운 내용만 출력하세요.
"""


def extract_work_patterns(
    messages: list[dict],
    model_client,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
    role: str = "general",
) -> str:
    """Stage 1: 메시지에서 업무 패턴을 구조화 데이터로 추출.

    role: "backend", "frontend", "ml", "pm", "data", "general" 중 하나.
    """
    msg_block = _format_messages_for_llm(messages, max_messages)
    role_prompt = ROLE_SPECIFIC_PROMPTS.get(role, "")
    prompt = _WORK_EXTRACT_PROMPT + role_prompt + f"\n\n## 메시지\n\n{msg_block}"
    return model_client.call(
        system_prompt=_WORK_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )


def build_work_md(analysis: str, display_name: str, model_client) -> str:
    """Stage 2: 업무 패턴 분석 결과를 work.md 포맷으로 변환."""
    prompt = _WORK_BUILD_PROMPT.format(name=display_name, analysis=analysis)
    return model_client.call(
        system_prompt=_WORK_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )


def extract_persona_patterns(
    messages: list[dict],
    model_client,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
    impression: str = "",
) -> str:
    """Stage 1: 메시지에서 페르소나 패턴을 구조화 데이터로 추출."""
    msg_block = _format_messages_for_llm(messages, max_messages)
    impression_ctx = f"\n\n[팀원 인상 메모: {impression}]\n" if impression.strip() else ""
    prompt = _PERSONA_EXTRACT_PROMPT + impression_ctx + f"\n\n## 메시지\n\n{msg_block}"
    return model_client.call(
        system_prompt=_PERSONA_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )


def build_persona_md(analysis: str, display_name: str, model_client) -> str:
    """Stage 2: 페르소나 패턴 분석 결과를 persona.md 포맷으로 변환."""
    prompt = _PERSONA_BUILD_PROMPT.format(name=display_name, analysis=analysis)
    return model_client.call(
        system_prompt=_PERSONA_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )


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
    raw_messages: list[dict] | None = None,
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
        "message_count": len(raw_messages) if raw_messages else 0,
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


# ── 추출 오케스트레이터 ───────────────────────────────────────────────────────

def _run_extraction(
    members: list[dict],    # [{"user_id", "slug", "display_name", "role", "impression"}, ...]
    token: str,
    channels: list[str] | None,
    q: stdlib_queue.SimpleQueue,
    team_skills_dir: Path,
    max_collect: int = _DEFAULT_MAX_COLLECT,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
) -> None:
    """팀원 목록을 순차 처리하며 SSE 이벤트를 q에 emit.

    각 팀원당: 수집 → 업무분석 → 페르소나분석 → 파일생성
    오류 발생 시 해당 멤버 스킵 후 다음 멤버 계속 진행.
    마지막에 None sentinel을 q에 넣어 SSE generator 종료 신호 전달.
    """
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
            role = member.get("role", "general")
            impression = member.get("impression", "")

            # 1. 메시지 수집
            emit({"type": "collecting", "slug": slug, "current": i, "total": total})
            try:
                messages = collect_user_messages(user_id, token, channels=channels, max_collect=max_collect)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 메시지 수집 실패 — {e}", "slug": slug})
                continue

            if not messages:
                emit({"type": "error", "message": f"{slug}: 필터링 후 메시지가 없습니다.", "slug": slug})
                continue

            # 2. 업무 패턴 추출 (Stage 1)
            emit({"type": "analyzing", "slug": slug, "step": "work_extract", "current": i, "total": total})
            try:
                work_analysis = extract_work_patterns(messages, model_client, max_messages=max_messages, role=role)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 업무 패턴 추출 실패 — {e}", "slug": slug})
                continue

            # 3. 업무 프로필 빌드 (Stage 2)
            emit({"type": "analyzing", "slug": slug, "step": "work_build", "current": i, "total": total})
            try:
                part_a = build_work_md(work_analysis, display_name, model_client)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 업무 프로필 생성 실패 — {e}", "slug": slug})
                continue

            # 4. 페르소나 패턴 추출 (Stage 1)
            emit({"type": "analyzing", "slug": slug, "step": "persona_extract", "current": i, "total": total})
            try:
                persona_analysis = extract_persona_patterns(
                    messages, model_client, max_messages=max_messages,
                    impression=impression,
                )
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 페르소나 패턴 추출 실패 — {e}", "slug": slug})
                continue

            # 5. 페르소나 빌드 (Stage 2)
            emit({"type": "analyzing", "slug": slug, "step": "persona_build", "current": i, "total": total})
            try:
                part_b = build_persona_md(persona_analysis, display_name, model_client)
            except Exception as e:
                emit({"type": "error", "message": f"{slug}: 페르소나 생성 실패 — {e}", "slug": slug})
                continue

            # 6. 파일 생성
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
