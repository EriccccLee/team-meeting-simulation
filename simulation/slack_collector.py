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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

    # 너무 짧으면 노이즈 (1자 이하)
    if len(no_emoji) <= 1:
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
    client = RateLimitedSlackClient(token)
    user_counts: dict[str, int] = {}

    for channel_id in channels:
        try:
            cursor = None
            while True:
                resp = client.call("conversations_history", channel=channel_id, limit=200) if cursor is None else \
                       client.call("conversations_history", channel=channel_id, cursor=cursor, limit=200)
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
            user_info = client.call("users_info", user=user_id)["user"]
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

    def _check(ch: dict) -> str | None:
        try:
            members = client.paginate(
                "conversations_members", "members",
                channel=ch["id"], limit=200,
            )
            return ch["id"] if user_id in members else None
        except SlackApiError:
            return None

    max_workers = min(len(channels), 5) if channels else 1
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_check, ch) for ch in channels]
    return [ch_id for f in futures if (ch_id := f.result()) is not None]


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
    seen_contents: set[str] = set()

    # Resolve channel names for LLM context
    channel_names: dict[str, str] = {}
    for ch_id in channels:
        try:
            info = client.call("conversations_info", channel=ch_id)
            channel_names[ch_id] = info.get("channel", {}).get("name", ch_id)
        except SlackApiError:
            channel_names[ch_id] = ch_id

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
                            if text not in seen_contents:
                                seen_contents.add(text)
                                messages.append({
                                    "content": text,
                                    "ts": msg.get("ts", ""),
                                    "channel": channel_id,
                                    "channel_name": channel_names.get(channel_id, channel_id),
                                    "is_thread_starter": bool(msg.get("reply_count", 0)),
                                    "is_thread_reply": False,
                                })
                next_cursor = (resp.get("response_metadata") or {}).get("next_cursor") or ""
                if next_cursor and len(messages) < max_collect:
                    cursor = next_cursor
                else:
                    break
            # 스레드 답장 수집 — 유저가 시작한 스레드에서 본인의 후속 답장 수집
            thread_starters = [m for m in messages if m.get("is_thread_starter") and m.get("channel") == channel_id]
            for ts_msg in thread_starters[:20]:  # 채널당 최대 20개 스레드
                if len(messages) >= max_collect:
                    break
                try:
                    replies = client.call("conversations_replies", channel=channel_id, ts=ts_msg["ts"], limit=200)
                    for reply in replies.get("messages", [])[1:]:  # [0]은 부모 메시지 (이미 수집됨)
                        if reply.get("user") == user_id and not reply.get("bot_id"):
                            text = reply.get("text", "").strip()
                            if text and not _is_noise(text) and text not in seen_contents:
                                seen_contents.add(text)
                                messages.append({
                                    "content": text,
                                    "ts": reply.get("ts", ""),
                                    "channel": channel_id,
                                    "channel_name": channel_names.get(channel_id, channel_id),
                                    "is_thread_starter": False,
                                    "is_thread_reply": True,
                                })
                except SlackApiError:
                    continue  # 개별 스레드 실패는 무시

        except SlackApiError as e:
            logger.warning(
                "채널 %s 메시지 수집 실패 (user=%s, 스킵): %s",
                channel_id, user_id, e,
            )
        if len(messages) >= max_collect:
            break

    messages.sort(key=lambda m: float(m.get("ts", "0")))
    return messages


# ── LLM 분석 프롬프트 (colleague-skill 기반) ──────────────────────────────────

_WORK_SYSTEM = "당신은 팀원 분석 전문가입니다. Slack 메시지를 기반으로 업무 프로필을 작성합니다."

_PERSONA_SYSTEM = "당신은 팀원 분석 전문가입니다. Slack 메시지를 기반으로 페르소나를 작성합니다."



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
        ch = m.get('channel_name', m.get('channel', ''))
        return f"[#{ch}] {m['content']}"

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


def _validate_llm_output(output: str, min_length: int = 50, context: str = "") -> str:
    """LLM 출력의 최소 품질을 검증. 부족하면 RuntimeError 발생."""
    if not output or not output.strip():
        raise RuntimeError(f"LLM 출력이 비어있습니다. ({context})")
    stripped = output.strip()
    if len(stripped) < min_length:
        raise RuntimeError(
            f"LLM 출력이 너무 짧습니다 ({len(stripped)}자 < {min_length}자). ({context})"
        )
    # 거부/오류 응답 감지
    refusal_markers = ["cannot analyze", "분석할 수 없", "충분하지 않", "Unable to"]
    for marker in refusal_markers:
        if marker.lower() in stripped.lower()[:200]:
            raise RuntimeError(f"LLM이 분석을 거부했습니다: {stripped[:100]}... ({context})")
    return stripped


def extract_work_patterns(
    messages: list[dict],
    model_client,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
    role: str = "general",
    impression: str = "",
) -> str:
    """Stage 1: 메시지에서 업무 패턴을 구조화 데이터로 추출.

    role: "backend", "frontend", "ml", "pm", "data", "general" 중 하나.
    """
    msg_block = _format_messages_for_llm(messages, max_messages)
    role_prompt = ROLE_SPECIFIC_PROMPTS.get(role, "")
    impression_ctx = f"\n\n[팀원 인상 메모: {impression}]\n" if impression.strip() else ""
    prompt = _WORK_EXTRACT_PROMPT + role_prompt + impression_ctx + f"\n\n## 메시지\n\n{msg_block}"
    result = model_client.call(
        system_prompt=_WORK_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )
    return _validate_llm_output(result, min_length=100, context="work pattern extraction")


def build_work_md(analysis: str, display_name: str, model_client) -> str:
    """Stage 2: 업무 패턴 분석 결과를 work.md 포맷으로 변환."""
    prompt = _WORK_BUILD_PROMPT.format(name=display_name, analysis=analysis)
    result = model_client.call(
        system_prompt=_WORK_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )
    return _validate_llm_output(result, min_length=100, context="work profile build")


def extract_persona_patterns(
    messages: list[dict],
    model_client,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
    impression: str = "",
    role: str = "general",
) -> str:
    """Stage 1: 메시지에서 페르소나 패턴을 구조화 데이터로 추출."""
    msg_block = _format_messages_for_llm(messages, max_messages)
    role_ctx = f"\n\n[추론된 직무: {role}]\n" if role != "general" else ""
    impression_ctx = f"\n\n[팀원 인상 메모: {impression}]\n" if impression.strip() else ""
    prompt = _PERSONA_EXTRACT_PROMPT + role_ctx + impression_ctx + f"\n\n## 메시지\n\n{msg_block}"
    result = model_client.call(
        system_prompt=_PERSONA_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )
    return _validate_llm_output(result, min_length=100, context="persona pattern extraction")


def build_persona_md(analysis: str, display_name: str, model_client) -> str:
    """Stage 2: 페르소나 패턴 분석 결과를 persona.md 포맷으로 변환."""
    prompt = _PERSONA_BUILD_PROMPT.format(name=display_name, analysis=analysis)
    result = model_client.call(
        system_prompt=_PERSONA_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )
    return _validate_llm_output(result, min_length=100, context="persona profile build")


# ── 파일 쓰기 ─────────────────────────────────────────────────────────────────

_slug_lock = threading.Lock()


def _unique_slug_in_run(slug: str, claimed: set[str]) -> str:
    """같은 추출 실행 내에서 이미 claim된 slug에만 _N suffix 부여.

    반드시 _slug_lock 보유 상태에서 호출해야 한다.
    """
    candidate = slug
    n = 2
    while candidate in claimed:
        candidate = f"{slug}_{n}"
        n += 1
    claimed.add(candidate)
    return candidate


def write_profile(
    slug: str,
    display_name: str,
    part_a: str,
    part_b: str,
    team_skills_dir: Path,
    role: str = "general",
    raw_messages: list[dict] | None = None,
    claimed_slugs: set[str] | None = None,
) -> Path:
    """팀원 프로필 파일 세트를 team-skills/{slug}/ 에 생성 또는 덮어씀.

    같은 추출 실행 내에서 slug가 충돌하면 _2, _3, ... suffix 부여.
    이전 실행으로 생성된 기존 디렉터리는 재추출 시 덮어씌움.

    Args:
        claimed_slugs: 현재 실행에서 claim된 slug 집합. 제공 시 slug 중복 방지,
                       None이면 slug를 그대로 사용.

    Returns:
        생성된 멤버 디렉터리 Path
    """
    if claimed_slugs is not None:
        with _slug_lock:
            unique = _unique_slug_in_run(slug, claimed_slugs)
    else:
        unique = slug
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
        "role": role,
        "persona_summary": [],
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


# ── 역할 자동 추론 ───────────────────────────────────────────────────────────

_ROLE_INFER_SYSTEM = "당신은 Slack 메시지를 보고 팀원의 직무 역할을 판단하는 전문가입니다."

_ROLE_INFER_PROMPT = """\
아래는 팀원의 Slack 메시지 샘플입니다. 이 사람의 주요 직무를 다음 중 **하나의 영문 키워드**로만 답하세요:

backend, frontend, ml, pm, data, general

판단 기준:
- backend: 서버 API, DB, 인프라, Docker, 배포 관련 발언
- frontend: UI, 컴포넌트, 웹, React/Vue 관련 발언
- ml: 모델, 학습, 임베딩, 파이프라인, AI/ML 관련 발언
- pm: 기획, 스펙, 로드맵, 우선순위 관련 발언
- data: SQL, 분석, 지표, 대시보드 관련 발언
- general: 위 카테고리에 해당하지 않거나 불명확한 경우

단어 하나만 출력하세요.

## 메시지 샘플
{messages}"""

_ROLE_INFER_VALID = {"backend", "frontend", "ml", "pm", "data", "general"}


def infer_role(messages: list[dict], model_client, sample_size: int = 40) -> str:
    """메시지 샘플로 직무 역할을 자동 추론. 실패 시 'general' 반환."""
    sample = messages[:sample_size]
    msg_block = _format_messages_for_llm(sample, max_messages=sample_size)
    prompt = _ROLE_INFER_PROMPT.format(messages=msg_block)
    try:
        result = model_client.call(
            system_prompt=_ROLE_INFER_SYSTEM,
            messages=[{"slug": "user", "speaker": "user", "content": prompt}],
        )
        role = result.strip().lower().split()[0] if result.strip() else "general"
        return role if role in _ROLE_INFER_VALID else "general"
    except Exception as e:
        logger.warning("역할 추론 실패 — 'general' 사용: %s", e)
        return "general"


# ── 추출 오케스트레이터 ───────────────────────────────────────────────────────

_PERSONA_SUMMARY_SYSTEM = "당신은 팀원 소개 전문가입니다."

_PERSONA_SUMMARY_PROMPT = """\
다음은 팀원 {name}의 페르소나 프로필입니다.
이 사람의 핵심 특징을 **한국어 3줄**로 요약하세요.
각 줄은 완성된 문장으로, 처음 만나는 동료에게 소개하듯이 써주세요.
번호나 불릿 없이 줄바꿈으로 구분된 3줄만 출력하세요.

{persona_md}"""


def summarize_persona(persona_md: str, display_name: str, model_client) -> list[str]:
    """페르소나 마크다운을 LLM으로 3줄 요약."""
    prompt = _PERSONA_SUMMARY_PROMPT.format(name=display_name, persona_md=persona_md)
    result = model_client.call(
        system_prompt=_PERSONA_SUMMARY_SYSTEM,
        messages=[{"slug": "user", "speaker": "user", "content": prompt}],
    )
    lines = [l.strip() for l in result.splitlines() if l.strip()]
    return lines[:3]


def _process_one_member(
    member: dict,
    token: str,
    channels: list[str] | None,
    model_client,
    team_skills_dir: Path,
    max_collect: int,
    max_messages: int,
    emit,
    idx: int,
    total: int,
    claimed_slugs: set[str] | None = None,
) -> None:
    """단일 팀원의 전체 추출 파이프라인 (스레드 안전)."""
    user_id = member["user_id"]
    slug = member["slug"]
    display_name = member["display_name"]
    impression = member.get("impression", "")

    # 1. 메시지 수집
    emit({"type": "collecting", "slug": slug, "current": idx, "total": total})
    try:
        messages = collect_user_messages(
            user_id, token, channels=channels, max_collect=max_collect
        )
    except Exception as e:
        emit({"type": "error", "message": f"{slug}: 메시지 수집 실패 — {e}", "slug": slug})
        return

    if not messages:
        emit({"type": "error", "message": f"{slug}: 필터링 후 메시지가 없습니다.", "slug": slug})
        return

    # 1-b. 역할 자동 추론 (메시지 샘플 기반, 빠른 LLM 호출)
    role = infer_role(messages, model_client)
    logger.info("[%s] 자동 추론 역할: %s", slug, role)

    # 2. Stage 1 병렬: work_extract + persona_extract 동시 실행
    emit({"type": "analyzing", "slug": slug, "step": "work_extract", "current": idx, "total": total})
    emit({"type": "analyzing", "slug": slug, "step": "persona_extract", "current": idx, "total": total})
    try:
        with ThreadPoolExecutor(max_workers=2) as stage1_pool:
            work_fut = stage1_pool.submit(
                extract_work_patterns, messages, model_client, max_messages, role, impression
            )
            persona_fut = stage1_pool.submit(
                extract_persona_patterns, messages, model_client, max_messages, impression, role
            )
        work_analysis = work_fut.result()
        persona_analysis = persona_fut.result()
    except Exception as e:
        emit({"type": "error", "message": f"{slug}: 패턴 추출 실패 — {e}", "slug": slug})
        return

    # 3. Stage 2 병렬: work_build + persona_build 동시 실행
    emit({"type": "analyzing", "slug": slug, "step": "work_build", "current": idx, "total": total})
    emit({"type": "analyzing", "slug": slug, "step": "persona_build", "current": idx, "total": total})
    try:
        with ThreadPoolExecutor(max_workers=2) as stage2_pool:
            build_work_fut = stage2_pool.submit(
                build_work_md, work_analysis, display_name, model_client
            )
            build_persona_fut = stage2_pool.submit(
                build_persona_md, persona_analysis, display_name, model_client
            )
        part_a = build_work_fut.result()
        part_b = build_persona_fut.result()
    except Exception as e:
        emit({"type": "error", "message": f"{slug}: 프로필 생성 실패 — {e}", "slug": slug})
        return

    # 4. 파일 생성
    emit({"type": "writing", "slug": slug, "current": idx, "total": total})
    try:
        member_dir = write_profile(
            slug, display_name, part_a, part_b, team_skills_dir,
            role=role, raw_messages=messages, claimed_slugs=claimed_slugs,
        )
    except Exception as e:
        emit({"type": "error", "message": f"{slug}: 파일 저장 실패 — {e}", "slug": slug})
        return

    actual_slug = member_dir.name
    emit({"type": "member_done", "slug": actual_slug, "current": idx, "total": total})
    return actual_slug, display_name, part_b


def _run_extraction(
    members: list[dict],
    token: str,
    channels: list[str] | None,
    q: stdlib_queue.SimpleQueue,
    team_skills_dir: Path,
    max_collect: int = _DEFAULT_MAX_COLLECT,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
) -> None:
    """팀원 목록을 병렬 처리하며 SSE 이벤트를 q에 emit.

    멤버 간: ThreadPoolExecutor(max_workers=min(len(members), 3))
    멤버 내: Stage 1(work_extract+persona_extract) 병렬, Stage 2(work_build+persona_build) 병렬
    마지막에 None sentinel을 q에 넣어 SSE generator 종료 신호 전달.
    """
    from simulation.model_client import ClaudeCodeModelClient

    model_client = ClaudeCodeModelClient(timeout=300)
    total = len(members)

    def emit(event: dict) -> None:
        q.put(event)

    # 이번 실행의 slug claim 집합 — 실행 단위 격리
    claimed_slugs: set[str] = set()

    try:
        max_workers = min(total, 3)
        # future → (member, idx) 맵 — 실패 멤버 재시도 추적용
        future_to_member: dict = {}
        with ThreadPoolExecutor(max_workers=max_workers) as member_pool:
            for idx, member in enumerate(members, start=1):
                fut = member_pool.submit(
                    _process_one_member,
                    member, token, channels, model_client,
                    team_skills_dir, max_collect, max_messages,
                    emit, idx, total, claimed_slugs,
                )
                future_to_member[fut] = (member, idx)

        # 성공한 멤버의 (slug, display_name, part_b) 수집 + 실패 멤버 추적
        summaries_input: list[tuple[str, str, str]] = []
        failed_members: list[tuple[dict, int]] = []
        for f, (member, idx) in future_to_member.items():
            try:
                result = f.result()
                if result is not None:
                    summaries_input.append(result)
                else:
                    failed_members.append((member, idx))
            except Exception as e:
                logger.error("멤버 처리 중 예외: %s", e)
                failed_members.append((member, idx))

        # 실패 멤버 순차 재시도 — timeout을 420s로 상향 (동시 부하 없음)
        if failed_members:
            retry_client = ClaudeCodeModelClient(timeout=420)
            logger.info("실패 멤버 %d명 재시도 시작", len(failed_members))
            for member, idx in failed_members:
                emit({"type": "retry_member", "slug": member["slug"]})
                try:
                    result = _process_one_member(
                        member, token, channels, retry_client,
                        team_skills_dir, max_collect, max_messages,
                        emit, idx, total, claimed_slugs,
                    )
                    if result is not None:
                        summaries_input.append(result)
                except Exception as e:
                    logger.error("재시도 중 예외 (slug=%s): %s", member["slug"], e)

        # LLM 페르소나 요약 병렬 생성
        persona_summaries: dict[str, list[str]] = {}
        if summaries_input:
            def _summarize(slug: str, display_name: str, part_b: str) -> tuple[str, list[str]]:
                try:
                    return slug, summarize_persona(part_b, display_name, model_client)
                except Exception as e:
                    logger.warning("페르소나 요약 실패 (slug=%s): %s", slug, e)
                    return slug, []

            max_sum_workers = min(len(summaries_input), 3)
            with ThreadPoolExecutor(max_workers=max_sum_workers) as summary_pool:
                sum_futures = [summary_pool.submit(_summarize, *s) for s in summaries_input]
            for sf in sum_futures:
                try:
                    slug, summary = sf.result()
                    persona_summaries[slug] = summary
                except Exception as e:
                    logger.error("요약 future 처리 오류: %s", e)

        # persona_summary를 각 멤버의 meta.json에 저장 (SetupView 로드용)
        for actual_slug, summary in persona_summaries.items():
            meta_path = team_skills_dir / actual_slug / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["persona_summary"] = summary
                    meta_path.write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                except Exception as e:
                    logger.warning("persona_summary 저장 실패 (slug=%s): %s", actual_slug, e)

        emit({"type": "done", "persona_summaries": persona_summaries})

    except Exception as e:
        emit({"type": "error", "message": str(e)})
    finally:
        q.put(None)  # SSE generator 종료 신호
