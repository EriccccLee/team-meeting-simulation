# Web Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 팀 미팅 시뮬레이션에 Vue 3 + FastAPI + SSE 기반 실시간 웹 프론트엔드를 추가한다.

**Architecture:** FastAPI 백엔드(:8000)가 시뮬레이션을 스레드에서 실행하며, 각 발언이 완성될 때마다 SSE 이벤트로 Vue 3 프론트엔드(:5173)에 push한다. 기존 `simulation/` 패키지는 `session.py`에 emit 콜백만 추가하고 CLI는 그대로 유지한다.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, python-multipart, Vue 3, Vite, Vue Router 4

---

## File Map

**수정:**
- `simulation/session.py` — emit 콜백 파라미터 추가
- `requirements.txt` — fastapi, uvicorn, python-multipart 추가

**신규 (백엔드):**
- `web/__init__.py`
- `web/app.py` — FastAPI 앱, CORS, 라우터 등록
- `web/routes/__init__.py`
- `web/routes/participants.py` — GET /api/participants
- `web/routes/simulation.py` — POST /api/run, GET /api/stream/{id}

**신규 (프론트엔드):**
- `frontend/package.json`
- `frontend/index.html`
- `frontend/vite.config.js` — Vite 설정 + /api 프록시
- `frontend/src/main.js`
- `frontend/src/App.vue`
- `frontend/src/router/index.js`
- `frontend/src/assets/main.css` — CSS 디자인 시스템
- `frontend/src/views/SetupView.vue` — 회의 설정 페이지
- `frontend/src/views/MeetingView.vue` — 실시간 채팅 페이지
- `frontend/src/components/ChatBubble.vue`
- `frontend/src/components/PhaseHeader.vue`
- `frontend/src/components/ConsensusCard.vue`

---

## Task 1: simulation/session.py에 emit 콜백 추가

**Files:**
- Modify: `simulation/session.py`

- [ ] **Step 1: session.py 수정 — emit 파라미터 추가**

`simulation/session.py` 전체를 아래로 교체한다:

```python
"""
MeetingSession
──────────────
실시간 터미널 출력 + 마크다운 회의록 파일 생성을 담당합니다.

plan.md §4-5 참조.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Callable


class MeetingSession:
    """
    회의 중 발생하는 모든 출력을 담당합니다.

    - stream_phase    : Phase 전환 구분선 출력
    - stream_message  : 팀원 발언 출력
    - stream_moderator: 사회자 발언 출력
    - save            : outputs/ 에 마크다운 파일 저장

    emit 콜백이 주어지면 각 stream_* 호출 시 이벤트 dict 를 emit(event) 로 전달합니다.
    CLI 경로에서는 emit=None 으로 기존 동작이 유지됩니다.
    """

    def __init__(
        self,
        topic: str,
        participants: list[str],
        output_dir: str = "outputs",
        emit: Callable[[dict], None] | None = None,
    ) -> None:
        self.topic = topic
        self.participants = participants
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = datetime.now()
        self._emit = emit

        # 파일 저장용 버퍼 (마크다운 형식)
        self._sections: list[str] = []

    # ── 터미널 출력 ──────────────────────────────────────────────────────────

    def stream_phase(self, phase_name: str) -> None:
        bar = "=" * 40
        self._print(f"\n{bar}\n[{phase_name}]\n{bar}\n")
        self._sections.append(f"\n## {phase_name}\n")
        if self._emit:
            self._emit({"type": "phase", "label": phase_name})

    def stream_message(self, speaker: str, content: str, slug: str = "") -> None:
        """팀원 발언 출력."""
        label = f"[{speaker}]" + (f" ({slug})" if slug else "")
        self._print(f"\n{label}")
        self._print(content)

        md_heading = f"### {speaker}" + (f" ({slug})" if slug else "")
        self._sections.append(f"\n{md_heading}\n{content}\n")
        if self._emit:
            self._emit({"type": "message", "speaker": speaker, "slug": slug, "content": content})

    def stream_moderator(self, content: str) -> None:
        """사회자 발언 출력."""
        self._print(f"\n[사회자] {content}")
        self._sections.append(f"\n**[사회자]**: {content}\n")
        if self._emit:
            self._emit({"type": "moderator", "content": content})

    @staticmethod
    def _print(text: str) -> None:
        """유니코드 안전 출력 (cli.py 에서 stdout 을 UTF-8 로 재설정한 후 호출됨)."""
        print(text, flush=True)

    # ── 파일 저장 ─────────────────────────────────────────────────────────────

    def save(self, participants_info: list[dict], consensus: str) -> Path:
        """
        회의 전체 내용을 마크다운 파일로 저장하고 경로를 반환합니다.

        Args:
            participants_info: [{"name": "이창영", "slug": "leecy"}, …]
            consensus:         ModeratorAgent 가 작성한 합의안 전문
        """
        timestamp = self.started_at.strftime("%Y-%m-%d-%H-%M")
        topic_slug = (
            self.topic[:20]
            .replace(" ", "-")
            .replace("/", "-")
            .lower()
        )
        filename = f"{timestamp}-{topic_slug}.md"
        filepath = self.output_dir / filename

        participants_str = ", ".join(
            p.get("name") or p.get("slug", "?") for p in participants_info
        )

        header = (
            "# 팀 미팅 시뮬레이션\n\n"
            f"- **안건**: {self.topic}\n"
            f"- **일시**: {self.started_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"- **참석자**: {participants_str}\n\n"
            "---\n"
        )

        # 합의안은 인용 블록으로
        consensus_lines = "\n".join(f"> {line}" for line in consensus.splitlines())
        consensus_section = f"\n## 합의안\n\n{consensus_lines}\n"

        body = "".join(self._sections)
        filepath.write_text(header + body + consensus_section, encoding="utf-8")

        self._print(f"\n[저장 완료] {filepath}")
        return filepath
```

- [ ] **Step 2: 수동 검증 — emit 콜백이 동작하는지 확인**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
python -c "
from simulation.session import MeetingSession
events = []
s = MeetingSession('테스트', ['leecy'], emit=events.append)
s.stream_phase('Phase 1')
s.stream_message('이창영3', '안녕하세요', 'leecy')
s.stream_moderator('회의를 시작합니다')
print(events)
assert events[0]['type'] == 'phase'
assert events[1]['type'] == 'message'
assert events[2]['type'] == 'moderator'
print('OK')
"
```

Expected output:
```
[{'type': 'phase', 'label': 'Phase 1'}, {'type': 'message', 'speaker': '이창영3', 'slug': 'leecy', 'content': '안녕하세요'}, {'type': 'moderator', 'content': '회의를 시작합니다'}]
OK
```

- [ ] **Step 3: Commit**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
git add simulation/session.py
git commit -m "feat: add emit callback to MeetingSession for SSE streaming"
```

---

## Task 2: requirements.txt 업데이트

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: requirements.txt에 웹 의존성 추가**

`requirements.txt` 파일 하단에 추가:

```
# 웹 프론트엔드 (FastAPI + SSE)
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9
```

- [ ] **Step 2: 패키지 설치 확인**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
pip install fastapi "uvicorn[standard]" python-multipart
python -c "import fastapi, uvicorn; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add fastapi/uvicorn/python-multipart to requirements"
```

---

## Task 3: FastAPI 백엔드 — 앱 + 팀원 목록 엔드포인트

**Files:**
- Create: `web/__init__.py`
- Create: `web/app.py`
- Create: `web/routes/__init__.py`
- Create: `web/routes/participants.py`

- [ ] **Step 1: web/__init__.py 생성**

```python
```
(빈 파일)

- [ ] **Step 2: web/routes/__init__.py 생성**

```python
```
(빈 파일)

- [ ] **Step 3: web/routes/participants.py 생성**

```python
"""
GET /api/participants — 팀원 목록 반환
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

TEAM_SKILLS_DIR = Path(__file__).parent.parent.parent / "team-skills"

# 팀원별 아바타 색상 (디자인 시스템 확정값)
_COLORS: dict[str, str] = {
    "leecy":      "#FF4500",
    "jasonjoe":   "#2563EB",
    "philgineer": "#16A34A",
    "jmyeon":     "#9333EA",
    "rockmin":    "#DC2626",
}
_DEFAULT_COLORS = ["#FF4500", "#2563EB", "#16A34A", "#9333EA", "#DC2626", "#CA8A04"]


@router.get("/participants")
def get_participants() -> list[dict]:
    """team-skills/ 디렉터리를 스캔해 팀원 목록을 반환합니다."""
    result = []
    for i, member_dir in enumerate(sorted(TEAM_SKILLS_DIR.iterdir())):
        if not member_dir.is_dir():
            continue
        slug = member_dir.name
        meta_path = member_dir / "meta.json"
        meta: dict = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_name = meta.get("name", slug)
        name = raw_name.split("[")[0].strip()
        color = _COLORS.get(slug, _DEFAULT_COLORS[i % len(_DEFAULT_COLORS)])
        result.append({"slug": slug, "name": name, "color": color})
    return result
```

- [ ] **Step 4: web/app.py 생성**

```python
"""
FastAPI 앱 진입점.

실행:
    uvicorn web.app:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import participants, simulation

app = FastAPI(title="Team Meeting Simulation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(participants.router, prefix="/api")
app.include_router(simulation.router, prefix="/api")
```

- [ ] **Step 5: 서버 기동 + 엔드포인트 확인**

터미널 1:
```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
uvicorn web.app:app --reload --port 8000
```

터미널 2:
```bash
curl http://localhost:8000/api/participants
```

Expected: 팀원 5명의 JSON 배열

- [ ] **Step 6: Commit**

```bash
git add web/__init__.py web/app.py web/routes/__init__.py web/routes/participants.py
git commit -m "feat: add FastAPI app with /api/participants endpoint"
```

---

## Task 4: FastAPI 백엔드 — 시뮬레이션 실행 + SSE 스트림

**Files:**
- Create: `web/routes/simulation.py`

- [ ] **Step 1: web/routes/simulation.py 생성**

```python
"""
POST /api/run       — 시뮬레이션 시작, session_id 반환
GET  /api/stream/{session_id} — SSE 이벤트 스트림
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

# simulation 패키지가 상위 디렉터리에 있으므로 sys.path 조정
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.agents import AgentConfig, MeetingAgent, ModeratorAgent, _strip_frontmatter
from simulation.model_client import ClaudeCodeModelClient
from simulation.orchestrator import MeetingOrchestrator, OrchestratorConfig
from simulation.session import MeetingSession
from simulation.cli import _load_agent_config, _load_file_contents

router = APIRouter()

# session_id → asyncio.Queue 매핑
_sessions: dict[str, asyncio.Queue] = {}


# ── 시뮬레이션 실행 (동기, 별도 스레드에서 호출됨) ────────────────────────────

def _run_simulation(
    session_id: str,
    topic: str,
    participant_slugs: list[str],
    rounds: int,
    file_contents: dict[str, str],
    loop: asyncio.AbstractEventLoop,
) -> None:
    """orchestrator.run() 을 동기 스레드에서 실행하고 결과를 SSE queue 에 push 합니다."""
    queue = _sessions[session_id]

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    try:
        model_client = ClaudeCodeModelClient()
        agents: list[MeetingAgent] = []
        for slug in participant_slugs:
            config = _load_agent_config(slug)
            agents.append(MeetingAgent(config, model_client))

        moderator = ModeratorAgent(model_client, participant_slugs)
        session = MeetingSession(
            topic,
            participant_slugs,
            output_dir=str(_ROOT / "outputs"),
            emit=emit,
        )
        config = OrchestratorConfig(phase2_rounds=rounds)
        orchestrator = MeetingOrchestrator(agents, moderator, session, config)
        result = orchestrator.run(topic, file_contents)

        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "done", "output_file": str(result.output_file)},
        )
    except Exception as e:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "error", "message": str(e)},
        )
    finally:
        # 스트림 종료 신호 (sentinel)
        loop.call_soon_threadsafe(queue.put_nowait, None)


# ── API 엔드포인트 ─────────────────────────────────────────────────────────────

@router.post("/run")
async def run_simulation(
    topic: Annotated[str, Form()],
    participants: Annotated[list[str], Form()],
    rounds: Annotated[int, Form()] = 3,
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """시뮬레이션을 백그라운드 스레드에서 시작하고 session_id 를 즉시 반환합니다."""
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _sessions[session_id] = queue
    loop = asyncio.get_event_loop()

    # 업로드된 파일을 임시 디렉터리에 저장
    file_contents: dict[str, str] = {}
    for upload in files:
        raw = await upload.read()
        if upload.filename and upload.filename.lower().endswith(".pdf"):
            # PDF는 임시 파일로 저장 후 _load_file_contents 로 변환
            with tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False, dir=str(_ROOT)
            ) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            loaded = _load_file_contents([tmp_path])
            file_contents.update(loaded)
            Path(tmp_path).unlink(missing_ok=True)
        else:
            name = upload.filename or "attachment.txt"
            try:
                file_contents[name] = raw.decode("utf-8")
            except UnicodeDecodeError:
                file_contents[name] = raw.decode("cp949", errors="replace")

    # 동기 orchestrator 를 별도 스레드에서 실행
    asyncio.get_event_loop().run_in_executor(
        None,
        _run_simulation,
        session_id,
        topic,
        participants,
        rounds,
        file_contents,
        loop,
    )

    return {"session_id": session_id}


@router.get("/stream/{session_id}")
async def stream_events(session_id: str) -> StreamingResponse:
    """SSE 스트림 — 시뮬레이션 이벤트를 실시간으로 전송합니다."""
    queue = _sessions.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="session not found")

    async def generate():
        try:
            while True:
                event = await queue.get()
                if event is None:  # sentinel — 스트림 종료
                    yield "data: {\"type\": \"end\"}\n\n"
                    break
                data = json.dumps(event, ensure_ascii=False)
                yield f"data: {data}\n\n"
        finally:
            _sessions.pop(session_id, None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 2: 서버 재기동 확인**

```bash
# 기존 uvicorn 재시작 (Ctrl+C 후)
uvicorn web.app:app --reload --port 8000
```

Expected: `INFO: Application startup complete.` (오류 없음)

- [ ] **Step 3: Commit**

```bash
git add web/routes/simulation.py
git commit -m "feat: add POST /api/run and GET /api/stream SSE endpoints"
```

---

## Task 5: Vue 3 + Vite 프론트엔드 프로젝트 스캐폴딩

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.js`
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/router/index.js`

- [ ] **Step 1: frontend/package.json 생성**

```json
{
  "name": "team-meeting-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.3.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.0.0"
  }
}
```

- [ ] **Step 2: frontend/vite.config.js 생성**

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 3: frontend/index.html 생성**

```html
<!DOCTYPE html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Team Meeting Simulation</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Space+Grotesk:wght@500;600;700&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 4: frontend/src/router/index.js 생성**

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import SetupView from '../views/SetupView.vue'
import MeetingView from '../views/MeetingView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: SetupView },
    { path: '/meeting', component: MeetingView },
  ],
})
```

- [ ] **Step 5: frontend/src/App.vue 생성**

```vue
<template>
  <router-view />
</template>

<script setup>
</script>
```

- [ ] **Step 6: frontend/src/main.js 생성**

```javascript
import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.js'
import './assets/main.css'

createApp(App).use(router).mount('#app')
```

- [ ] **Step 7: npm install 및 dev 서버 기동 확인**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation\frontend
npm install
npm run dev
```

Expected: `VITE v5.x.x ready` + `Local: http://localhost:5173/` (빈 페이지, 오류 없음)

- [ ] **Step 8: Commit**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
git add frontend/
git commit -m "feat: scaffold Vue 3 + Vite frontend project"
```

---

## Task 6: CSS 디자인 시스템

**Files:**
- Create: `frontend/src/assets/main.css`

- [ ] **Step 1: frontend/src/assets/main.css 생성**

```css
/* ── 디자인 토큰 ─────────────────────────────────────────────────────── */
:root {
  --black:   #000000;
  --white:   #FFFFFF;
  --orange:  #FF4500;
  --gray-50: #F5F5F5;
  --gray-100:#EEEEEE;
  --gray-200:#E5E5E5;
  --gray-400:#AAAAAA;
  --gray-600:#666666;
  --gray-800:#333333;

  --font-sans:  'Inter', sans-serif;
  --font-head:  'Space Grotesk', sans-serif;
  --font-mono:  'JetBrains Mono', monospace;

  /* 팀원 색상 */
  --color-leecy:      #FF4500;
  --color-jasonjoe:   #2563EB;
  --color-philgineer: #16A34A;
  --color-jmyeon:     #9333EA;
  --color-rockmin:    #DC2626;
}

/* ── 리셋 ────────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--black);
  background: var(--white);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3 { font-family: var(--font-head); }

/* ── 공통 컴포넌트 ───────────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 24px;
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  border: 1px solid var(--black);
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
  background: var(--black);
  color: var(--white);
  border-radius: 4px;
  letter-spacing: 0.02em;
}
.btn:hover { background: var(--orange); border-color: var(--orange); }
.btn:disabled { background: var(--gray-200); color: var(--gray-400); border-color: var(--gray-200); cursor: not-allowed; }

.tag {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 7px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  color: var(--gray-600);
}

/* ── fade-in 애니메이션 ──────────────────────────────────────────────── */
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.fade-in-up {
  animation: fadeInUp 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
}

/* ── 타이핑 커서 (mirofish 스타일) ──────────────────────────────────── */
@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
.cursor::after {
  content: '▋';
  color: var(--orange);
  animation: blink 1s step-start infinite;
  margin-left: 2px;
}
```

- [ ] **Step 2: 개발 서버에서 폰트 로드 확인**

브라우저 `http://localhost:5173` 열고 개발자 도구 → Network 탭에서 Google Fonts 로드 확인 (또는 body font-family 적용 확인).

- [ ] **Step 3: Commit**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
git add frontend/src/assets/main.css
git commit -m "feat: add CSS design system (mirofish style)"
```

---

## Task 7: 공통 컴포넌트 — ChatBubble, PhaseHeader, ConsensusCard

**Files:**
- Create: `frontend/src/components/ChatBubble.vue`
- Create: `frontend/src/components/PhaseHeader.vue`
- Create: `frontend/src/components/ConsensusCard.vue`

- [ ] **Step 1: frontend/src/components/PhaseHeader.vue 생성**

```vue
<template>
  <div class="phase-header fade-in-up">
    <div class="line" />
    <span class="label">{{ label }}</span>
    <div class="line" />
  </div>
</template>

<script setup>
defineProps({ label: { type: String, required: true } })
</script>

<style scoped>
.phase-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 0 12px;
}
.line {
  flex: 1;
  height: 1px;
  background: var(--gray-200);
}
.label {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--orange);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}
</style>
```

- [ ] **Step 2: frontend/src/components/ChatBubble.vue 생성**

```vue
<template>
  <div class="bubble fade-in-up" :class="type">
    <!-- 사회자 -->
    <template v-if="type === 'moderator'">
      <p class="mod-text">{{ content }}</p>
    </template>

    <!-- 팀원 -->
    <template v-else>
      <div class="avatar" :style="{ background: color }">
        {{ initials }}
      </div>
      <div class="body">
        <div class="header">
          <span class="speaker">{{ speaker }}</span>
          <span class="tag">{{ slug }}</span>
        </div>
        <p class="content">{{ content }}</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  type:    { type: String, required: true },   // 'message' | 'moderator'
  speaker: { type: String, default: '' },
  slug:    { type: String, default: '' },
  content: { type: String, required: true },
  color:   { type: String, default: '#999' },
})

const initials = computed(() =>
  props.speaker
    ? props.speaker.slice(0, 2)
    : '??'
)
</script>

<style scoped>
.bubble { display: flex; gap: 12px; padding: 6px 0; }

/* 사회자 */
.bubble.moderator {
  justify-content: center;
  padding: 12px 0;
}
.mod-text {
  font-style: italic;
  color: var(--gray-600);
  font-size: 13px;
  text-align: center;
  max-width: 560px;
}

/* 팀원 */
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  flex-shrink: 0;
  margin-top: 2px;
}

.body { flex: 1; min-width: 0; }

.header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.speaker {
  font-family: var(--font-head);
  font-size: 13px;
  font-weight: 600;
  color: var(--black);
}
.tag {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 6px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  color: var(--gray-600);
}

.content {
  font-size: 14px;
  line-height: 1.65;
  color: var(--gray-800);
  background: var(--gray-50);
  padding: 10px 14px;
  border-radius: 0 8px 8px 8px;
  border: 1px solid var(--gray-200);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
```

- [ ] **Step 3: frontend/src/components/ConsensusCard.vue 생성**

```vue
<template>
  <div class="consensus-wrap fade-in-up">
    <PhaseHeader label="최종 합의안" />
    <div class="card">
      <div class="card-header">
        <span class="card-tag">CONSENSUS</span>
        <span class="card-sub">팀 합의 결과</span>
      </div>
      <div class="card-body">
        <p v-for="(line, i) in lines" :key="i" class="line" :class="{ empty: !line.trim() }">
          <span v-if="line.trim()">{{ line }}</span>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import PhaseHeader from './PhaseHeader.vue'

const props = defineProps({ content: { type: String, required: true } })

const lines = computed(() => props.content.split('\n'))
</script>

<style scoped>
.consensus-wrap { padding-bottom: 40px; }

.card {
  border: 1px solid var(--orange);
  border-radius: 6px;
  overflow: hidden;
}

.card-header {
  background: var(--orange);
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.card-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--white);
  letter-spacing: 0.1em;
}
.card-sub {
  font-size: 12px;
  color: rgba(255,255,255,0.8);
}

.card-body {
  padding: 20px 24px;
  background: var(--white);
}

.line {
  font-size: 14px;
  line-height: 1.7;
  color: var(--gray-800);
  white-space: pre-wrap;
}
.line.empty { height: 8px; }
</style>
```

- [ ] **Step 4: Commit**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
git add frontend/src/components/
git commit -m "feat: add ChatBubble, PhaseHeader, ConsensusCard components"
```

---

## Task 8: SetupView.vue — 회의 설정 페이지

**Files:**
- Create: `frontend/src/views/SetupView.vue`

- [ ] **Step 1: frontend/src/views/SetupView.vue 생성**

```vue
<template>
  <div class="setup-page">
    <!-- 헤더 -->
    <header class="header">
      <span class="logo-square" />
      <span class="logo-text">TEAM MEETING SIMULATION</span>
    </header>

    <main class="main">
      <!-- 좌측: 안건 + 파일 -->
      <section class="left">
        <div class="field">
          <label class="field-label">안건</label>
          <textarea
            v-model="topic"
            class="textarea"
            placeholder="회의 주제를 입력하세요..."
            rows="4"
          />
        </div>

        <div class="field">
          <label class="field-label">첨부 파일 <span class="optional">(선택)</span></label>
          <div
            class="dropzone"
            :class="{ dragover: isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="onDrop"
            @click="fileInput.click()"
          >
            <input ref="fileInput" type="file" multiple hidden @change="onFileChange" />
            <span v-if="!files.length" class="drop-hint">
              드래그 & 드롭 또는 클릭하여 파일 선택<br />
              <span class="drop-sub">.md .txt .pdf 지원</span>
            </span>
            <ul v-else class="file-list">
              <li v-for="(f, i) in files" :key="i" class="file-item">
                <span class="file-name">{{ f.name }}</span>
                <button class="file-remove" @click.stop="removeFile(i)">×</button>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 우측: 참여자 + 라운드 -->
      <section class="right">
        <div class="field">
          <label class="field-label">참여자</label>
          <div v-if="loadingParticipants" class="loading-text">불러오는 중...</div>
          <ul v-else class="participant-list">
            <li v-for="p in allParticipants" :key="p.slug" class="participant-item">
              <label class="participant-label">
                <input type="checkbox" :value="p.slug" v-model="selectedSlugs" />
                <span class="p-avatar" :style="{ background: p.color }">
                  {{ p.name.slice(0, 2) }}
                </span>
                <span class="p-name">{{ p.name }}</span>
                <span class="tag">{{ p.slug }}</span>
              </label>
            </li>
          </ul>
        </div>

        <div class="field field-inline">
          <label class="field-label">Phase 2 라운드 수</label>
          <input type="number" v-model.number="rounds" class="rounds-input" min="1" max="10" />
        </div>
      </section>
    </main>

    <!-- 시작 버튼 -->
    <footer class="footer">
      <div v-if="error" class="error-msg">{{ error }}</div>
      <button
        class="btn btn-start"
        :disabled="!canStart || isSubmitting"
        @click="startSimulation"
      >
        {{ isSubmitting ? '시뮬레이션 시작 중...' : '시뮬레이션 시작 ──────────' }}
      </button>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const topic = ref('')
const files = ref([])
const selectedSlugs = ref([])
const rounds = ref(3)
const allParticipants = ref([])
const loadingParticipants = ref(true)
const isSubmitting = ref(false)
const error = ref('')
const isDragging = ref(false)
const fileInput = ref(null)

const canStart = computed(() => topic.value.trim() && selectedSlugs.value.length > 0)

onMounted(async () => {
  try {
    const res = await fetch('/api/participants')
    allParticipants.value = await res.json()
    selectedSlugs.value = allParticipants.value.map(p => p.slug)
  } catch (e) {
    error.value = '팀원 목록을 불러오지 못했습니다.'
  } finally {
    loadingParticipants.value = false
  }
})

function onDrop(e) {
  isDragging.value = false
  files.value.push(...Array.from(e.dataTransfer.files))
}
function onFileChange(e) {
  files.value.push(...Array.from(e.target.files))
}
function removeFile(i) {
  files.value.splice(i, 1)
}

async function startSimulation() {
  if (!canStart.value) return
  isSubmitting.value = true
  error.value = ''

  try {
    const formData = new FormData()
    formData.append('topic', topic.value.trim())
    selectedSlugs.value.forEach(s => formData.append('participants', s))
    formData.append('rounds', rounds.value)
    files.value.forEach(f => formData.append('files', f))

    const res = await fetch('/api/run', { method: 'POST', body: formData })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `서버 오류 (${res.status})`)
    }
    const { session_id } = await res.json()

    // 참여자 정보를 sessionStorage 에 보관 (MeetingView 에서 색상 조회용)
    sessionStorage.setItem('participants', JSON.stringify(allParticipants.value))
    router.push({ path: '/meeting', query: { session: session_id } })
  } catch (e) {
    error.value = e.message
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.setup-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 0 40px;
}

/* 헤더 */
.header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 28px 0 24px;
  border-bottom: 1px solid var(--gray-200);
}
.logo-square {
  width: 14px; height: 14px;
  background: var(--orange);
  display: inline-block;
}
.logo-text {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--black);
}

/* 메인 2-컬럼 */
.main {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 48px;
  padding: 36px 0 24px;
  flex: 1;
}

.field { margin-bottom: 28px; }
.field-label {
  display: block;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--gray-600);
  text-transform: uppercase;
  margin-bottom: 8px;
}
.optional { color: var(--gray-400); font-weight: 400; }

.textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  font-family: var(--font-sans);
  font-size: 14px;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
}
.textarea:focus { border-color: var(--black); }

/* 드롭존 */
.dropzone {
  border: 1px dashed var(--gray-400);
  border-radius: 4px;
  padding: 24px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  min-height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dropzone.dragover { border-color: var(--orange); background: #fff5f2; }
.drop-hint { text-align: center; color: var(--gray-600); font-size: 13px; line-height: 1.7; }
.drop-sub { font-size: 11px; color: var(--gray-400); }

.file-list { list-style: none; width: 100%; }
.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  margin-bottom: 4px;
}
.file-name { font-size: 12px; font-family: var(--font-mono); color: var(--gray-800); }
.file-remove {
  background: none; border: none; cursor: pointer;
  font-size: 16px; color: var(--gray-400);
  line-height: 1; padding: 0 4px;
}
.file-remove:hover { color: var(--orange); }

/* 참여자 */
.participant-list { list-style: none; }
.participant-item { margin-bottom: 8px; }
.participant-label {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.participant-label input[type="checkbox"] { accent-color: var(--orange); }
.p-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 11px;
  color: #fff; flex-shrink: 0;
}
.p-name { font-size: 14px; font-weight: 500; flex: 1; }

/* 라운드 입력 */
.field-inline { display: flex; align-items: center; gap: 16px; }
.field-inline .field-label { margin-bottom: 0; }
.rounds-input {
  width: 64px; padding: 6px 10px;
  border: 1px solid var(--gray-200); border-radius: 4px;
  font-family: var(--font-mono); font-size: 14px;
  text-align: center;
}

/* 푸터 */
.footer {
  padding: 20px 0 32px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  border-top: 1px solid var(--gray-200);
}
.btn-start { min-width: 280px; padding: 14px 28px; font-size: 13px; }
.error-msg { color: #DC2626; font-size: 13px; }
.loading-text { color: var(--gray-400); font-size: 13px; }
</style>
```

- [ ] **Step 2: 브라우저에서 SetupView 확인**

`http://localhost:5173` 에서:
- 팀원 체크박스 5명 표시 확인
- 안건 입력 후 시작 버튼 활성화 확인
- 시작 버튼 hover 시 오렌지 색상 확인

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/SetupView.vue
git commit -m "feat: add SetupView with topic input, participant selection, file upload"
```

---

## Task 9: MeetingView.vue — 실시간 채팅 페이지

**Files:**
- Create: `frontend/src/views/MeetingView.vue`

- [ ] **Step 1: frontend/src/views/MeetingView.vue 생성**

```vue
<template>
  <div class="meeting-page">
    <!-- 좌측 사이드바 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <span class="logo-square" />
        <span class="logo-text">MEETING</span>
      </div>

      <div class="sidebar-section">
        <p class="sidebar-label">PARTICIPANTS</p>
        <ul class="p-list">
          <li
            v-for="p in participants"
            :key="p.slug"
            class="p-item"
            :class="{ active: activeSpeaker === p.slug }"
          >
            <span class="p-dot" :style="{ background: activeSpeaker === p.slug ? p.color : 'var(--gray-200)' }" />
            <span class="p-name">{{ p.name }}</span>
          </li>
        </ul>
      </div>

      <div class="sidebar-section">
        <p class="sidebar-label">PROGRESS</p>
        <ul class="phase-steps">
          <li
            v-for="n in 3"
            :key="n"
            class="phase-step"
            :class="{ done: currentPhase > n, active: currentPhase === n }"
          >
            <span class="step-num">0{{ n }}</span>
            <span class="step-label">Phase {{ n }}</span>
          </li>
        </ul>
      </div>

      <div class="sidebar-footer">
        <span class="status-dot" :class="statusClass" />
        <span class="status-text">{{ statusText }}</span>
      </div>
    </aside>

    <!-- 우측 채팅 영역 -->
    <main class="chat-area" ref="chatArea">
      <div class="chat-inner">
        <div class="topic-header">
          <p class="topic-label">AGENDA</p>
          <h1 class="topic-title">{{ topic }}</h1>
        </div>

        <template v-for="(item, i) in feed" :key="i">
          <PhaseHeader v-if="item.type === 'phase'" :label="item.label" />
          <ConsensusCard v-else-if="item.type === 'consensus'" :content="item.content" />
          <ChatBubble
            v-else
            :type="item.type"
            :speaker="item.speaker"
            :slug="item.slug"
            :content="item.content"
            :color="colorOf(item.slug)"
          />
        </template>

        <div v-if="isRunning" class="typing-indicator fade-in-up">
          <span /><span /><span />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChatBubble from '../components/ChatBubble.vue'
import PhaseHeader from '../components/PhaseHeader.vue'
import ConsensusCard from '../components/ConsensusCard.vue'

const route = useRoute()
const router = useRouter()

const sessionId = route.query.session
const topic = ref('')
const feed = ref([])
const participants = ref([])
const activeSpeaker = ref('')
const currentPhase = ref(0)
const isRunning = ref(true)
const isDone = ref(false)
const hasError = ref(false)
const chatArea = ref(null)

let es = null  // EventSource

const statusClass = computed(() => {
  if (hasError.value) return 'error'
  if (isDone.value) return 'done'
  return 'running'
})
const statusText = computed(() => {
  if (hasError.value) return '오류 발생'
  if (isDone.value) return '완료'
  return '시뮬레이션 진행 중'
})

function colorOf(slug) {
  return participants.value.find(p => p.slug === slug)?.color ?? '#999'
}

async function scrollToBottom() {
  await nextTick()
  if (chatArea.value) {
    chatArea.value.scrollTop = chatArea.value.scrollHeight
  }
}

onMounted(() => {
  if (!sessionId) { router.push('/'); return }

  // 참여자 정보 복원
  try {
    participants.value = JSON.parse(sessionStorage.getItem('participants') || '[]')
  } catch (_) {}

  // topic 복원 (sessionStorage 에 없으면 빈 문자열)
  topic.value = sessionStorage.getItem('topic') || ''

  // SSE 연결
  es = new EventSource(`/api/stream/${sessionId}`)

  es.onmessage = async (e) => {
    const event = JSON.parse(e.data)

    if (event.type === 'phase') {
      currentPhase.value = parseInt(event.label.match(/\d+/)?.[0] || '0')
      feed.value.push({ type: 'phase', label: event.label })
    } else if (event.type === 'moderator') {
      activeSpeaker.value = ''
      feed.value.push({ type: 'moderator', content: event.content })
    } else if (event.type === 'message') {
      activeSpeaker.value = event.slug
      feed.value.push({
        type: 'message',
        speaker: event.speaker,
        slug: event.slug,
        content: event.content,
      })
    } else if (event.type === 'done') {
      // 마지막 moderator 메시지가 합의안이므로 ConsensusCard 로 교체
      const last = feed.value[feed.value.length - 1]
      if (last && last.type === 'moderator') {
        feed.value[feed.value.length - 1] = { type: 'consensus', content: last.content }
      }
      isRunning.value = false
      isDone.value = true
      activeSpeaker.value = ''
    } else if (event.type === 'error') {
      isRunning.value = false
      hasError.value = true
      feed.value.push({ type: 'moderator', content: `[오류] ${event.message}` })
    } else if (event.type === 'end') {
      es.close()
    }

    await scrollToBottom()
  }

  es.onerror = () => {
    if (!isDone.value) {
      hasError.value = true
      isRunning.value = false
    }
    es.close()
  }
})

onUnmounted(() => {
  es?.close()
})
</script>

<style scoped>
.meeting-page {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* 사이드바 */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--gray-200);
  display: flex;
  flex-direction: column;
  padding: 24px 20px;
  gap: 28px;
}
.sidebar-header { display: flex; align-items: center; gap: 8px; }
.logo-square { width: 10px; height: 10px; background: var(--orange); display: inline-block; }
.logo-text { font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.1em; color: var(--black); }
.sidebar-label {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.08em; color: var(--gray-400);
  text-transform: uppercase; margin-bottom: 10px;
}
.sidebar-section { }

/* 참여자 목록 */
.p-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.p-item { display: flex; align-items: center; gap: 8px; }
.p-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; transition: background 0.3s; }
.p-name { font-size: 13px; color: var(--gray-800); }
.p-item.active .p-name { color: var(--black); font-weight: 600; }

/* 페이즈 스텝 */
.phase-steps { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.phase-step { display: flex; align-items: center; gap: 8px; opacity: 0.35; transition: opacity 0.3s; }
.phase-step.active { opacity: 1; }
.phase-step.done { opacity: 0.6; }
.step-num { font-family: var(--font-mono); font-size: 11px; color: var(--orange); width: 20px; }
.step-label { font-size: 12px; color: var(--gray-800); }

/* 상태 표시 */
.sidebar-footer { margin-top: auto; display: flex; align-items: center; gap: 8px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.running { background: var(--orange); animation: pulse 1.4s ease-in-out infinite; }
.status-dot.done { background: #16A34A; }
.status-dot.error { background: #DC2626; }
.status-text { font-family: var(--font-mono); font-size: 11px; color: var(--gray-600); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}

/* 채팅 영역 */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 0 40px;
}
.chat-inner {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 0 60px;
}

/* 안건 헤더 */
.topic-header { margin-bottom: 24px; }
.topic-label {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.08em; color: var(--gray-400);
  text-transform: uppercase; margin-bottom: 4px;
}
.topic-title {
  font-size: 22px; font-weight: 700; color: var(--black); line-height: 1.3;
}

/* 타이핑 인디케이터 */
.typing-indicator {
  display: flex; gap: 4px; padding: 12px 0 0 48px;
}
.typing-indicator span {
  width: 6px; height: 6px; border-radius: 50%; background: var(--gray-400);
  animation: typing 1.2s ease-in-out infinite;
}
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30%           { transform: translateY(-6px); opacity: 1; }
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/MeetingView.vue
git commit -m "feat: add MeetingView with SSE real-time chat display"
```

---

## Task 10: .gitignore 업데이트 + 최종 통합 테스트

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: .gitignore에 frontend 빌드 산출물 추가**

`.gitignore`에 추가:

```
# Frontend 빌드 산출물
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 2: topic을 sessionStorage에 저장 — SetupView.vue 수정**

`SetupView.vue`의 `startSimulation` 함수에서 `router.push(...)` 직전에 추가:

```javascript
sessionStorage.setItem('topic', topic.value.trim())
```

즉, 아래 코드를 찾아서:
```javascript
    router.push({ path: '/meeting', query: { session: session_id } })
```

그 바로 위에 추가:
```javascript
    sessionStorage.setItem('topic', topic.value.trim())
```

- [ ] **Step 3: 백엔드 서버 기동**

터미널 1:
```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
uvicorn web.app:app --reload --port 8000
```

- [ ] **Step 4: 프론트엔드 서버 기동**

터미널 2:
```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation\frontend
npm run dev
```

- [ ] **Step 5: 브라우저에서 전체 플로우 테스트**

`http://localhost:5173` 접속 후:
1. 안건 입력 (짧은 주제로 테스트: "간단한 테스트 회의")
2. 참여자 2명만 선택 (빠른 테스트용)
3. Phase 2 라운드 1로 설정
4. "시뮬레이션 시작" 클릭
5. MeetingView로 자동 이동 확인
6. 사이드바 상태 점 깜빡임 확인
7. 발언이 순서대로 채팅창에 등장하는 것 확인
8. Phase 구분선이 오렌지로 표시되는 것 확인
9. 완료 후 ConsensusCard가 오렌지 테두리로 표시되는 것 확인
10. 사이드바 상태가 "완료"(녹색 점)로 바뀌는 것 확인

- [ ] **Step 6: Commit**

```bash
cd C:\Users\leecy\Desktop\eric_code\team-meeting-simulation
git add .gitignore frontend/src/views/SetupView.vue
git commit -m "chore: update gitignore, fix topic sessionStorage in SetupView"
```

- [ ] **Step 7: GitHub push**

```bash
git push origin master
```

---

## 실행 요약

```bash
# 백엔드
uvicorn web.app:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd frontend && npm run dev

# 브라우저
open http://localhost:5173
```
