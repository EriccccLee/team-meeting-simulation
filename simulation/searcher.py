"""
PreSearcher
───────────
회의 시작 전 DuckDuckGo 웹 검색을 수행해 결과를 마크다운으로 반환.
duckduckgo-search 라이브러리 사용 (무료, API 키 불필요).
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

_MAX_RESULTS = 6
_MAX_BODY_CHARS = 350


def pre_search(topic: str, max_results: int = _MAX_RESULTS) -> str | None:
    """topic 을 DuckDuckGo 로 검색하고 결과를 마크다운 문자열로 반환.

    Args:
        topic:       회의 안건 텍스트 (검색어로 사용)
        max_results: 최대 결과 수

    Returns:
        마크다운 형식의 검색 결과 문자열, 실패/결과 없음 시 None.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore[no-redef]
        except ImportError:
            logger.warning("ddgs 미설치 — 웹 검색 비활성 (pip install ddgs)")
            return None

    query = topic
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region="kr-kr"))
    except Exception as e:
        logger.error("DuckDuckGo 검색 실패: %s", e)
        return None

    if not results:
        logger.info("검색 결과 없음: %r", query)
        return None

    lines = [
        "## 웹 검색 결과\n",
        f"**검색어**: `{query}`  ",
        f"**검색일**: {date.today().isoformat()}\n",
    ]
    for i, r in enumerate(results, 1):
        title = r.get("title", "제목 없음")
        body = (r.get("body", "") or "")[:_MAX_BODY_CHARS]
        href = r.get("href", "")
        lines.append(f"### {i}. {title}\n{body}\n\n> 출처: {href}\n")

    return "\n".join(lines)
