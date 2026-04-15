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

      <button class="new-meeting-btn" @click="startNewMeeting">
        ＋ 새 회의 시작
      </button>
    </aside>

    <!-- 우측 채팅 영역 -->
    <main class="chat-area" ref="chatArea">
      <div class="chat-inner">
        <div class="topic-header">
          <p class="topic-label">AGENDA</p>
          <h1 class="topic-title">{{ topic }}</h1>
        </div>

        <!-- 파일 전처리 진행 상황 -->
        <div v-if="preprocessingFiles.length" class="preprocessing-panel fade-in-up">
          <p class="pre-title">
            <span class="pre-spinner" v-if="isPreprocessing" />
            {{ isPreprocessing ? '파일 변환 중...' : '파일 변환 완료' }}
          </p>
          <ul class="pre-list">
            <li v-for="f in preprocessingFiles" :key="f.filename" class="pre-item">
              <span class="pre-check" :class="{ done: f.done }">{{ f.done ? '✓' : '○' }}</span>
              <span class="pre-msg">{{ f.message }}</span>
            </li>
          </ul>
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
const preprocessingFiles = ref([])  // [{filename, message, done}]
const isPreprocessing = computed(() => preprocessingFiles.value.some(f => !f.done))

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

onMounted(async () => {
  if (!sessionId) { router.push('/'); return }

  // 참여자 정보 복원 — sessionStorage 없으면 API fallback
  try {
    const cached = JSON.parse(sessionStorage.getItem('participants') || '[]')
    if (cached.length > 0) {
      participants.value = cached
    } else {
      const res = await fetch('/api/participants')
      if (res.ok) {
        participants.value = await res.json()
      } else {
        hasError.value = true
        isRunning.value = false
      }
    }
  } catch (_) {
    hasError.value = true
    isRunning.value = false
  }

  // topic 복원
  topic.value = sessionStorage.getItem('topic') || ''

  // SSE 연결
  if (hasError.value) return
  es = new EventSource(`/api/stream/${sessionId}`)

  es.onmessage = async (e) => {
    const event = JSON.parse(e.data)

    if (event.type === 'preprocessing') {
      const existing = preprocessingFiles.value.find(f => f.filename === event.filename)
      if (existing) {
        existing.message = event.message
        existing.done = event.done
      } else {
        preprocessingFiles.value.push({ filename: event.filename, message: event.message, done: event.done })
      }
    } else if (event.type === 'phase') {
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

function startNewMeeting() {
  es?.close()
  router.push('/')
}
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
.sidebar-footer { display: flex; align-items: center; gap: 8px; margin-top: auto; }

/* 새 회의 버튼 */
.new-meeting-btn {
  width: 100%;
  margin-top: 12px;
  padding: 8px 0;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  background: none;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  color: var(--gray-600);
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.new-meeting-btn:hover { border-color: var(--orange); color: var(--orange); }
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

/* 파일 전처리 패널 */
.preprocessing-panel {
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 20px;
  background: var(--gray-50);
}
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
