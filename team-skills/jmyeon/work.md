# 연준명 (jmyeon) 업무 스킬 분석

## 1. 주요 담당 업무 영역

### 🤖 AI 에이전트 & 슬랙봇 개발
- 슬랙봇 고도화 및 멀티 에이전트 연동 구조 설계
- NXClaw(로컬 AI 에이전트) 슬랙봇 연동 개발
- 티켓 발행, Cron Job 등 자동화 기능 구현
- MCP(Model Context Protocol) 기반 API 서버 구축

### 📊 데이터 수집 & 파이프라인
- 슬랙, 노션, Git, Jira, Confluence, M365 등 다양한 소스 데이터 수집기 개발
- GCS(Google Cloud Storage) 기반 데이터 적재 파이프라인 구축
- Snowflake 연동 및 일일 배치 처리 구현
- Vertex AI Search용 JSONL 변환 스크립트 개발

### 🔍 RAG & 검색 시스템
- Graphiti(Knowledge Graph) 기반 RAG 구현 및 테스트
- Neo4j Docker 환경 구축
- Vertex AI Search 연동
- 검색 정확도 및 속도 개선 작업

### 🧠 Skill 추출 & 개인화 에이전트
- LLM 기반 업무 스킬 자동 추출 시스템 개발
- colleague.skill 프로젝트 (디지털 동료 복제 도구)
- 개인화 에이전트 아이디어 기획 및 구현

---

## 2. 사용하는 기술 스택

### Cloud & Infrastructure
```
GCP (Google Cloud Platform)
├── Cloud Run
├── GCS (Google Cloud Storage)
├── Vertex AI Search
└── Gen App Builder

Snowflake (데이터 웨어하우스)
Neo4j (그래프 DB, Docker)
WSL (Windows Subsystem for Linux)
```

### AI & LLM
```
Claude (Anthropic) - Enterprise 사용
Gemini / Gemini CLI
Graphiti (Knowledge Graph + LLM)
RAG 시스템 설계
MCP (Model Context Protocol)
OpenClaw / NXClaw
```

### 개발 언어 & 프레임워크
```
Python (주력)
├── collect_raw.py, gcs_upload, gcs_sync.py
├── graphiti_client.py
└── datastore_prep.py
Node.js / npm
PowerShell
```

### 협업 & 데이터 소스 연동
```
Slack API (슬랙봇 개발)
Notion API
Git / GitLab
Jira
Confluence
M365 (MS Graph API)
```

---

## 3. 업무 처리 스타일

### ✅ 빠른 실행 & 공유 우선
> *"빠르게 먼저 스펙 공유드립니다"*, *"일단 마무리 하였습니다"*
- 완벽한 완성보다 빠른 프로토타입 배포 후 피드백 수렴
- 구현 완료 즉시 팀에 공유하는 습관

### ✅ 문서화 & 기록 중시
- 구두 논의 내용을 즉시 슬랙에 기록
- 노션 페이지로 정리 후 공유하는 루틴 보유
- 코드 정리 시 아카이브 폴더 분리 등 체계적 관리

### ✅ 협업 지향적 개발
- 작업 전 팀원과 역할 분담 확인 (*"내용 안겹치게 진행하기 위해"*)
- 다른 팀원이 바로 사용할 수 있도록 설치/실행 가이드 함께 제공
- 코드 리뷰 및 의견 요청을 적극적으로 함

### ✅ 점진적 개선
- 버그 수정 → 배포 → 피드백 → 재개선 사이클 반복
- 기존 코드 정리(아카이브) 후 새 버전으로 전환

---

## 4. 기술적 기준과 철학

### 🔑 신뢰성 & 정확성 우선
> *"신뢰성을 어떻게 확보할까에 집중해서 skill 추출을 해봤습니다"*
- 데이터 품질과 검색 정확도를 핵심 지표로 삼음
- 잘못된 결과에 대한 사용자 승인 프로세스 설계

### 🔑 확장성 고려 설계
> *"수집 대상이 확장될 경우 GCS 지금 위치에 계속 수집해도 무방하겠죠?"*
- 초기 설계 단계부터 확장 가능성을 고려
- 팀 단위 → 실 단위 → 전사 단위 확장을 염두에 둔 아키텍처

### 🔑 적합한 도구 선택
> *"어떤 곳에 적합한지 좀 더 파악해서 한정적으로 구축해서 사용하는 방식이 알맞을 수 있"*
- 기술 트렌드를 맹목적으로 따르지 않고 적합성 검토 후 도입
- 단순 RAG vs Knowledge Graph 등 상황별 최적 솔루션 판단

### 🔑 비용 효율 의식
> *"Knowledge Graph 사용해서 claude code 토큰 아끼는 프로젝트"*, *"gemini cli랑 조합해서 쓰면 충분하겠네요"*
- LLM 토큰 비용을 항상 고려한 설계
- 여러 모델 조합으로 비용 최적화 추구

---

## 5. 커뮤니케이션 패턴

### 💬 정보 공유형 리더
- 외부 기술 트렌드(논문, 블로그, GitHub)를 적극적으로 팀에 공유
- 단순 링크 공유가 아닌 **팀 업무와의 연관성 해석**을 함께 제공

### 💬 친근하고 겸손한 톤
- `(_ _)`, `ㅋㅋ`, `~` 등 부드러운 어투 사용
- 아이디어 공유 시 *"진짜 막 생각난거 그대로 적은 거라 참고만 하고 넘어가주세요"* 등 부담 없는 제안 방식

### 💬 명확한 액션 아이템 제시
- 팀원에게 요청 시 예시(example)와 함께 구체적인 형식 제공
- 완료 사항과 진행 중 사항을 명확히 구분하여 공유

### 💬 선제적 소통
- 부재 일정 사전 공지 철저
- 토큰 소진 예상 시 미리 증설 요청하는 등 선제적 대응

---

## 📋 종합 요약

| 구분 | 평가 |
|------|------|
| **핵심 역량** | AI 에이전트 개발, 데이터 파이프라인, RAG 시스템 |
| **강점** | 빠른 실행력, 팀 협업, 기술 트렌드 감지 |
| **개발 스타일** | 프로토타입 우선 → 점진적 개선 |
| **기술 철학** | 신뢰성 + 확장성 + 비용 효율 |
| **포지션** | 풀스택 AI 엔지니어 (기획 감각 보유) |