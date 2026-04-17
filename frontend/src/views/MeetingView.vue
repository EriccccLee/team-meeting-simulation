<template>
  <div class="meeting-page">
    <!-- 좌측 사이드바 -->
    <MeetingSidebar
      logo-text="MEETING"
      :participants="store.participants"
      :active-speaker="activeSpeaker"
      :phases="phaseSteps"
      :status-dot="statusClass"
      :status-text="statusText"
      :attachments="attachedFiles"
      @new-meeting="startNewMeeting"
    />

    <!-- 우측 채팅 영역 -->
    <main class="chat-area" ref="chatArea">
      <div class="chat-inner">
        <div class="topic-header">
          <p class="topic-label">AGENDA</p>
          <h1 class="topic-title">{{ store.topic }}</h1>
        </div>

        <!-- 파일 전처리 진행 상황 -->
        <div v-if="preprocessingFiles.length || preprocessError" class="preprocessing-panel fade-in-up">
          <p class="pre-title">
            <span class="pre-spinner" v-if="isPreprocessing && !preprocessError" />
            {{ preprocessError ? '파일 변환 오류' : isPreprocessing ? '파일 변환 중...' : '파일 변환 완료' }}
          </p>
          <ul class="pre-list">
            <li v-for="f in preprocessingFiles" :key="f.filename" class="pre-item">
              <span class="pre-check" :class="{ done: f.done }">{{ f.done ? '✓' : '○' }}</span>
              <span class="pre-msg">{{ f.message }}</span>
            </li>
          </ul>
          <p v-if="preprocessError" class="pre-error">{{ preprocessError }}</p>
        </div>

        <!-- 웹 사전 검색 상태 -->
        <div v-if="searchingStatus !== 'idle'" class="preprocessing-panel searching-panel fade-in-up">
          <p class="pre-title">
            <span class="pre-spinner" v-if="searchingStatus === 'running'" />
            <span v-else class="pre-check" :class="{ done: searchFound }">{{ searchFound ? '✓' : '○' }}</span>
            {{
              searchingStatus === 'running' ? '웹 검색 중...' :
              searchFound ? '웹 검색 완료 — 결과를 회의 자료로 주입했습니다' :
              '웹 검색 결과 없음 — 학습 데이터 기반으로 진행합니다'
            }}
          </p>
        </div>

        <template v-for="(item, i) in feed" :key="i">
          <PhaseHeader v-if="item.type === 'phase'" :label="item.label" />
          <ConsensusCard v-else-if="item.type === 'consensus'" :content="item.content" />
          <ToolUseBubble
            v-else-if="item.type === 'tool_use'"
            :speaker="item.speaker ?? ''"
            :slug="item.slug ?? ''"
            :tool-name="item.tool_name ?? ''"
            :tool-input="item.tool_input ?? {}"
            :failed="item.tool_failed ?? false"
            :color="store.colorOf(item.slug ?? '')"
          />
          <ChatBubble
            v-else
            :type="item.type"
            :speaker="item.speaker"
            :slug="item.slug"
            :content="item.content"
            :color="store.colorOf(item.slug ?? '')"
          />
        </template>

        <div v-if="isRunning" class="typing-indicator fade-in-up">
          <span /><span /><span />
        </div>

        <div v-if="isRunning" class="cancel-area">
          <button class="cancel-btn" @click="cancelMeeting">회의 중단</button>
        </div>

        <div v-if="isDone && !hasError" class="followup-area fade-in-up">
          <button class="btn followup-btn" @click="startFollowUp">후속 회의 시작</button>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMeetingStore } from '../stores/meeting'
import '../assets/chat-layout.css'
import MeetingSidebar from '../components/MeetingSidebar.vue'
import ChatBubble from '../components/ChatBubble.vue'
import PhaseHeader from '../components/PhaseHeader.vue'
import ConsensusCard from '../components/ConsensusCard.vue'
import ToolUseBubble from '../components/ToolUseBubble.vue'

interface FeedItem {
  type: 'phase' | 'moderator' | 'message' | 'consensus' | 'tool_use'
  label?: string
  content?: string
  speaker?: string
  slug?: string
  tool_name?: string
  tool_input?: Record<string, unknown>
  tool_failed?: boolean
}

interface PreprocessingFile {
  filename: string
  message: string
  done: boolean
}

const route = useRoute()
const router = useRouter()
const store = useMeetingStore()

const feed = ref<FeedItem[]>([])
const activeSpeaker = ref('')
const currentPhase = ref(0)
const isRunning = ref(true)
const isDone = ref(false)
const hasError = ref(false)
const chatArea = ref<HTMLElement | null>(null)
const preprocessingFiles = ref<PreprocessingFile[]>([])
const preprocessError = ref<string | null>(null)
const isPreprocessing = computed(() => preprocessingFiles.value.some(f => !f.done))
const attachedFiles = ref<string[]>([])
const searchingStatus = ref<'idle' | 'running' | 'done'>('idle')
const searchFound = ref(false)

// Fix 1: SSE EventSource as a ref so it is trackable across all exit paths
const es = ref<EventSource | null>(null)

let preprocessTimeout: ReturnType<typeof setTimeout> | null = null

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

const PHASE_COUNT = 3
const phaseSteps = computed(() =>
  Array.from({ length: PHASE_COUNT }, (_, i) => ({
    label: `Phase ${i + 1}`,
    state: currentPhase.value > i + 1 ? 'done'
         : currentPhase.value === i + 1 ? 'active'
         : '',
  }))
)

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (chatArea.value) {
    chatArea.value.scrollTop = chatArea.value.scrollHeight
  }
}

onMounted(async () => {
  // Fix 3: Validate session query parameter before doing anything
  const rawSession = route.query.session
  const sessionId = typeof rawSession === 'string' ? rawSession.trim() : ''
  if (!sessionId) {
    router.push('/')
    return
  }

  try {
    await store.fetchParticipants()
  } catch (_) {
    hasError.value = true
    isRunning.value = false
  }

  if (hasError.value) return

  // Fix 1: Close any pre-existing connection before creating a new one
  if (es.value) { es.value.close(); es.value = null }
  es.value = new EventSource(`/api/stream/${sessionId}`)

  // Fix 2: Safety timeout — if preprocessing takes more than 120s, show an error
  preprocessTimeout = setTimeout(() => {
    if (preprocessingFiles.value.some(f => !f.done)) {
      preprocessError.value = '파일 변환 시간이 초과되었습니다. 파일 형식을 확인해주세요.'
    }
    preprocessTimeout = null
  }, 120000)

  es.value.onmessage = async (e: MessageEvent) => {
    const event = JSON.parse(e.data) as Record<string, unknown>

    if (event.type === 'preprocessing') {
      const existing = preprocessingFiles.value.find(f => f.filename === event.filename)
      if (existing) {
        existing.message = event.message as string
        existing.done = event.done as boolean
      } else {
        preprocessingFiles.value.push({
          filename: event.filename as string,
          message: event.message as string,
          done: event.done as boolean,
        })
      }
      if (!attachedFiles.value.includes(event.filename as string)) {
        attachedFiles.value.push(event.filename as string)
      }
      // Clear the preprocessing timeout once all files are done
      if (!isPreprocessing.value && preprocessTimeout !== null) {
        clearTimeout(preprocessTimeout)
        preprocessTimeout = null
      }
    } else if (event.type === 'preprocessing_error') {
      // Fix 2: Surface preprocessing errors sent by the backend
      preprocessError.value = (event.message as string | undefined) ?? '파일 변환 중 오류가 발생했습니다.'
      if (preprocessTimeout !== null) { clearTimeout(preprocessTimeout); preprocessTimeout = null }
    } else if (event.type === 'phase') {
      const label = event.label as string
      currentPhase.value = parseInt(label.match(/\d+/)?.[0] || '0')
      feed.value.push({ type: 'phase', label })
    } else if (event.type === 'moderator') {
      activeSpeaker.value = ''
      feed.value.push({ type: 'moderator', content: event.content as string })
    } else if (event.type === 'searching') {
      searchingStatus.value = event.status as 'running' | 'done'
      if (event.status === 'done') {
        searchFound.value = (event.found as boolean) ?? false
      }
    } else if (event.type === 'tool_use') {
      feed.value.push({
        type: 'tool_use',
        speaker: event.speaker as string,
        slug: event.slug as string,
        tool_name: event.tool_name as string,
        tool_input: event.tool_input as Record<string, unknown>,
        tool_failed: (event.failed as boolean) ?? false,
      })
    } else if (event.type === 'message') {
      activeSpeaker.value = event.slug as string
      feed.value.push({
        type: 'message',
        speaker: event.speaker as string,
        slug: event.slug as string,
        content: event.content as string,
      })
    } else if (event.type === 'done') {
      const last = feed.value[feed.value.length - 1]
      if (last && last.type === 'moderator') {
        feed.value[feed.value.length - 1] = { type: 'consensus', content: last.content }
      }
      isRunning.value = false
      isDone.value = true
      activeSpeaker.value = ''
      // 시뮬레이션 완료 후 localStorage에서 activeSessionId 제거
      localStorage.removeItem('activeSessionId')
    } else if (event.type === 'cancelled') {
      isRunning.value = false
      isDone.value = true
      feed.value.push({ type: 'moderator', content: '[시뮬레이션이 중단되었습니다]' })
      // 중단 후 localStorage에서 activeSessionId 제거
      localStorage.removeItem('activeSessionId')
    } else if (event.type === 'error') {
      isRunning.value = false
      hasError.value = true
      feed.value.push({ type: 'moderator', content: `[오류] ${event.message}` })
      // 오류 발생 시 localStorage에서 activeSessionId 제거
      localStorage.removeItem('activeSessionId')
    } else if (event.type === 'end') {
      // Fix 1: Null out the ref after closing
      if (es.value) { es.value.close(); es.value = null }
    }

    await scrollToBottom()
  }

  es.value.onerror = () => {
    if (!isDone.value) {
      hasError.value = true
      isRunning.value = false
    }
    // Fix 1: Null out the ref after closing so it doesn't linger
    if (es.value) { es.value.close(); es.value = null }
  }
})

onUnmounted(() => {
  // Fix 1: Clean up SSE connection on unmount
  if (es.value) { es.value.close(); es.value = null }
  // Fix 2: Clear preprocessing timeout on unmount
  if (preprocessTimeout !== null) { clearTimeout(preprocessTimeout); preprocessTimeout = null }
})

function startNewMeeting(): void {
  // Fix 1: Close SSE before navigating away
  if (es.value) { es.value.close(); es.value = null }
  store.topic = ''
  // 새로운 회의 시작할 때 진행 중인 session 제거
  localStorage.removeItem('activeSessionId')
  router.push('/')
}

async function cancelMeeting(): Promise<void> {
  if (!confirm('진행 중인 시뮬레이션을 중단하시겠습니까?')) return
  const sessionId = typeof route.query.session === 'string' ? route.query.session.trim() : ''
  try {
    if (sessionId) await fetch(`/api/stream/${sessionId}`, { method: 'DELETE' })
  } catch (_) {}
  isDone.value = true
  // Fix 1: Close SSE in cancel path
  if (es.value) { es.value.close(); es.value = null }
  isRunning.value = false
  // 중단 시 localStorage에서 activeSessionId 제거
  localStorage.removeItem('activeSessionId')
  router.push('/')
}

function startFollowUp(): void {
  if (es.value) { es.value.close(); es.value = null }
  const sessionId = typeof route.query.session === 'string' ? route.query.session.trim() : ''
  // 후속 회의 시작할 때 진행 중인 session 제거
  localStorage.removeItem('activeSessionId')
  router.push({ path: '/', query: { ref: sessionId } })
}
</script>

<style scoped>
/* 파일 전처리 패널 */
.preprocessing-panel {
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 20px;
  background: var(--gray-50);
}

/* 웹 검색 패널 — 파란색 계열로 구분 */
.searching-panel {
  background: #EFF6FF;
  border-color: #BFDBFE;
}
.searching-panel .pre-title { color: #2563EB; }
.searching-panel .pre-spinner {
  border-color: #BFDBFE;
  border-top-color: #2563EB;
}
.searching-panel .pre-check { color: #93C5FD; }
.searching-panel .pre-check.done { color: #2563EB; }
.pre-title {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gray-600);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.pre-spinner {
  width: 10px; height: 10px;
  border: 2px solid var(--gray-400);
  border-top-color: var(--orange);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
.pre-list { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.pre-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--gray-800); }
.pre-check { font-family: var(--font-mono); font-size: 11px; color: var(--gray-400); width: 14px; flex-shrink: 0; }
.pre-check.done { color: #16A34A; }
.pre-msg { flex: 1; }
.pre-error { margin-top: 8px; font-size: 12px; color: #DC2626; font-family: var(--font-mono); }

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

/* 취소 버튼 */
.cancel-area {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
.cancel-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  padding: 6px 20px;
  background: none;
  border: 1px solid var(--gray-400);
  border-radius: 4px;
  color: var(--gray-600);
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.cancel-btn:hover { border-color: #DC2626; color: #DC2626; }

/* 후속 회의 버튼 */
.followup-area {
  display: flex;
  justify-content: center;
  padding: 24px 0 16px;
}
.followup-btn {
  background: var(--black);
  color: var(--white);
  border: 1px solid var(--black);
  padding: 10px 24px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.04em;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.followup-btn:hover { background: var(--orange); border-color: var(--orange); }
</style>
