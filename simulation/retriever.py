"""simulation/retriever.py — BM25 기반 Slack 메시지 검색."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class SlackRetriever:
    """멤버별 Slack 메시지를 BM25로 검색합니다.

    세션 시작 시 1회 인덱스를 메모리에 빌드하고, search()로 관련 메시지를 반환합니다.
    """

    def __init__(self, team_skills_dir: Path) -> None:
        # slug → (BM25Okapi 인스턴스, 원본 메시지 리스트)
        self._indexes: dict[str, tuple[BM25Okapi, list[str]]] = {}
        self._build_all(team_skills_dir)

    def _build_all(self, team_skills_dir: Path) -> None:
        for member_dir in sorted(team_skills_dir.iterdir()):
            if not member_dir.is_dir():
                continue
            slug = member_dir.name
            messages_path = member_dir / "slack_messages.json"
            if not messages_path.exists():
                continue
            try:
                data = json.loads(messages_path.read_text(encoding="utf-8"))
                messages = [
                    m["content"]
                    for m in data.get("messages", [])
                    if m.get("content", "").strip()
                ]
                if not messages:
                    continue
                corpus = [self._tokenize(m) for m in messages]
                self._indexes[slug] = (BM25Okapi(corpus), messages)
                logger.info("SlackRetriever: %s — %d개 메시지 인덱싱 완료", slug, len(messages))
            except Exception as e:
                logger.warning("SlackRetriever: %s 로드 실패 — %s", slug, e)

    def search(self, slug: str, query: str, top_k: int = 5) -> list[str]:
        """slug 멤버의 Slack 메시지 중 query와 관련된 상위 top_k개를 반환합니다.

        관련 메시지가 없거나 slug가 없으면 빈 리스트를 반환합니다.
        score > 0인 결과만 반환합니다.
        """
        if slug not in self._indexes:
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []
        bm25, messages = self._indexes[slug]
        scores = bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [messages[i] for i in ranked[:top_k] if scores[i] > 0]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """공백 분리 + 소문자 변환. 한국어 Slack 메시지에 충분합니다."""
        return text.lower().split()
