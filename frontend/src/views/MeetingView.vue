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
            :color="store.colorOf(item.slug ?? '')"
          />
        </template>

        <div v-if="isRunning" class="typing-indicator fade-in-up">
          <span /><span /><span />
        </div>

        <div v-if="isRunning" class="cancel-area">
          <button class="cancel-btn" @click="cancelMeeting">회의 중단</button>
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

interface FeedItem {
  type: 'phase' | 'moderator' | 'message' | 'consensus'
  label?: string
  content?: string
  speaker?: string
  slug?: string
}

interface PreprocessingFile {
  filename: string
  message: string
  done: boolean
}

const route = useRoute()
const router = useRouter()
const store = useMeetingStore()

const sessionId = route.query.session as string | undefined
const feed = ref<FeedItem[]>([])
const activeSpeaker = ref('')
const currentPhase = ref(0)
const isRunning = ref(true)
const isDone = ref(false)
const hasError = ref(false)
const chatArea = ref<HTMLElement | null>(null)
const preprocessingFiles = ref<PreprocessingFile[]>([])
const isPreprocessing = computed(() => preprocessingFiles.value.some(f => !f.done))
const attachedFiles = ref<string[]>([])

let es: EventSource | null = null

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
  if (!sessionId) { router.push('/'); return }

  try {
    await store.fetchParticipants()
  } catch (_) {
    hasError.value = true
    isRunning.value = false
  }

  if (hasError.value) return
  es = new EventSource(`/api/stream/${sessionId}`)

  es.onmessage = async (e: MessageEvent) => {
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
    } else if (event.type === 'phase') {
      const label = event.label as string
      currentPhase.value = parseInt(label.match(/\d+/)?.[0] || '0')
      feed.value.push({ type: 'phase', label })
    } else if (event.type === 'moderator') {
      activeSpeaker.value = ''
      feed.value.push({ type: 'moderator', content: event.content as string })
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
    } else if (event.type === 'cancelled') {
      isRunning.value = false
      isDone.value = true
      feed.value.push({ type: 'moderator', content: '[시뮬레이션이 중단되었습니다]' })
    } else if (event.type === 'error') {
      isRunning.value = false
      hasError.value = true
      feed.value.push({ type: 'moderator', content: `[오류] ${event.message}` })
    } else if (event.type === 'end') {
      es?.close()
    }

    await scrollToBottom()
  }

  es.onerror = () => {
    if (!isDone.value) {
      hasError.value = true
      isRunning.value = false
    }
    es?.close()
  }
})

onUnmounted(() => {
  es?.close()
})

function startNewMeeting(): void {
  es?.close()
  store.topic = ''
  router.push('/')
}

async function cancelMeeting(): Promise<void> {
  if (!confirm('진행 중인 시뮬레이션을 중단하시겠습니까?')) return
  try {
    await fetch(`/api/stream/${sessionId}`, { method: 'DELETE' })
  } catch (_) {}
  isDone.value = true
  es?.close()
  isRunning.value = false
  router.push('/')
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
</style>
