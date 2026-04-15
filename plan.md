# 팀 미팅 시뮬레이션 — 기획 설계서

**작성일**: 2026-04-15  
**방식**: AutoGen AssistantAgent + `claude -p` subprocess ModelClient  
**목적**: 팀원의 SKILL.md 페르소나 기반으로 특정 주제/파일에 대해 3단계 구조화 토론을 시뮬레이션하고 합의안을 도출

---

## 1. 개요

### 핵심 아이디어

별도 API 키 없이 Claude Code(`claude -p`) 의 인증을 재사용하는 것이 핵심.  
AutoGen의 `AssistantAgent`로 각 팀원의 페르소나를 표현하되, 실제 LLM 호출은 `subprocess`로 `claude -p`를 호출하는 커스텀 ModelClient를 사용한다.

### 사용 시나리오

- **의사결정 보조**: "RAG 아키텍처 Neo4j vs 벡터DB 어떻게 할까?" → 팀원 반응 사전 파악
- **아이디어 검토**: 기획서 파일을 첨부해서 팀원 시각으로 피드백 수집
- **회의록 생성**: 주제 입력 → 3단계 토론 → 합의안 마크다운 파일 자동 생성

---

## 2. 아키텍처

### 전체 구조

```
CLI 입력 (topic, files, participants, rounds)
        │
        ▼
MeetingOrchestrator
        │
        ├─── Phase 1: 초기 의견 수집
        │      └── 선택된 MeetingAgent 순서대로 직접 호출
        │
        ├─── Phase 2: 자유 토론
        │      └── ModeratorAgent가 다음 발언자 선택 → 해당 MeetingAgent 호출
        │
        └─── Phase 3: 합의 도출
               ├── 팀원 최종 입장 수집 (찬성/수정/반대 + 이유)
               └── ModeratorAgent가 합의안 초안 작성
```

### 컴포넌트 역할

| 컴포넌트 | 파일 | 역할 |
|---------|------|------|
| `ClaudeCodeModelClient` | `simulation/model_client.py` | `claude -p` subprocess 래퍼. AutoGen ModelClient 인터페이스 구현 |
| `MeetingAgent` | `simulation/agents.py` | 팀원 1명 = 1 인스턴스. SKILL.md 로드 → system prompt 구성 |
| `ModeratorAgent` | `simulation/agents.py` | 사회자 에이전트. 단계 전환 선언, 다음 발언자 선택, 합의안 작성 |
| `MeetingOrchestrator` | `simulation/orchestrator.py` | 3단계 흐름 제어, 대화 히스토리 관리 |
| `MeetingSession` | `simulation/session.py` | 실시간 스트리밍 출력 + 마크다운 파일 저장 |
| `cli.py` | `simulation/cli.py` | argparse 기반 진입점 |

---

## 3. 디렉토리 구조

```
team-meeting-simulation/
├── team-skills/                  # 기존 팀원 데이터
│   ├── leecy/
│   │   ├── SKILL.md              # system prompt로 사용
│   │   ├── persona.md
│   │   ├── meta.json
│   │   ├── work.md
│   │   └── slack_messages.json
│   ├── jasonjoe/
│   ├── jmyeon/
│   ├── rockmin/
│   └── philgineer/
│
├── simulation/                   # 구현 패키지
│   ├── __init__.py
│   ├── model_client.py           # ClaudeCodeModelClient
│   ├── agents.py                 # MeetingAgent, ModeratorAgent
│   ├── orchestrator.py           # MeetingOrchestrator
│   ├── session.py                # MeetingSession (출력/저장)
│   └── cli.py                    # 진입점
│
├── outputs/                      # 생성된 회의록 마크다운
│   └── YYYY-MM-DD-HH-MM-<slug>.md
│
├── plan.md                       # 이 문서
└── requirements.txt
```

---

## 4. 컴포넌트 상세 설계

### 4-1. ClaudeCodeModelClient (`model_client.py`)

`claude -p` CLI를 subprocess로 호출하는 ModelClient.

```python
# 인터페이스
class ClaudeCodeModelClient:
    def call(self, system_prompt: str, messages: list[dict]) -> str
```

**구현 방식:**
- `messages`를 `"화자: 내용\n화자: 내용"` 형식으로 직렬화
- `subprocess.run(["claude", "-p", "--system-prompt", system, conversation])` 실행
- stdout을 반환, stderr는 오류 로그용으로 처리
- 타임아웃 설정 (기본 60초)

**claude -p 호출 시 주의사항:**
- `--output-format text` 명시 (기본값이지만 명시적으로)
- `--tools ""` 옵션으로 파일 시스템 등 불필요한 도구 비활성화 (순수 텍스트 응답만)
- Windows 환경이므로 인코딩 `utf-8` 명시

---

### 4-2. MeetingAgent (`agents.py`)

팀원 1명을 대표하는 에이전트. AutoGen `AssistantAgent`를 상속하지 않고, 같은 인터페이스를 구현하는 래퍼 클래스로 구성 (AutoGen 버전 변화에 덜 의존하도록).

```python
@dataclass
class AgentConfig:
    slug: str           # "leecy"
    name: str           # "이창영"
    skill_md: str       # SKILL.md 전체 내용 (frontmatter 제거)
    persona_md: str     # persona.md 전체 내용

class MeetingAgent:
    def __init__(self, config: AgentConfig, model_client: ClaudeCodeModelClient)
    def respond(self, topic: str, history: list[dict], instruction: str) -> str
```

**system prompt 구성:**
```
[SKILL.md 내용 — Part A(업무능력) + Part B(페르소나)]

---
[회의 맥락 주입]
지금 당신은 팀 미팅에 참여 중입니다.
안건: {topic}
{첨부 파일 내용이 있으면 여기에 포함}

위 정체성과 말투를 유지하며 회의에 참여하세요.
다른 팀원의 발언에 반응할 때도 본인 캐릭터를 일관되게 유지하세요.
간결하게 발언하세요 (3~5문장 권장).
```

**SKILL.md 로드 시 frontmatter(---) 제거** 처리.

---

### 4-3. ModeratorAgent (`agents.py`)

사회자 에이전트. 팀원 페르소나 없이, 다음 역할만 수행:

| 동작 | 호출 시점 | 출력 |
|------|---------|------|
| 회의 개회 선언 | Phase 1 시작 전 | 안건 정리 텍스트 |
| 다음 발언자 선택 | Phase 2 매 턴 | 팀원 slug 1개 |
| Phase 전환 선언 | 각 단계 사이 | 전환 안내 텍스트 |
| 합의안 작성 | Phase 3 종료 시 | 합의안 마크다운 블록 |

**다음 발언자 선택 로직 (Phase 2):**
```
prompt: "다음 발언자를 선택하세요. 선택지: {slugs}
현재까지 대화 흐름: {history 요약}
가장 기여할 수 있는 사람 1명의 slug만 출력하세요."
→ LLM 응답에서 slug 파싱
```

---

### 4-4. MeetingOrchestrator (`orchestrator.py`)

3단계 흐름을 순서대로 실행하는 컨트롤러.

```python
class MeetingOrchestrator:
    def __init__(
        self,
        agents: list[MeetingAgent],
        moderator: ModeratorAgent,
        session: MeetingSession,
        config: OrchestratorConfig,
    )
    def run(self, topic: str, files: list[str]) -> MeetingResult

@dataclass
class OrchestratorConfig:
    phase2_rounds: int = 3        # Phase 2 총 발언 횟수
    max_tokens_per_turn: int = 500  # 발언당 최대 토큰 (system prompt 지시)
```

**Phase 1: 초기 의견 수집**
1. Moderator 개회 선언
2. 선택된 팀원 순서대로 1번씩 직접 호출
3. instruction: `"이 안건에 대한 초기 의견을 밝혀주세요."`
4. 각 응답을 history에 추가 + 실시간 출력

**Phase 2: 자유 토론**
1. Moderator Phase 2 선언
2. `phase2_rounds`번 반복:
   - Moderator가 slug 선택
   - 해당 MeetingAgent.respond() 호출
   - instruction: `"다른 팀원의 의견에 반응하거나 새 논점을 제시하세요."`
3. 각 응답 history 추가 + 출력

**Phase 3: 합의 도출**
1. Moderator Phase 3 선언 + 토론 요약
2. 팀원 순서대로 최종 입장 수집
   - instruction: `"최종 입장을 밝혀주세요: 동의/수정 요청/반대 중 하나와 이유를 말해주세요."`
3. Moderator가 최종 입장들을 기반으로 합의안 작성
4. 합의안 출력 + 파일 저장

---

### 4-5. MeetingSession (`session.py`)

출력과 저장을 담당.

```python
class MeetingSession:
    def stream_message(self, speaker: str, content: str) -> None
    def stream_phase(self, phase_name: str) -> None
    def save(self) -> Path  # outputs/ 에 마크다운 저장
```

**터미널 출력 형식:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Phase 1] 초기 의견 수집
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧑 이창영 (leecy)
우선 Neo4j 쪽이 Graph 특성상 관계 탐색에 유리할 것 같은데...
...

🧑 조성훈 (jasonjoe)
...
```

**저장 파일 형식** (`outputs/YYYY-MM-DD-HH-MM-<topic-slug>.md`):
```markdown
# 팀 미팅 시뮬레이션

- **안건**: RAG 아키텍처 선택
- **일시**: 2026-04-15 14:30
- **참석자**: 이창영, 조성훈, 연준명

---

## 안건 상세
{topic + 첨부 파일 내용 요약}

## Phase 1: 초기 의견

### 이창영 (leecy)
...

### 조성훈 (jasonjoe)
...

## Phase 2: 자유 토론

**이창영**: ...
**연준명**: ...

## Phase 3: 최종 입장

| 이름 | 입장 | 이유 |
|------|------|------|
| 이창영 | 동의 | ... |
| 조성훈 | 수정 요청 | ... |

## 합의안

> {Moderator가 작성한 합의안 전문}
```

---

### 4-6. CLI (`cli.py`)

```bash
# 기본 사용법
python -m simulation.cli --topic "RAG 아키텍처 Neo4j vs 벡터DB"

# 파일 첨부
python -m simulation.cli --topic "이 기획서 검토해줘" --files proposal.md data.csv

# 참석자 지정 (기본: 전원)
python -m simulation.cli --topic "배포 전략" --participants leecy jasonjoe philgineer

# Phase 2 라운드 수 조정 (기본 3)
python -m simulation.cli --topic "주제" --rounds 5
```

**argparse 인자:**

| 인자 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--topic` | str | 필수 | 회의 주제 |
| `--files` | list[str] | [] | 첨부 파일 경로들 |
| `--participants` | list[str] | 전원 | 참여 팀원 slug |
| `--rounds` | int | 3 | Phase 2 발언 횟수 |
| `--output-dir` | str | `outputs/` | 결과 파일 저장 경로 |

---

## 5. 데이터 흐름

```
1. CLI 파싱
        │
        ▼
2. team-skills/{slug}/SKILL.md 로드 (참여자별)
   + 첨부 파일 읽기
        │
        ▼
3. ClaudeCodeModelClient 초기화
   MeetingAgent × N 생성 (slug별 system_prompt 구성)
   ModeratorAgent 생성
   MeetingSession 생성
        │
        ▼
4. MeetingOrchestrator.run(topic, file_contents)
   ├── Phase 1: agent.respond() × N  →  stream + history
   ├── Phase 2: moderator.select_speaker() → agent.respond() × rounds  →  stream + history
   └── Phase 3: agent.respond() × N  →  moderator.draft_consensus()  →  stream
        │
        ▼
5. MeetingSession.save()  →  outputs/YYYY-MM-DD-....md
```

---

## 6. 대화 히스토리 관리

모든 phase에 걸쳐 단일 `history: list[dict]` 를 유지.

```python
# 메시지 스키마
{
    "role": "assistant",        # 항상 assistant (LLM 입장에서)
    "speaker": "이창영",        # 실제 발언자 이름
    "slug": "leecy",
    "phase": 1,                 # 1, 2, 3
    "content": "발언 내용..."
}
```

각 에이전트 호출 시 history를 다음과 같이 직렬화해서 전달:
```
이창영: ...
조성훈: ...
[사회자]: Phase 2 시작합니다.
윤준호: ...
```

---

## 7. 오류 처리

| 상황 | 처리 |
|------|------|
| `claude -p` 실패 (exit code ≠ 0) | stderr 로그 출력 후 해당 발언 스킵, 회의 계속 진행 |
| 팀원 slug 없음 | CLI 단에서 즉시 오류 메시지 + 사용 가능 slug 목록 출력 |
| 첨부 파일 없음 | 경고 출력 후 무시, 파일 없이 진행 |
| ModeratorAgent slug 파싱 실패 | 참여자 중 랜덤 선택으로 fallback |
| 타임아웃 (60초 초과) | 재시도 1회, 실패 시 스킵 |

---

## 8. 의존성

```
# requirements.txt 추가 항목
autogen-agentchat>=0.4.0   # AssistantAgent 인터페이스 참조용 (선택)
```

> 실제로는 AutoGen을 직접 상속하지 않고 같은 인터페이스를 구현하므로,
> AutoGen 없이도 동작 가능하게 설계. 추후 GroupChat 기능 추가 시 의존성 활용.

---

## 9. 구현 순서 (Implementation Plan 예정)

1. `model_client.py` — `claude -p` subprocess 래퍼 구현 및 단위 테스트
2. `agents.py` — `MeetingAgent` SKILL.md 로드 + 호출 로직
3. `agents.py` — `ModeratorAgent` (발언자 선택, 합의안 작성)
4. `session.py` — 터미널 출력 + 마크다운 저장
5. `orchestrator.py` — 3단계 흐름 통합
6. `cli.py` — argparse 진입점
7. E2E 테스트 — 실제 `claude -p` 기반 전체 시뮬레이션

---

## 10. 인증 환경별 호환성

`claude -p` subprocess는 **현재 Claude Code의 인증을 그대로 재사용**하므로 별도 API 키 불필요.

| 환경 | authMethod | 동작 여부 |
|------|-----------|---------|
| Nexon Vertex AI (현재) | `third_party` / vertex | ✅ gcloud 인증 자동 사용 |
| Claude Pro 구독 (OAuth) | `oauth` / anthropic | ✅ keychain 토큰 자동 사용 |
| Anthropic API Key | `api_key` / anthropic | ✅ env var 자동 사용 |

현재 인증 상태 확인 방법:
```bash
claude auth status
```

**Claude Pro 사용자 주의**: 1회 시뮬레이션 = 약 17~20회 `claude -p` 호출 발생. 연속 실행 시 rate limit에 걸릴 수 있음. `--rounds` 를 낮게 설정하거나 실행 간 간격을 두는 것을 권장.

---

## 11. 미결 사항 / 향후 고려

- **병렬 호출**: Phase 1 초기 의견 수집 시 팀원들을 asyncio로 병렬 호출 가능 (속도 향상). 초기 버전은 순차 구현 후 고려.
- **Streamlit UI**: CLI 검증 후 웹 UI 추가 가능성
- **few-shot 예시 추가**: SKILL.md의 `slack_messages.json`에서 샘플 메시지를 system prompt에 삽입해 페르소나 정확도 향상
- **팀원 추가**: `team-skills/`에 폴더 추가만으로 자동 인식되도록 설계
