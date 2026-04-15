"""
ClaudeCodeModelClient
─────────────────────
claude -p subprocess 래퍼. Claude Code 의 기존 인증을 재사용하므로
별도 API 키가 필요 없습니다.

plan.md §4-1 참조.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)


def _decode(data: bytes | None) -> str:
    """bytes → str. UTF-8 실패 시 cp949(한국어 Windows 기본)로 재시도."""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp949", errors="replace")

# Windows 에서 npm 전역 설치된 claude 는 claude.CMD 파일입니다.
# .CMD 파일은 cmd.exe 를 통해야 실행되므로, Windows 에서는 항상
# ["cmd.exe", "/c", <exe>] 접두사를 붙이고 shell=False 로 실행합니다.
# 대화 내용은 긴 멀티라인 텍스트이므로 positional arg 대신 stdin 으로 전달합니다.
_CLAUDE_EXE: str = shutil.which("claude") or "claude"
_IS_WINDOWS: bool = sys.platform == "win32"


class ClaudeCodeModelClient:
    """
    `claude -p <conversation> --system-prompt <system>` 를 subprocess 로 호출해
    stdout 을 반환합니다.

    타임아웃 시 1회 재시도, 그 이후 실패 시 TimeoutError 를 raise 합니다.
    non-zero exit 시 RuntimeError 를 raise 합니다.
    """

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout

    # ── Public API ────────────────────────────────────────────────────────────

    def call(self, system_prompt: str, messages: list[dict]) -> str:
        """
        Args:
            system_prompt: 에이전트 system prompt 전문
            messages:      대화 히스토리 (speaker/slug/content 키 포함)

        Returns:
            LLM 응답 텍스트 (strip 적용)
        """
        conversation = self._serialize(messages)
        last_err: Exception | None = None

        for attempt in range(2):
            try:
                return self._run(system_prompt, conversation)
            except TimeoutError as e:
                last_err = e
                if attempt == 0:
                    logger.warning("claude -p timed out (attempt 1), retrying…")
            except RuntimeError:
                raise  # 재시도 불필요 — 즉시 상위로 전파

        raise last_err  # type: ignore[misc]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self, system_prompt: str, conversation: str) -> str:
        # system_prompt 를 임시 파일로 저장 후 --system-prompt-file 로 전달합니다.
        # 이유: --system-prompt 인자로 넘기면 Windows 커맨드라인 길이 제한(32767자)
        #       초과 오류("명령줄이 너무 깁니다.")가 발생합니다.
        sp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        )
        try:
            sp_file.write(system_prompt)
            sp_file.close()

            base_cmd = [
                "-p",
                "--system-prompt-file", sp_file.name,
                "--output-format", "text",
                "--tools", "",               # 불필요한 도구 비활성화
                "--no-session-persistence",  # 세션 저장 불필요, 속도 향상
            ]
            if _IS_WINDOWS:
                cmd = ["cmd.exe", "/c", _CLAUDE_EXE] + base_cmd
            else:
                cmd = [_CLAUDE_EXE] + base_cmd

            try:
                result = subprocess.run(
                    cmd,
                    input=conversation.encode("utf-8"),  # stdin 으로 대화 내용 전달
                    capture_output=True,
                    timeout=self.timeout,
                    shell=False,
                )
            except subprocess.TimeoutExpired as e:
                raise TimeoutError(f"claude -p timed out after {self.timeout}s") from e
        finally:
            os.unlink(sp_file.name)  # 임시 파일 항상 삭제

        stdout = _decode(result.stdout)
        stderr = _decode(result.stderr)

        if result.returncode != 0:
            logger.error("claude -p stderr: %s", stderr.strip())
            raise RuntimeError(
                f"claude -p exited with code {result.returncode}: {stderr.strip()}"
            )

        return stdout.strip()

    @staticmethod
    def _serialize(messages: list[dict]) -> str:
        """대화 히스토리를 '화자: 내용\\n화자: 내용' 형식으로 직렬화."""
        lines: list[str] = []
        for msg in messages:
            if msg.get("slug") == "__moderator__":
                speaker = "[사회자]"
            else:
                speaker = msg.get("speaker") or msg.get("slug") or "Unknown"
            lines.append(f"{speaker}: {msg['content']}")
        return "\n".join(lines)
