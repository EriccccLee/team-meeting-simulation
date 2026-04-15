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


# ── Slack API: 메시지 수집 ────────────────────────────────────────────────────

def collect_user_messages(
    user_id: str,
    channels: list[str],
    token: str,
) -> list[str]:
    """지정 user_id가 보낸 메시지 중 노이즈를 제거한 텍스트 목록 반환.

    여러 채널을 순회하며 수집하고, _is_noise() 필터를 적용한다.
    """
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
