<template>
  <div class="extract-page">
    <!-- 헤더 -->
    <header class="header">
      <span class="logo-square" />
      <span class="logo-text">SLACK SKILL EXTRACTION</span>
      <button class="back-btn" @click="router.push('/')">← 돌아가기</button>
    </header>

    <!-- Step 1: 탐색 시작 -->
    <main v-if="step === 1" class="main">
      <div class="intro">
        <p class="hint">
          <code>.env</code>에 설정된 Slack 채널에서 3개 이상 메시지를 보낸 팀원을 자동으로 탐색합니다.
        </p>
      </div>
      <div v-if="discoverError" class="error-msg">{{ discoverError }}</div>
      <footer class="footer">
        <button class="btn btn-start" :disabled="isDiscovering" @click="doDiscover">
          {{ isDiscovering ? '탐색 중...' : '채널 탐색 시작 ──────────' }}
        </button>
      </footer>
    </main>

    <!-- Step 2: 후보 확인 + slug 편집 -->
    <main v-else-if="step === 2" class="main">
      <p class="section-label">발견된 팀원 ({{ candidates.length }}명, 메시지 3개 이상 기준)</p>
      <ul class="candidate-list">
        <li
          v-for="c in candidates"
          :key="c.user_id"
          class="candidate-item"
          :class="{ selected: selectedIds.includes(c.user_id) }"
        >
          <input type="checkbox" :value="c.user_id" v-model="selectedIds" />
          <div class="cand-info">
            <span class="cand-name">{{ c.display_name }}</span>
            <span class="cand-badge">{{ c.message_count }}개</span>
          </div>
          <div class="cand-intake">
            <input
              class="slug-input"
              v-model="c.editedSlug"
              @input="sanitizeSlug(c)"
              placeholder="slug"
              :disabled="!selectedIds.includes(c.user_id)"
            />
            <select class="role-select" v-model="c.role" :disabled="!selectedIds.includes(c.user_id)">
              <option value="general">역할 선택</option>
              <option value="backend">백엔드 엔지니어</option>
              <option value="frontend">프론트엔드 엔지니어</option>
              <option value="ml">AI/ML 엔지니어</option>
              <option value="pm">프로덕트 매니저</option>
              <option value="data">데이터 분석가</option>
            </select>
            <input
              class="impression-input"
              v-model="c.impression"
              placeholder="한 마디 인상 (선택사항)"
              maxlength="200"
              :disabled="!selectedIds.includes(c.user_id)"
            />
          </div>
        </li>
      </ul>
      <!-- 메시지 한도 설정 -->
      <div class="limit-panel">
        <p class="section-label">추출 설정</p>
        <div class="limit-row">
          <label class="limit-label">
            메시지 수집 한도
            <span
              class="tooltip-icon"
              title="Slack API에서 유저당 수집할 최대 메시지 수.&#10;5000 이상은 Rate Limit 위험 (초당 API 호출 제한).&#10;10000 이상은 수집 시간이 매우 길어짐."
            >?</span>
          </label>
          <input type="number" class="limit-input" v-model.number="maxCollect" min="100" max="10000" step="100" />
        </div>
        <div class="limit-row">
          <label class="limit-label">
            LLM 분석 메시지 수
            <span
              class="tooltip-icon"
              title="Claude에 전달할 최대 메시지 수.&#10;300까지 안전 (약 60K 토큰).&#10;1000 이상은 컨텍스트 초과 위험."
            >?</span>
          </label>
          <input type="number" class="limit-input" v-model.number="maxMessages" min="50" max="500" step="50" />
        </div>
      </div>

      <div v-if="extractError" class="error-msg">{{ extractError }}</div>
      <footer class="footer">
        <button
          class="btn btn-start"
          :disabled="!canExtract || isExtracting"
          @click="doExtract"
        >
          {{ isExtracting
            ? '시작 중...'
            : `선택한 ${selectedIds.length}명 스킬 추출 시작 ──────────` }}
        </button>
      </footer>
    </main>

    <!-- Step 3: 추출 진행 중 (SSE) -->
    <main v-else-if="step === 3" class="main step3">
      <p class="section-label">추출 진행 중 ({{ doneCount }}/{{ members.length }})</p>
      <div
        v-for="m in members"
        :key="m.slug"
        class="member-card"
        :class="{
          active: m.slug === currentSlug,
          done: m.done,
          errored: m.errored
        }"
      >
        <div class="member-header">
          <div class="member-title">
            <span class="member-name">{{ m.display_name }}</span>
            <span class="member-slug">{{ m.slug }}</span>
          </div>
          <span class="member-idx">[{{ m.index }}/{{ members.length }}]</span>
        </div>
        <div v-if="m.slug === currentSlug || m.done || m.errored" class="member-steps">
          <div
            v-for="s in m.steps"
            :key="s.key"
            class="step-row"
            :class="{ 'step-done': s.done, 'step-active': s.active }"
          >
            <span class="step-icon">{{ s.done ? '✓' : s.active ? '⟳' : '○' }}</span>
            <span class="step-text">{{ s.label }}</span>
            <span v-if="s.active && s.startedAt" class="step-elapsed">
              {{ Math.floor((now - s.startedAt) / 1000) }}s
            </span>
          </div>
          <div v-if="m.errored" class="member-error">{{ m.errorMsg }}</div>
        </div>
        <div v-if="m.done && m.persona_summary.length" class="persona-summary">
          <p v-for="(line, i) in m.persona_summary" :key="i" class="persona-line">{{ line }}</p>
        </div>
      </div>

      <p v-if="globalError" class="global-error">{{ globalError }}</p>

      <div v-if="isDone" class="done-banner">
        ✓ 모든 팀원 스킬 추출 완료! 잠시 후 메인 화면으로 이동합니다...
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// ── 상태 ──────────────────────────────────────────────────────────────────────
const step = ref(1)
const candidates = ref([])
const selectedIds = ref([])

const members = ref([])
const currentSlug = ref(null)
const isDone = ref(false)
const doneCount = computed(() => members.value.filter(m => m.done).length)

const isDiscovering = ref(false)
const isExtracting = ref(false)
const discoverError = ref('')
const extractError = ref('')
const globalError = ref('')

// 추출 설정 (프론트에서 조정 가능)
const maxCollect = ref(2000)
const maxMessages = ref(300)

const canExtract = computed(() => selectedIds.value.length > 0)

// ── 경과 시간 타이머 ─────────────────────────────────────────────────────────
const now = ref(Date.now())
let _timerHandle = null
onMounted(() => { _timerHandle = setInterval(() => { now.value = Date.now() }, 1000) })
onUnmounted(() => { clearInterval(_timerHandle) })

// ── Step 1: 탐색 ──────────────────────────────────────────────────────────────
async function doDiscover() {
  isDiscovering.value = true
  discoverError.value = ''

  try {
    const res = await fetch('/api/slack/discover')
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `서버 오류 (${res.status})`)
    }
    const raw = await res.json()
    candidates.value = raw.map(c => ({
      ...c,
      editedSlug: c.suggested_slug,
      role: 'general',
      impression: '',
    }))

    if (!candidates.value.length) {
      discoverError.value =
        '3개 이상 메시지를 보낸 팀원을 찾지 못했습니다. 채널 설정을 확인하세요.'
      return
    }

    selectedIds.value = candidates.value.map(c => c.user_id)
    step.value = 2
  } catch (e) {
    discoverError.value = e.message
  } finally {
    isDiscovering.value = false
  }
}

// ── Step 2: 추출 시작 ─────────────────────────────────────────────────────────
async function doExtract() {
  isExtracting.value = true
  extractError.value = ''

  const selected = candidates.value.filter(c =>
    selectedIds.value.includes(c.user_id)
  )
  const body = selected.map(c => ({
    user_id: c.user_id,
    slug: c.editedSlug || c.suggested_slug,
    display_name: c.display_name,
    role: c.role || 'general',
    impression: c.impression || '',
  }))

  members.value = body.map((m, i) => ({
    slug: m.slug,
    display_name: m.display_name,
    index: i + 1,
    done: false,
    errored: false,
    errorMsg: '',
    persona_summary: [],
    steps: [
      { key: 'collecting',      label: '메시지 수집',      done: false, active: false, startedAt: null },
      { key: 'work_extract',    label: '업무 패턴 추출',   done: false, active: false, startedAt: null },
      { key: 'work_build',      label: '업무 프로필 생성', done: false, active: false, startedAt: null },
      { key: 'persona_extract', label: '페르소나 추출',    done: false, active: false, startedAt: null },
      { key: 'persona_build',   label: '페르소나 생성',    done: false, active: false, startedAt: null },
      { key: 'writing',         label: '파일 생성',        done: false, active: false, startedAt: null },
    ],
  }))

  try {
    const res = await fetch('/api/slack/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        members: body,
        max_collect: maxCollect.value,
        max_messages: maxMessages.value,
      }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `서버 오류 (${res.status})`)
    }
    const { session_id } = await res.json()
    step.value = 3
    subscribeSSE(session_id)
  } catch (e) {
    extractError.value = e.message
    isExtracting.value = false
  }
}

// ── Step 3: SSE 구독 ──────────────────────────────────────────────────────────
function subscribeSSE(sessionId) {
  const es = new EventSource(`/api/slack/stream/${sessionId}`)

  es.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (data.type === 'end') {
      es.close()
      return
    }

    const member = members.value.find(m => m.slug === data.slug)

    if (data.type === 'collecting') {
      currentSlug.value = data.slug
      if (member) activateStep(member, 'collecting')

    } else if (data.type === 'analyzing') {
      if (member) {
        const stepOrder = ['collecting', 'work_extract', 'work_build', 'persona_extract', 'persona_build', 'writing']
        const currentIdx = stepOrder.indexOf(data.step)
        if (currentIdx > 0) completeStep(member, stepOrder[currentIdx - 1])
        activateStep(member, data.step)
      }

    } else if (data.type === 'writing') {
      if (member) {
        completeStep(member, 'persona_build')
        activateStep(member, 'writing')
      }

    } else if (data.type === 'member_done') {
      if (member) {
        completeStep(member, 'writing')
        member.done = true
        if (data.persona_summary && data.persona_summary.length) {
          member.persona_summary = data.persona_summary
        }
      }
      currentSlug.value = null

    } else if (data.type === 'done') {
      isDone.value = true
      setTimeout(() => router.push('/'), 3000)

    } else if (data.type === 'error' && data.slug) {
      const m = members.value.find(m => m.slug === data.slug)
      if (m) {
        m.errored = true
        m.errorMsg = data.message
      }
    } else if (data.type === 'error') {
      globalError.value = data.message
    }
  }

  es.onerror = () => es.close()
}

function sanitizeSlug(c) {
  c.editedSlug = c.editedSlug.toLowerCase().replace(/[^a-z0-9_]/g, '')
}

function activateStep(member, key) {
  const s = member.steps.find(s => s.key === key)
  if (s) { s.active = true; s.done = false; s.startedAt = Date.now() }
}

function completeStep(member, key) {
  const s = member.steps.find(s => s.key === key)
  if (s) { s.done = true; s.active = false; s.startedAt = null }
}
</script>

<style scoped>
.extract-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 0 40px;
}

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
  flex: 1;
}
.back-btn {
  background: none;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gray-600);
  padding: 6px 12px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.back-btn:hover { border-color: var(--black); color: var(--black); }

.main {
  display: flex;
  flex-direction: column;
  padding: 36px 0 24px;
  flex: 1;
  max-width: 640px;
}
.section-label {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--gray-600);
  text-transform: uppercase;
  margin-bottom: 16px;
}
.hint {
  font-size: 14px;
  color: var(--gray-600);
  line-height: 1.7;
  margin-bottom: 32px;
}
.hint code {
  font-family: var(--font-mono);
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 12px;
}
.error-msg { color: #DC2626; font-size: 13px; margin-bottom: 16px; }

.footer { padding: 20px 0; display: flex; flex-direction: column; gap: 10px; }
.btn {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.05em;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-start {
  background: var(--black);
  color: #fff;
  padding: 14px 28px;
  text-align: left;
}
.btn-start:hover:not(:disabled) { background: #222; }

.candidate-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.candidate-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  transition: border-color 0.2s;
}
.candidate-item.selected { border-color: var(--black); }
.candidate-item input[type="checkbox"] { accent-color: var(--orange); flex-shrink: 0; }
.cand-info { display: flex; align-items: center; gap: 8px; flex: 1; }
.cand-name { font-size: 14px; font-weight: 500; }
.cand-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  padding: 2px 8px;
  color: var(--gray-600);
}
.cand-intake {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.slug-input {
  font-family: var(--font-mono);
  font-size: 11px;
  width: 90px;
  padding: 3px 7px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  background: var(--gray-50);
  color: var(--black);
}
.slug-input:focus { outline: none; border-color: var(--orange); }
.slug-input:disabled { color: var(--gray-400); }
.role-select {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 3px 6px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  background: var(--gray-50);
  color: var(--gray-600);
}
.role-select:disabled { color: var(--gray-400); }
.impression-input {
  font-size: 12px;
  width: 140px;
  padding: 3px 7px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  background: var(--gray-50);
}
.impression-input:focus { outline: none; border-color: var(--orange); }
.impression-input:disabled { color: var(--gray-400); }

.step3 { max-width: 540px; }
.member-card {
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  margin-bottom: 10px;
  overflow: hidden;
  transition: border-color 0.2s;
}
.member-card.active { border-color: var(--orange); }
.member-card.done { border-color: #16A34A; }
.member-card.errored { border-color: #DC2626; }

.member-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--gray-50);
}
.member-title { display: flex; align-items: center; gap: 8px; }
.member-name { font-size: 14px; font-weight: 500; }
.member-slug { font-family: var(--font-mono); font-size: 11px; color: var(--gray-400); }
.member-idx { font-family: var(--font-mono); font-size: 11px; color: var(--gray-400); }

.member-steps { padding: 10px 16px 12px; }
.step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  color: var(--gray-400);
  font-size: 13px;
}
.step-row.step-done { color: #16A34A; }
.step-row.step-active { color: var(--black); font-weight: 500; }
.step-icon { font-family: var(--font-mono); width: 16px; }
.step-elapsed {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gray-400);
}

.member-error {
  margin-top: 8px;
  font-size: 12px;
  color: #DC2626;
  font-family: var(--font-mono);
}

.persona-summary {
  padding: 8px 16px 12px;
  border-top: 1px solid var(--gray-200);
}
.persona-line {
  font-size: 12px;
  color: var(--gray-600);
  line-height: 1.6;
  margin: 0;
}
.persona-line + .persona-line {
  margin-top: 4px;
}

.global-error { color: #DC2626; font-size: 13px; margin-top: 12px; }

.done-banner {
  margin-top: 24px;
  padding: 16px 20px;
  background: #F0FDF4;
  border: 1px solid #16A34A;
  border-radius: 4px;
  font-size: 14px;
  color: #15803D;
}

/* 추출 설정 패널 */
.limit-panel {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.limit-panel .section-label { margin-bottom: 4px; }
.limit-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.limit-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--gray-600);
}
.tooltip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--gray-200);
  color: var(--gray-600);
  font-size: 10px;
  font-style: normal;
  cursor: help;
}
.tooltip-icon:hover { background: var(--gray-400); color: #fff; }
.limit-input {
  width: 90px;
  padding: 5px 8px;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 13px;
  text-align: right;
}
.limit-input:focus { outline: none; border-color: var(--black); }
</style>
