@echo off
setlocal
cd /d "%~dp0"

echo.
echo ========================================
echo    Team Meeting Simulation -- Start
echo ========================================
echo.

:: ── .venv 확인 ────────────────────────────────────────────────────────────────

if not exist ".venv\" (
    echo [오류] .venv 폴더가 없습니다.
    echo        먼저 setup을 실행해주세요: setup.bat
    pause
    exit /b 1
)

:: 포트 정리 ─────────────────────────────────────────────────────────────────

echo 기존 포트 정리 중 (8000, 5173)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 "') do taskkill /F /PID %%a >nul 2>&1

:: ── 백엔드 서버 시작 ──────────────────────────────────────────────────────────

echo [1/2] 백엔드 서버 시작 중 (port 8000)...
start "Backend - Team Meeting" cmd /k "call .venv\Scripts\activate && uvicorn web.app:app --port 8000"
echo       [OK] 백엔드 창 열림

:: ── 프론트엔드 서버 시작 ──────────────────────────────────────────────────────

echo [2/2] 프론트엔드 서버 시작 중 (port 5173)...
start "Frontend - Team Meeting" cmd /k "cd frontend && npm run dev"
echo       [OK] 프론트엔드 창 열림

:: ── 브라우저 오픈 ─────────────────────────────────────────────────────────────

echo.
echo   서버 초기화 대기 중...
timeout /t 4 /nobreak >nul

start http://localhost:5173

:: ── 서버 정보 출력 ────────────────────────────────────────────────────────────

echo.
echo ========================================
echo    서버 실행 중
echo ========================================
echo.
echo   프론트엔드:  http://localhost:5173
echo   백엔드 API:  http://localhost:8000
echo.
echo   각 터미널 창을 닫으면 해당 서버가 종료됩니다.
echo.
pause
