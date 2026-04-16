# Setup Scripts Design

**Date:** 2026-04-16  
**Topic:** 배포용 환경 세팅 자동화 스크립트

## 목표

처음 받는 사람이 명령 2개만으로 실행 가능한 상태까지 도달하게 한다.

```
./setup.sh   # 또는 setup.bat
./start.sh   # 또는 start.bat
```

## 대상 OS

- Windows (setup.bat, start.bat)
- macOS / Linux (setup.sh, start.sh)

## 파일 목록

| 파일 | 역할 |
|------|------|
| `setup.sh` | Mac/Linux 환경 설치 |
| `setup.bat` | Windows 환경 설치 |
| `start.sh` | Mac/Linux 서버 실행 + 브라우저 오픈 |
| `start.bat` | Windows 서버 실행 + 브라우저 오픈 |

## 섹션 1: 사전 검사

setup 스크립트 최초 실행 시 3가지를 순서대로 점검한다.  
하나라도 실패하면 에러 메시지 + 설치 링크 출력 후 즉시 종료(exit 1).

| 검사 항목 | 기준 | 실패 시 출력 |
|-----------|------|-------------|
| Python | 3.10 이상 | "Python 3.10+ 필요. https://python.org" |
| Node.js | 18 이상 | "Node.js 18+ 필요. https://nodejs.org" |
| Claude Code CLI | `claude` 명령 존재 | "Claude Code CLI 필요. https://claude.ai/code — 설치 후 `claude` 로그인 완료 필요" |

Claude Code 로그인 상태는 별도 검증하지 않는다 (실행 시간이 길어짐).  
대신 안내 문구로 명시한다.

## 섹션 2: setup 스크립트 동작

사전 검사 통과 후 순서대로 실행:

1. `.venv` 생성 — 이미 존재하면 스킵
2. pip install -r requirements.txt
3. frontend/node_modules 설치 — 이미 존재하면 스킵
4. .env.example → .env 복사 — 이미 존재하면 스킵 (덮어쓰지 않음)
5. 완료 메시지 + 다음 단계 안내

## 섹션 3: start 스크립트 동작

1. `.venv` 존재 확인 — 없으면 "setup 먼저 실행하세요" 안내 후 종료
2. 백엔드 서버 시작 (uvicorn, port 8000)
3. 프론트엔드 서버 시작 (npm run dev, port 5173)
4. 3초 대기
5. 브라우저 자동 오픈 (http://localhost:5173)
6. 서버 주소 출력

**OS별 구현 차이:**

- **Mac/Linux**: `&` 백그라운드 실행 → `wait`로 Ctrl+C 시 전체 종료
- **Windows**: `start "Backend" cmd /k ...` 로 새 창 2개 오픈

## 섹션 4: README 업데이트

기존 "시작 방법" 위에 "빠른 시작" 섹션 추가.  
기존 수동 설치 섹션은 그대로 유지.

## 비기능 요건

- 멱등성: setup을 여러 번 실행해도 기존 설치를 덮어쓰지 않음
- 명확한 에러: 각 단계 실패 시 무엇이 문제인지 한국어로 출력
- 최소 의존성: bash, python3, node, npm 외 추가 도구 불필요
