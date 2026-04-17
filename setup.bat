@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ========================================
echo    Team Meeting Simulation -- Setup
echo ========================================
echo.

:: ── 1. 사전 검사 ──────────────────────────────────────────────────────────────

echo [검사 1/3] Python 버전 확인...

python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python을 찾을 수 없습니다.
    echo        Python 3.10 이상을 설치해주세요: https://python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PYTHON_VERSION=%%V
for /f "tokens=1,2 delims=." %%A in ("!PYTHON_VERSION!") do (
    set PYTHON_MAJOR=%%A
    set PYTHON_MINOR=%%B
)

if !PYTHON_MAJOR! LSS 3 (
    echo [오류] Python !PYTHON_VERSION! 감지 -- 3.10 이상이 필요합니다.
    echo        https://python.org 에서 최신 버전을 설치해주세요.
    pause
    exit /b 1
)
if !PYTHON_MAJOR! EQU 3 if !PYTHON_MINOR! LSS 10 (
    echo [오류] Python !PYTHON_VERSION! 감지 -- 3.10 이상이 필요합니다.
    echo        https://python.org 에서 최신 버전을 설치해주세요.
    pause
    exit /b 1
)

echo        [OK] Python !PYTHON_VERSION!

:: ────────────────────────────────────────────────────────────────────────────

echo [검사 2/3] Node.js 버전 확인...

node --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Node.js를 찾을 수 없습니다.
    echo        Node.js 18 이상을 설치해주세요: https://nodejs.org
    pause
    exit /b 1
)

for /f "tokens=1 delims=." %%V in ('node --version') do (
    set NODE_MAJOR=%%V
    set NODE_MAJOR=!NODE_MAJOR:v=!
)

if !NODE_MAJOR! LSS 18 (
    echo [오류] Node.js v!NODE_MAJOR! 감지 -- 18 이상이 필요합니다.
    echo        https://nodejs.org 에서 최신 LTS 버전을 설치해주세요.
    pause
    exit /b 1
)

for /f %%V in ('node --version') do echo        [OK] Node.js %%V

:: ────────────────────────────────────────────────────────────────────────────

echo [검사 3/3] Claude Code CLI 확인...

where claude >nul 2>&1
if errorlevel 1 (
    :: .cmd 확장자로도 시도
    where claude.cmd >nul 2>&1
    if errorlevel 1 (
        echo [오류] Claude Code CLI를 찾을 수 없습니다.
        echo        설치: https://claude.ai/code
        echo        설치 후 'claude' 명령으로 로그인까지 완료해주세요.
        pause
        exit /b 1
    )
)

echo        [OK] Claude Code CLI 감지
echo        ※ 'claude' 로그인이 완료된 상태여야 합니다.
echo.

:: ── 2. Python 가상환경 ─────────────────────────────────────────────────────────

if exist ".venv\" (
    echo [스킵] .venv 이미 존재합니다.
) else (
    echo [1/3] Python 가상환경 생성 중...
    python -m venv .venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성 실패.
        pause
        exit /b 1
    )
    echo       [OK] .venv 생성 완료
)

:: ── 3. Python 의존성 ───────────────────────────────────────────────────────────

echo [2/3] Python 패키지 설치 중...
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [오류] Python 패키지 설치 실패.
    pause
    exit /b 1
)
echo       [OK] Python 패키지 설치 완료

:: ── 4. Node.js 의존성 ─────────────────────────────────────────────────────────

if exist "frontend\node_modules\" (
    echo [스킵] frontend\node_modules 이미 존재합니다.
) else (
    echo [3/3] Node.js 패키지 설치 중...
    pushd frontend
    npm install --silent
    if errorlevel 1 (
        popd
        echo [오류] Node.js 패키지 설치 실패.
        pause
        exit /b 1
    )
    popd
    echo       [OK] Node.js 패키지 설치 완료
)

:: ── 5. .env 파일 ───────────────────────────────────────────────────────────────

if exist ".env" (
    echo [스킵] .env 이미 존재합니다.
) else (
    copy .env.example .env >nul
    echo [완료] .env 파일 생성됨 ^(Slack 기능 사용 시 내용을 채워주세요^)
)

:: ── 완료 ──────────────────────────────────────────────────────────────────────

echo.
echo ========================================
echo    설치 완료!
echo ========================================
echo.
echo   Slack 팀원 추출 기능을 사용하려면:
echo   .env 파일에 SLACK_BOT_TOKEN과 SLACK_CHANNELS를 입력하세요.
echo.
echo   서버 실행:
echo   start.bat
echo.
pause
