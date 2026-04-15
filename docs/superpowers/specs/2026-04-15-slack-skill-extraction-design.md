# Slack Skill Extraction — Design Spec

**Date**: 2026-04-15  
**Status**: Approved  
**Scope**: Slack 대화 로그 기반 팀원 SKILL.md 자동 추출 기능

---

## 1. 개요

`team-skills/` 폴더가 비어있을 때 Slack 메시지 히스토리를 기반으로 팀원 프로필(SKILL.md)을 자동 생성하는 기능을 추가한다. 기존 시뮬레이션 SSE 스트리밍 패턴을 재사용하며, 별도 `/extract` 라우트로 분리한다.

참조 레포: [titanwings/colleague-skill](https://github.com/titanwings/colleague-skill)  
— `tools/slack_auto_collector.py`의 메시지 수집 로직과 `prompts/work_analyzer.md`, `prompts/persona_analyzer.md`의 LLM 분석 프롬프트를 어댑터 형태로 통합한다.

---

## 2. 환경 변수 (.env)

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNELS=C01234567,C08901234   # 쉼표 구분, 여러 채널 가능
```

필요한 Slack Bot OAuth 스코프: `users:read`, `channels:read`, `channels:history`, `groups:read`, `groups:history`

---

## 3. 파일 변경 목록

### 신규 파일
| 파일 | 역할 |
|------|------|
| `.env` | Slack 토큰 + 채널 환경변수 |
| `web/routes/slack_extraction.py` | `/api/slack/discover`, `/api/slack/extract`, `/api/slack/stream/{id}` |
| `simulation/slack_collector.py` | 메시지 수집 + 슬러그 생성 + LLM 분석 + 파일 쓰기 |
| `frontend/src/views/ExtractionView.vue` | 3단계 추출 UI |

### 수정 파일
| 파일 | 변경 내용 |
|------|---------|
| `web/app.py` | `slack_extraction` 라우터 등록 |
| `frontend/src/router/index.js` | `/extract` 라우트 추가 |
| `frontend/src/views/SetupView.vue` | 빈 team-skills 감지 시 `/extract` 리다이렉트 + 헤더 재추출 링크 |
| `requirements.txt` | `slack-sdk>=3.27.0`, `python-dotenv>=1.0.0`, `pypinyin>=0.48.0` 추가 |

---

## 4. 백엔드 설계

### 4-1. `GET /api/slack/discover`

1. `.env` 로드 → `SLACK_BOT_TOKEN`, `SLACK_CHANNELS` 읽기
2. 각 채널 `conversations.history` 페이지네이션 (rate-limit retry 포함)
3. 유저별 메시지 수 집계 → 3개 이상인 유저만 필터
4. 봇 계정 제외 (`is_bot: true` 필터)
5. `users.info` 로 display_name 조회
6. 슬러그 자동 생성:
   - 한글: `pypinyin` 로마자 변환 (`홍길동` → `honggildong`)
   - 영문: 소문자 + 공백·특수문자 제거 (`John Kim` → `johnkim`)
7. 반환:

```json
[
  {"user_id": "U012AB3CD", "display_name": "홍길동", "message_count": 47, "suggested_slug": "honggildong"},
  {"user_id": "U045EF6GH", "display_name": "John Kim", "message_count": 23, "suggested_slug": "johnkim"}
]
```

### 4-2. `POST /api/slack/extract`

Request body:
```json
[
  {"user_id": "U012AB3CD", "slug": "honggildong", "display_name": "홍길동"},
  {"user_id": "U045EF6GH", "slug": "johnkim", "display_name": "John Kim"}
]
```

- `session_id` 즉시 반환
- `loop.run_in_executor` 로 백그라운드 스레드에서 `_run_extraction()` 실행

### 4-3. `GET /api/slack/stream/{session_id}`

기존 `/api/stream/{session_id}` 와 동일한 SSE 패턴 (SimpleQueue 폴링).

SSE 이벤트 타입:

| type | 필드 | 설명 |
|------|------|------|
| `collecting` | `slug`, `current`, `total` | 메시지 수집 중 |
| `analyzing` | `slug`, `step` (`work`\|`persona`), `current`, `total` | LLM 분석 중 |
| `writing` | `slug`, `current`, `total` | 파일 생성 중 |
| `member_done` | `slug`, `current`, `total` | 팀원 1명 완료 |
| `done` | — | 전체 완료 |
| `error` | `message` | 오류 |

### 4-4. `simulation/slack_collector.py` 내부 흐름

팀원 1명당 처리 순서:

```
1. fetch_user_messages(user_id, channels, token)
   → 각 채널 conversations.history 순회 → 해당 user_id 발화만 필터
   → 순수 이모지·단순 멘션 제거 (colleague-skill 동일 기준)
   → messages: list[str]

2. analyze_work(messages) — claude -p 호출
   → `slack_collector.py` 내 인라인 WORK_ANALYSIS_PROMPT 사용
     (colleague-skill work_analyzer.md 기반으로 작성, 외부 파일 의존 없음)
   → Part A (업무 역할, 기술 스택, 작업 스타일) 마크다운 반환
   → 호출 방식: 기존 ClaudeCodeModelClient.call() 패턴 동일하게 subprocess 사용

3. analyze_persona(messages) — claude -p 호출
   → `slack_collector.py` 내 인라인 PERSONA_ANALYSIS_PROMPT 사용
     (colleague-skill persona_analyzer.md 기반으로 작성, 외부 파일 의존 없음)
   → Part B (Layer 0~4 페르소나) 마크다운 반환
   → 호출 방식: 기존 ClaudeCodeModelClient.call() 패턴 동일하게 subprocess 사용

4. write_profile(slug, display_name, part_a, part_b)
   → team-skills/{slug}/ 폴더 생성
   → SKILL.md = Part A + Part B 결합
   → work.md = Part A
   → persona.md = Part B
   → meta.json = {slug, name, version: "v1", created_at, corrections_count: 0}
```

**오류 처리:**

| 상황 | 처리 |
|------|------|
| SLACK_BOT_TOKEN 없음 | discover 시점에 400 반환 + 메시지 |
| 채널 접근 불가 | 해당 채널 스킵, 경고 SSE emit |
| 메시지 0개 (필터 후) | 해당 멤버 스킵, `error` SSE emit |
| claude -p 실패 | 1회 재시도 후 실패 시 해당 멤버 스킵 |
| slug 충돌 (이미 존재) | `_{n}` suffix 자동 부여 |

---

## 5. 프론트엔드 설계

### ExtractionView.vue — 3단계

**Step 1: 탐색 시작**
- 채널 목록 표시 (`.env`에서 읽은 값, 백엔드 반환)
- "채널 탐색 시작" 버튼 → `GET /api/slack/discover` → 로딩 스피너

**Step 2: 후보 확인**
- 발견된 유저 카드 목록:
  - 체크박스 (기본 전체 선택)
  - display_name, 메시지 수 배지
  - slug 인라인 편집 input
- "선택한 팀원 스킬 추출 시작" 버튼 → `POST /api/slack/extract`

**Step 3: 추출 진행**
- SSE 구독 → 팀원별 진행 카드:
  - 수집 중 / 분석 중 (work) / 분석 중 (persona) / 파일 생성 중 / 완료
  - 현재 처리 중인 팀원 하이라이트
- 전체 완료 시 3초 후 `router.push('/')` 자동 이동

### SetupView.vue 변경
- `onMounted`: `/api/participants` 빈 배열 반환 시 `router.push('/extract')`
- 헤더에 "팀원 재추출" 링크 추가 (항상 노출)

---

## 6. 데이터 흐름 요약

```
.env (SLACK_BOT_TOKEN, SLACK_CHANNELS)
     │
     ▼
GET /api/slack/discover
     │ 채널 순회 + 유저 집계
     ▼
ExtractionView Step 2 (후보 선택 + slug 편집)
     │
     ▼
POST /api/slack/extract  →  session_id
     │
     ▼ (백그라운드 스레드)
slack_collector._run_extraction()
     ├── 팀원 1: collect → analyze(work) → analyze(persona) → write
     ├── 팀원 2: ...
     └── 팀원 N: ...
     │  (각 단계마다 SSE emit)
     ▼
team-skills/{slug}/ 생성 완료
     │
     ▼
router.push('/')  →  SetupView 정상 로드
```

---

## 7. 의존성 추가

```
slack-sdk>=3.27.0
python-dotenv>=1.0.0
pypinyin>=0.48.0
```
