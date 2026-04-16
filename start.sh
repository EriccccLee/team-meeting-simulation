#!/usr/bin/env bash
set -e

# ── 색상 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}   Team Meeting Simulation — Start${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ── .venv 확인 ────────────────────────────────────────────────────────────────

if [ ! -d ".venv" ]; then
    echo -e "${RED}[오류] .venv 폴더가 없습니다.${NC}"
    echo "       먼저 setup을 실행해주세요: ./setup.sh"
    exit 1
fi

# ── 기존 프로세스 정리 ────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo -e "${YELLOW}서버를 종료합니다...${NC}"
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    echo -e "${GREEN}종료 완료.${NC}"
}
trap cleanup EXIT INT TERM

# ── 백엔드 서버 시작 ──────────────────────────────────────────────────────────

echo -e "${CYAN}[1/2]${NC} 백엔드 서버 시작 중 (port 8000)..."
source .venv/bin/activate
uvicorn web.app:app --port 8000 --log-level warning &
BACKEND_PID=$!
echo -e "      ${GREEN}✓ 백엔드 PID: $BACKEND_PID${NC}"

# ── 프론트엔드 서버 시작 ──────────────────────────────────────────────────────

echo -e "${CYAN}[2/2]${NC} 프론트엔드 서버 시작 중 (port 5173)..."
(cd frontend && npm run dev -- --port 5173 2>/dev/null) &
FRONTEND_PID=$!
echo -e "      ${GREEN}✓ 프론트엔드 PID: $FRONTEND_PID${NC}"

# ── 브라우저 오픈 ─────────────────────────────────────────────────────────────

echo ""
echo "  서버 초기화 대기 중..."
sleep 3

URL="http://localhost:5173"

# macOS
if command -v open &>/dev/null; then
    open "$URL"
# Linux (GNOME, KDE, etc.)
elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"
fi

# ── 서버 정보 출력 ────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   서버 실행 중${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  프론트엔드:  ${CYAN}http://localhost:5173${NC}"
echo -e "  백엔드 API:  ${CYAN}http://localhost:8000${NC}"
echo ""
echo -e "  ${YELLOW}Ctrl+C 로 모든 서버를 종료합니다.${NC}"
echo ""

# ── 서버 유지 ─────────────────────────────────────────────────────────────────

wait
