# Team Meeting Simulation

실제 팀원의 Slack 메시지를 학습해 페르소나를 구성하고, AI가 그 팀원을 대신해 회의에 참여하는 시뮬레이션 도구입니다.

회의 안건과 참여자를 설정하면 각 팀원 AI가 자신의 말투·성격·업무 스타일을 유지하며 3단계 토론을 진행하고, 사회자 AI가 최종 합의안을 도출합니다.

---

## 빠른 시작

설치와 실행을 자동화하는 스크립트를 제공합니다.

**Mac / Linux**
```bash
chmod +x setup.sh start.sh
./setup.sh    # 최초 1회 — 환경 검사 + 의존성 설치
./start.sh    # 서버 실행 + 브라우저 자동 오픈
```

**Windows**
```bat
setup.bat     # 최초 1회 — 환경 검사 + 의존성 설치
start.bat     # 서버 실행 + 브라우저 자동 오픈
```

> setup은 **최초 1회만** 실행하면 됩니다. 이후에는 `start`만 실행하면 됩니다.

---

## 목차

- [빠른 시작](#빠른-시작)
- [요구사항](#요구사항)
- [시작 방법](#시작-방법)
- [Slack 팀원 프로필 추출](#slack-팀원-프로필-추출)
- [회의 시뮬레이션 사용법](#회의-시뮬레이션-사용법)
- [작동 원리](#작동-원리)
- [디렉터리 구조](#디렉터리-구조)
- [지원 파일 형식](#지원-파일-형식)

---

## 요구사항

| 항목 | 최소 버전 | 비고 |
|------|-----------|------|
| [Claude Code CLI](https://claude.ai/code) | 최신 버전 | LLM 실행 엔진, 별도 API 키 불필요 |
| Python | 3.10+ | 백엔드 |
| Node.js | 18+ | 프론트엔드 빌드 |
| Slack Bot Token | — | 팀원 프로필 추출 시에만 필요 |

> **핵심 전제:** 이 시스템은 Claude Code CLI를 LLM 호출 엔진으로 사용합니다.  
> `claude` 명령이 터미널에서 실행 가능하고, 로그인이 완료된 상태여야 합니다.  
> `claude -p "hello"` 를 실행해 응답이 오는지 미리 확인하세요.

---

## 시작 방법

### 1. 저장소 클론

```bash
git clone <repo-url>
cd team-meeting-simulation
```

### 2. Python 가상환경 설정

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 프론트엔드 의존성 설치

```bash
cd frontend
npm install
cd ..
```

### 4. 환경 변수 설정 (Slack 추출 사용 시)

```bash
cp .env.example .env
```

`.env` 파일을 열어 Slack 설정을 입력합니다:

```env
# Slack Bot Token (xoxb- 로 시작)
# 필요 스코프: users:read, channels:read, channels:history, groups:read, groups:history
SLACK_BOT_TOKEN=xoxb-your-bot-token

# 수집 대상 채널 ID 목록 (쉼표 구분, C로 시작하는 채널 ID)
SLACK_CHANNELS=C01234567,C08901234
```

> Slack 추출 기능을 사용하지 않고 `team-skills/` 폴더에 프로필을 직접 작성한다면 이 단계는 건너뛰어도 됩니다.

### 5. 서버 실행

터미널 두 개를 열어 각각 실행합니다.

**백엔드 (터미널 1):**
```bash
# 가상환경 활성화 상태에서
uvicorn web.app:app --reload --port 8000
```

**프론트엔드 (터미널 2):**
```bash
cd frontend
npm run dev
```

브라우저에서 `http://localhost:5173` 접속.

---

## Slack 팀원 프로필 추출

팀원의 실제 Slack 메시지를 분석해 AI 페르소나 프로필을 자동 생성합니다.  
생성된 프로필은 `team-skills/<slug>/` 폴더에 저장됩니다.

### 추출 절차

1. 메인 화면 우측 상단 **팀원 재추출** 버튼 클릭 (또는 `/extract` 경로 직접 접속)
2. **채널 탐색 시작** → `.env`에 설정된 채널에서 3개 이상 메시지를 보낸 팀원을 자동 탐색
3. 추출할 팀원 선택, slug 편집, 역할 지정
4. 메시지 수집 한도 설정 후 **스킬 추출 시작**
5. 6단계 파이프라인이 실시간으로 진행됨:
   - 메시지 수집 → 업무 패턴 추출 → 업무 프로필 생성 → 페르소나 추출 → 페르소나 생성 → 파일 생성

### 생성되는 파일

```
team-skills/<slug>/
├── SKILL.md            # 핵심 프로필 (Part A 업무 + Part B 페르소나)
├── persona.md          # 페르소나 요약 (Part B)
├── work.md             # 업무 프로필 요약 (Part A)
├── meta.json           # 메타데이터 (slug, 이름, 메시지 수, 버전 등)
└── slack_messages.json # 원본 Slack 메시지 (분석 원천 데이터)
```

### 프로필 수동 작성

Slack 없이 직접 프로필을 작성하려면 `team-skills/` 아래 폴더를 만들고 위 파일 구조를 따라 작성합니다.  
`SKILL.md`만 있으면 시뮬레이션에 참여 가능합니다.

---

## 회의 시뮬레이션 사용법

1. `http://localhost:5173` 접속
2. **안건** 입력 (회의 주제)
3. **첨부 파일** 추가 (선택) — PDF, Excel, Word 등 참고 자료
4. **참여자** 선택 — `team-skills/`에 프로필이 있는 팀원 목록에서 체크
5. **Phase 2 라운드 수** 설정 (자유 토론 횟수, 기본 3)
6. **시뮬레이션 시작** 클릭
7. 실시간으로 각 팀원의 발언이 스트리밍되어 표시됨
8. 종료 후 합의안 확인 및 회의록 다운로드

**회의록은 `outputs/` 폴더에 마크다운 파일로 저장됩니다.**

---

## 작동 원리

### LLM 호출 방식

별도 API 키 없이 **Claude Code CLI**를 subprocess로 호출합니다.

```
FastAPI 서버
  └─ subprocess: claude -p <대화 내용> --system-prompt-file <페르소나>
       └─ Claude Code (기존 로그인 세션 재사용)
            └─ 응답 텍스트 → stdout → 파싱 → SSE emit → 프론트엔드
```

### 회의 3단계 구조

```
Phase 1: 초기 의견 수집
  사회자가 안건 소개 → 각 팀원이 순서대로 초기 의견 발언

Phase 2: 자유 토론
  사회자가 매 라운드마다 다음 발언자를 선택 → 팀원이 다른 의견에 반응하거나 새 논점 제시
  (설정한 라운드 수만큼 반복)

Phase 3: 합의 도출
  각 팀원이 최종 입장 표명 → 사회자가 모든 의견을 종합해 합의안 작성
```

### 팀원 페르소나 구조 (SKILL.md)

각 팀원 AI는 `SKILL.md`를 system prompt로 받아 동작합니다:

- **Part A — 업무 프로필**: 역할, 기술 스택, 업무 스타일, 커뮤니케이션 패턴
- **Part B — 페르소나 레이어**:
  - Layer 0: 절대 행동 원칙 (어떤 상황에서도 유지)
  - Layer 1: 핵심 정체성
  - Layer 2: 표현 스타일 (말투, 어투)
  - Layer 3: 의사결정 패턴
  - Layer 4: 대인관계 패턴

### Slack 추출 파이프라인

```
Slack API 메시지 수집
  ↓
Stage 1 (병렬):
  work_extract    — 업무 패턴 구조화 추출 (Claude)
  persona_extract — 페르소나 패턴 구조화 추출 (Claude)
  ↓
Stage 2 (병렬):
  work_build      — 업무 프로필 마크다운 생성 (Claude)
  persona_build   — 페르소나 마크다운 생성 (Claude)
  ↓
파일 저장: SKILL.md, work.md, persona.md, meta.json, slack_messages.json
```

### PDF 처리 방식

업로드된 PDF는 디스크에 저장되지 않습니다.

```
프론트엔드 업로드 → 백엔드 메모리 수신
  → 임시 파일 생성
  → claude -p (Read 툴) 로 PDF 전체를 마크다운으로 변환
  → 임시 파일 즉시 삭제
  → 변환된 마크다운을 메모리에서 에이전트 system prompt에 주입
  → 시뮬레이션 종료 시 메모리에서 소멸
```

### SSE 실시간 스트리밍

백엔드는 시뮬레이션을 별도 스레드에서 실행하며, `SimpleQueue`를 통해 이벤트를 프론트엔드에 Server-Sent Events로 전달합니다.

```
백그라운드 스레드: 시뮬레이션 실행 → queue.put(event)
메인 스레드 (FastAPI): queue.get_nowait() 50ms 폴링 → SSE yield
프론트엔드: EventSource 구독 → 실시간 UI 업데이트
```

---

## 디렉터리 구조

```
team-meeting-simulation/
├── frontend/               # Vue 3 + Vite + TypeScript 프론트엔드
│   └── src/
│       ├── views/          # SetupView, MeetingView, ExtractionView, HistoryView
│       └── components/     # ChatBubble, ConsensusCard, 등
├── web/                    # FastAPI 백엔드
│   └── routes/
│       ├── simulation.py   # POST /api/run, GET /api/stream/{id}
│       ├── slack_extraction.py  # Slack 추출 API
│       ├── participants.py # 팀원 목록 API
│       └── history.py      # 회의 기록 API
├── simulation/             # 핵심 시뮬레이션 로직
│   ├── agents.py           # MeetingAgent, ModeratorAgent
│   ├── orchestrator.py     # 3단계 회의 흐름 제어
│   ├── session.py          # 회의록 생성 및 SSE emit
│   ├── model_client.py     # claude -p subprocess 래퍼
│   ├── slack_collector.py  # Slack 메시지 수집 및 프로필 추출
│   └── loader.py           # 팀원 설정 및 첨부 파일 로딩
├── team-skills/            # 팀원 프로필 폴더 (1명 = 1폴더)
│   └── <slug>/
│       ├── SKILL.md
│       ├── persona.md
│       ├── work.md
│       ├── meta.json
│       └── slack_messages.json
├── outputs/                # 시뮬레이션 결과물
│   └── history/            # 회의 기록 JSON
├── .env.example            # 환경 변수 템플릿
├── requirements.txt        # Python 의존성
└── README.md
```

---

## 지원 파일 형식

회의 시 첨부 가능한 파일 형식과 처리 방식:

| 확장자 | 처리 방식 |
|--------|-----------|
| `.pdf` | Claude Code Read 툴로 전체 내용을 마크다운으로 변환 |
| `.xlsx`, `.xls` | pandas로 마크다운 표로 변환 |
| `.csv` | pandas로 마크다운 표로 변환 |
| `.docx` | python-docx 추출 후 Claude로 재구조화 |
| `.pptx` | python-pptx 추출 후 Claude로 재구조화 (슬라이드별) |
| `.md`, `.txt` | 텍스트 직접 읽기 |

변환된 내용은 각 팀원의 system prompt에 주입되어 회의 컨텍스트로 활용됩니다.
