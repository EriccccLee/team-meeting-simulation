#!/usr/bin/env bash
set -e

# ── 색상 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}   Team Meeting Simulation — Setup${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ── 1. 사전 검사 ──────────────────────────────────────────────────────────────

echo -e "${YELLOW}[검사 1/3]${NC} Python 버전 확인..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}[오류] Python을 찾을 수 없습니다.${NC}"
    echo "       Python 3.10 이상을 설치해주세요: https://python.org"
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    echo -e "${RED}[오류] Python $PYTHON_VERSION 감지 — 3.10 이상이 필요합니다.${NC}"
    echo "       https://python.org 에서 최신 버전을 설치해주세요."
    exit 1
fi

echo -e "       ${GREEN}✓ Python $PYTHON_VERSION${NC}"

# ────────────────────────────────────────────────────────────────────────────

echo -e "${YELLOW}[검사 2/3]${NC} Node.js 버전 확인..."

if ! command -v node &>/dev/null; then
    echo -e "${RED}[오류] Node.js를 찾을 수 없습니다.${NC}"
    echo "       Node.js 18 이상을 설치해주세요: https://nodejs.org"
    exit 1
fi

NODE_VERSION=$(node -e "process.stdout.write(process.version.slice(1).split('.')[0])")

if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}[오류] Node.js v$NODE_VERSION 감지 — 18 이상이 필요합니다.${NC}"
    echo "       https://nodejs.org 에서 최신 LTS 버전을 설치해주세요."
    exit 1
fi

echo -e "       ${GREEN}✓ Node.js v$(node --version | tr -d 'v')${NC}"

# ────────────────────────────────────────────────────────────────────────────

echo -e "${YELLOW}[검사 3/3]${NC} Claude Code CLI 확인..."

if ! command -v claude &>/dev/null; then
    echo -e "${RED}[오류] Claude Code CLI를 찾을 수 없습니다.${NC}"
    echo "       설치: https://claude.ai/code"
    echo "       설치 후 'claude' 명령으로 로그인까지 완료해주세요."
    exit 1
fi

echo -e "       ${GREEN}✓ Claude Code CLI 감지${NC}"
echo -e "       ${YELLOW}※ 'claude' 로그인이 완료된 상태여야 합니다.${NC}"

echo ""

# ── 2. Python 가상환경 ─────────────────────────────────────────────────────────

if [ -d ".venv" ]; then
    echo -e "${GREEN}[스킵]${NC} .venv 이미 존재합니다."
else
    echo -e "${CYAN}[1/3]${NC} Python 가상환경 생성 중..."
    "$PYTHON_CMD" -m venv .venv
    echo -e "      ${GREEN}✓ .venv 생성 완료${NC}"
fi

# ── 3. Python 의존성 ───────────────────────────────────────────────────────────

echo -e "${CYAN}[2/3]${NC} Python 패키지 설치 중..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo -e "      ${GREEN}✓ Python 패키지 설치 완료${NC}"

# ── 4. Node.js 의존성 ─────────────────────────────────────────────────────────

if [ -d "frontend/node_modules" ]; then
    echo -e "${GREEN}[스킵]${NC} frontend/node_modules 이미 존재합니다."
else
    echo -e "${CYAN}[3/3]${NC} Node.js 패키지 설치 중..."
    (cd frontend && npm install --silent)
    echo -e "      ${GREEN}✓ Node.js 패키지 설치 완료${NC}"
fi

# ── 5. .env 파일 ───────────────────────────────────────────────────────────────

if [ -f ".env" ]; then
    echo -e "${GREEN}[스킵]${NC} .env 이미 존재합니다."
else
    cp .env.example .env
    echo -e "${GREEN}[완료]${NC} .env 파일 생성됨 (Slack 기능 사용 시 내용을 채워주세요)"
fi

# ── 완료 ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   설치 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Slack 팀원 추출 기능을 사용하려면:"
echo "  .env 파일에 SLACK_BOT_TOKEN과 SLACK_CHANNELS를 입력하세요."
echo ""
echo "  서버 실행:"
echo -e "  ${CYAN}./start.sh${NC}"
echo ""
