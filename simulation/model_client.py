"""
ClaudeCodeModelClient
─────────────────────
claude -p subprocess 래퍼. Claude Code 의 기존 인증을 재사용하므로
별도 API 키가 필요 없습니다.

plan.md §4-1 참조.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

logger = logging.getLogger(__name__)


def decode_bytes(data: bytes | None) -> str:
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


def run_claude_prompt(
    args: list[str],
    *,
    stdin: bytes | None = None,
    timeout: int = 180,
) -> str:
    """
    `claude -p` 를 실행하고 stdout을 반환합니다.

    Args:
        args:    claude 실행 후 이어지는 인자 목록
        stdin:   표준 입력 바이트 (선택)
        timeout: 타임아웃 (초)

    Returns:
        stdout 문자열 (strip 처리됨)

    Raises:
        TimeoutError: 타임아웃 초과
        RuntimeError: non-zero exit code
    """
    exe = _CLAUDE_EXE
    if _IS_WINDOWS:
        cmd = ["cmd.exe", "/c", exe]
    else:
        cmd = [exe]
    cmd += args

    try:
        result = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"claude timed out after {timeout}s")

    stdout = decode_bytes(result.stdout)
    stderr = decode_bytes(result.stderr)

    if result.returncode != 0:
        logger.error("claude stderr: %s", stderr.strip())
        raise RuntimeError(
            f"claude exited with code {result.returncode}: {stderr.strip()}"
        )

    return stdout.strip()


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

    def call(
        self,
        system_prompt: str,
        messages: list[dict],
        on_tool_use: Callable[[dict], None] | None = None,
    ) -> str:
        """
        Args:
            system_prompt: 에이전트 system prompt 전문
            messages:      대화 히스토리 (speaker/slug/content 키 포함)
            on_tool_use:   도구 사용 감지 시 호출되는 콜백 (선택)
                           {"name": "WebSearch", "input": {...}} 형태의 dict 전달

        Returns:
            LLM 응답 텍스트 (strip 적용)
        """
        conversation = self._serialize(messages)
        last_err: Exception | None = None

        for attempt in range(2):
            try:
                return self._run(system_prompt, conversation, on_tool_use=on_tool_use)
            except TimeoutError as e:
                last_err = e
                if attempt == 0:
                    logger.warning("claude -p timed out (attempt 1), retrying…")
            except RuntimeError:
                raise  # 재시도 불필요 — 즉시 상위로 전파

        raise last_err  # type: ignore[misc]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(
        self,
        system_prompt: str,
        conversation: str,
        on_tool_use: Callable[[dict], None] | None = None,
    ) -> str:
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
                "--output-format", "stream-json",  # NDJSON — tool use 감지 가능
                "--verbose",                        # stream-json 은 --verbose 필수
                "--tools", "",                      # 도구 비활성화 (실제 검색은 pre-search 단계에서 처리)
                "--no-session-persistence",
            ]
            if _IS_WINDOWS:
                cmd = ["cmd.exe", "/c", _CLAUDE_EXE] + base_cmd
            else:
                cmd = [_CLAUDE_EXE] + base_cmd

            try:
                result = subprocess.run(
                    cmd,
                    input=conversation.encode("utf-8"),
                    capture_output=True,
                    timeout=self.timeout,
                    shell=False,
                )
            except subprocess.TimeoutExpired as e:
                raise TimeoutError(f"claude -p timed out after {self.timeout}s") from e
        finally:
            os.unlink(sp_file.name)

        stdout = decode_bytes(result.stdout)
        stderr = decode_bytes(result.stderr)

        if result.returncode != 0:
            logger.error("claude -p stderr: %s", stderr.strip())
            raise RuntimeError(
                f"claude -p exited with code {result.returncode}: {stderr.strip()}"
            )

        return self._parse_stream_json(stdout, on_tool_use)

    @staticmethod
    def _parse_stream_json(
        stdout: str,
        on_tool_use: Callable[[dict], None] | None = None,
    ) -> str:
        """stream-json NDJSON 출력을 파싱해 최종 응답 텍스트를 반환.

        tool_use 콜백은 모든 라인 파싱 완료 후 호출됩니다.
        result 의 usage.server_tool_use 를 확인해 실제 검색이 실행됐는지 판단하고
        failed 필드를 포함해 콜백을 호출합니다.
        """
        result_text = ""
        result_usage: dict = {}
        pending_tool_uses: list[dict] = []   # 콜백은 모든 파싱 후 일괄 호출

        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            obj_type = obj.get("type")

            if obj_type == "assistant":
                content = obj.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            pending_tool_uses.append({
                                "name": block.get("name", "Unknown"),
                                "input": block.get("input", {}),
                            })
            elif obj_type == "result" and obj.get("subtype") == "success":
                result_text = obj.get("result", "")
                result_usage = obj.get("usage", {})

        # 실제 실행 횟수로 실패 여부 판단
        if on_tool_use and pending_tool_uses:
            server_use = result_usage.get("server_tool_use", {})
            web_search_count = server_use.get("web_search_requests", -1)
            web_fetch_count = server_use.get("web_fetch_requests", -1)

            for tool_event in pending_tool_uses:
                name = tool_event["name"]
                failed = False
                if name == "WebSearch" and web_search_count == 0:
                    failed = True
                elif name == "WebFetch" and web_fetch_count == 0:
                    failed = True
                on_tool_use({**tool_event, "failed": failed})

        # stream-json 형식이 예상과 다를 경우 raw stdout 으로 fallback
        return result_text.strip() or stdout.strip()

    @staticmethod
    def _serialize(messages: list[dict]) -> str:
        """대화 히스토리를 '화자: 내용\\n화자: 내용' 형식으로 직렬화."""
        lines: list[str] = []
        for msg in messages:
            slug = msg.get("slug")
            if slug == "__moderator__":
                speaker = "[사회자]"
            elif slug == "__memory__":
                speaker = "[과거 발언 참고]"
            else:
                speaker = msg.get("speaker") or slug or "Unknown"
            lines.append(f"{speaker}: {msg['content']}")
        return "\n".join(lines)
