# Web Frontend Design — Team Meeting Simulation

**Date:** 2026-04-15  
**Status:** Approved  
**Stack:** Vue 3 + Vite (frontend) · FastAPI (backend) · SSE (streaming)

---

## 1. 목표

팀 미팅 시뮬레이션 결과를 실시간 채팅 UI로 표시하는 로컬 웹 프론트엔드를 구축한다.  
각 팀원 발언이 완성될 때마다 SSE(Server-Sent Events)로 브라우저에 push되어, 채팅이 생성되는 것처럼 보인다.

---

## 2. 아키텍처

```
[Browser: Vue 3 + Vite :5173]
        │  ① POST /api/run        → 시뮬레이션 시작, session_id 반환
        │  ② GET  /api/stream/:id → SSE 구독 (실시간 이벤트 수신)
        │  ③ GET  /api/participants → 팀원 목록
        ↓
[Backend: FastAPI :8000]
        │
        ├── BackgroundTask로 별도 스레드에서 orchestrator.run() 실행
        │       각 발언 완료 시 → asyncio.Queue에 이벤트 push
        │
        └── SSE 엔드포인트: Queue에서 이벤트 pop → text/event-stream 전송
```

기존 `simulation/` 패키지는 최소 수정. CLI(`python -m simulation.cli`)는 그대로 동작.

---

## 3. 파일 구조

```
team-meeting-simulation/
├── web/
│   ├── app.py                  ← FastAPI 앱 진입점 (포트 8000)
│   └── routes/
│       ├── participants.py     ← GET /api/participants
│       └── simulation.py       ← POST /api/run, GET /api/stream/{id}
├── frontend/                   ← Vue 3 + Vite 프로젝트
│   ├── src/
│   │   ├── views/
│   │   │   ├── SetupView.vue   ← 회의 설정 페이지
│   │   │   └── MeetingView.vue ← 실시간 채팅 페이지
│   │   ├── components/
│   │   │   ├── ChatBubble.vue  ← 팀원 발언 버블
│   │   │   ├── PhaseHeader.vue ← 페이즈 구분선
│   │   │   └── ConsensusCard.vue ← 최종 합의안 카드
│   │   ├── App.vue
│   │   └── main.js
│   ├── index.html
│   └── package.json
└── simulation/                 ← 기존 코드 (최소 변경)
    ├── session.py              ← stream_* 메서드에 emit 콜백 추가
    └── ...
```

---

## 4. API 명세

### `GET /api/participants`
팀원 목록 반환.

```json
[
  {"slug": "leecy", "name": "이창영3", "color": "#FF4500"},
  {"slug": "jasonjoe", "name": "조성훈", "color": "#2563EB"},
  {"slug": "philgineer", "name": "윤준호", "color": "#16A34A"},
  {"slug": "jmyeon", "name": "연준명", "color": "#9333EA"},
  {"slug": "rockmin", "name": "최석민", "color": "#DC2626"}
]
```

### `POST /api/run`
시뮬레이션 시작. multipart/form-data.

```
topic:        str           (필수) 회의 안건
participants: str[]         (필수) slug 목록
rounds:       int           (선택, 기본 3) Phase 2 발언 횟수
files:        UploadFile[]  (선택) 첨부 파일
```

응답:
```json
{"session_id": "uuid4"}
```

### `GET /api/stream/{session_id}`
SSE 스트림. `Content-Type: text/event-stream`

**이벤트 타입 5종:**

| type | payload 예시 |
|------|-------------|
| `phase` | `{"phase": 1, "label": "Phase 1: 초기 의견 수집"}` |
| `moderator` | `{"content": "회의를 시작하겠습니다..."}` |
| `message` | `{"speaker": "이창영3", "slug": "leecy", "content": "...", "phase": 1}` |
| `done` | `{"output_file": "outputs/2026-04-15-...md"}` |
| `error` | `{"message": "오류 내용"}` |

---

## 5. 프론트엔드 UI

### 디자인 시스템 (mirofish 스타일)

```
색상:
  --black:   #000000
  --white:   #FFFFFF
  --orange:  #FF4500   (액센트, CTA, 상태 표시)
  --gray-50: #F5F5F5
  --gray-200:#E5E5E5
  --gray-600:#666666

폰트:
  JetBrains Mono → 슬러그·태그·step 번호
  Space Grotesk  → 헤드라인
  Inter          → 본문

팀원별 아바타 색상:
  leecy      → #FF4500
  jasonjoe   → #2563EB
  philgineer → #16A34A
  jmyeon     → #9333EA
  rockmin    → #DC2626
```

### SetupView (회의 설정)

- 좌: 안건 텍스트 입력 + 파일 드래그&드롭 업로드
- 우: 팀원 체크박스 목록 (아바타 이니셜 + slug 태그) + 라운드 수 입력
- 하단: 검정 배경 "시뮬레이션 시작" 버튼 → hover 시 오렌지

### MeetingView (실시간 채팅)

- 좌 패널 (고정 240px):
  - 참여자 목록 (아바타 원형 + 이름, 현재 발언자 오렌지 강조)
  - 페이즈 진행 표시기 (Phase 1·2·3 스텝)
- 우 패널 (스크롤 채팅 영역):
  - `PhaseHeader`: 오렌지 구분선 + 페이즈 이름
  - `ChatBubble`: 아바타 이니셜 원형 + 이름 + 발언 내용, 등장 시 fade-in 애니메이션
  - 사회자 발언: 중앙 정렬, 이탤릭, 회색 텍스트
  - `ConsensusCard`: 페이즈 3 완료 후 오렌지 테두리 카드, 섹션별 번호(01·02·03) 표시

---

## 6. 기존 코드 수정 범위

`simulation/session.py` 만 수정:
- `MeetingSession` 생성자에 선택적 `emit: Callable | None = None` 파라미터 추가
- `stream_message()`, `stream_moderator()`, `stream_phase()` 내부에서 `emit()` 호출 추가
- CLI 경로는 `emit=None` 이므로 기존 동작 무변화

---

## 7. 실행 방법

```bash
# 백엔드
cd team-meeting-simulation
pip install fastapi uvicorn python-multipart
uvicorn web.app:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## 8. 오류 처리

- 시뮬레이션 중 예외 → `error` 이벤트 emit → 프론트엔드 에러 배너 표시
- SSE 연결 끊김 → EventSource 자동 재연결 (브라우저 기본 동작)
- 파일 업로드 실패 → POST /api/run 422 응답 → 설정 페이지 인라인 오류 메시지
- session_id 없음 → 404 응답
