# Follow-Up Meeting Reference Attachment — Design Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Scope:** 이전 미팅 결과를 후속 미팅의 첨부 자료로 연결하는 기능

---

## 1. 개요

완료된 미팅의 결론과 대화 내용을 후속 미팅의 첨부 자료로 넣어, 이전 맥락을 이어받는 연속 미팅을 지원한다. 두 가지 진입점을 제공한다.

---

## 2. 진입점

### 2-1. SetupView HISTORY 목록에서 첨부

- 기존 HISTORY 항목마다 "참조" 버튼 추가
- 클릭 시 `GET /api/history/{session_id}/markdown`으로 마크다운 텍스트를 fetch
- `new File([text], "[이전회의] {topic 앞 20자}.md")` 로 File 객체 생성
- 기존 `files` ref 배열에 push (드래그&드롭 첨부와 동일한 인프라 사용)
- 동일 session_id 중복 첨부 방지 (이미 첨부된 회의는 버튼 비활성)
- 여러 회의를 각각 첨부 가능

### 2-2. MeetingView / HistoryView에서 후속 회의 시작

**MeetingView (완료 상태):**
- `isDone === true` 일 때 "후속 회의 시작" 버튼 표시 (취소 버튼 자리에)
- 클릭 시 `router.push({ path: '/', query: { ref: sessionId } })`

**HistoryView:**
- "후속 회의 시작" 버튼 표시 (사이드바 하단, "새 회의 시작" 버튼 위)
- 클릭 시 `router.push({ path: '/', query: { ref: route.params.sessionId } })`

**SetupView 진입 시:**
- `route.query.ref` 가 존재하면 onMounted에서 해당 회의를 자동 첨부
- 첨부 완료 후 URL에서 ref 쿼리 제거 (`router.replace('/')`)

---

## 3. API

### `GET /api/history/{session_id}/markdown`

히스토리 JSON을 구조화된 마크다운 텍스트로 변환해 반환한다.

**Response:** `text/plain; charset=utf-8`

**마크다운 포맷:**

```markdown
# 이전 회의 기록

- **안건:** {topic}
- **참여자:** {participant1}, {participant2}, ...
- **일시:** {timestamp (YYYY.MM.DD HH:MM)}

---

## Phase 1: 초기 의견 수집

> *사회자: {moderator content}*

**{speaker name} ({slug}):**
{message content}

---

## Phase 2: 자유 토론

...

---

## 최종 합의안

{consensus content (마지막 moderator 메시지)}
```

**변환 규칙:**
- `phase` 이벤트 → `## {label}` 헤더
- `moderator` 이벤트 → 인용문(`> *사회자: ...*`)
- `message` 이벤트 → `**{speaker} ({slug}):**\n{content}`
- 마지막 `moderator` 메시지 → `## 최종 합의안` 섹션으로 변환
- `done`, `error` 이벤트 → 생략
- 참여자 이름은 `team-skills/{slug}/meta.json`에서 조회, 없으면 slug 사용

---

## 4. 파일 변경 목록

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `web/routes/history.py` | `GET /api/history/{session_id}/markdown` 엔드포인트 추가 |
| `frontend/src/views/SetupView.vue` | HISTORY 항목에 참조 버튼 추가, `ref` 쿼리 파라미터 자동 첨부 처리 |
| `frontend/src/views/MeetingView.vue` | 완료 시 "후속 회의 시작" 버튼 추가 |
| `frontend/src/views/HistoryView.vue` | "후속 회의 시작" 버튼 추가 |

### 신규 파일

없음

---

## 5. 오류 처리

| 상황 | 처리 |
|------|------|
| 마크다운 변환 API 실패 | 인라인 에러 메시지 ("회의 자료를 불러오지 못했습니다") |
| 이미 첨부된 회의 재첨부 시도 | 버튼 비활성 또는 무시 |
| `ref` 쿼리의 session_id가 유효하지 않음 | 에러 무시, 정상 SetupView로 표시 |
