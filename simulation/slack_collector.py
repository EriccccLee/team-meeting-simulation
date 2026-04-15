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
import logging
import queue as stdlib_queue
import re
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
        result.append(
            {
                "user_id": user_id,
                "display_name": display_name,
                "message_count": count,
                "suggested_slug": generate_slug(display_name),
            }
        )

    return sorted(result, key=lambda x: x["message_count"], reverse=True)
