<template>
  <div class="meeting-page">
    <!-- 좌측 사이드바 -->
    <MeetingSidebar
      logo-text="HISTORY"
      :participants="sidebarParticipants"
      :phases="historyPhaseSteps"
      status-dot="done"
      :status-text="formatDate(data.timestamp)"
      @new-meeting="router.push('/')"
    />

    <!-- 우측 채팅 영역 -->
    <main class="chat-area" ref="chatArea">
      <div v-if="loading" class="loading-wrap">불러오는 중...</div>
      <div v-else-if="error" class="error-wrap">{{ error }}</div>
      <div v-else class="chat-inner">
        <div class="topic-header">
          <p class="topic-label">AGENDA</p>
          <h1 class="topic-title">{{ data.topic }}</h1>
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

        <div class="followup-area">
          <button class="btn followup-btn" @click="startFollowUp">후속 회의 시작</button>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatDate } from '../utils/format'
import { useMeetingStore } from '../stores/meeting'
import '../assets/chat-layout.css'
import MeetingSidebar from '../components/MeetingSidebar.vue'
import ChatBubble from '../components/ChatBubble.vue'
import PhaseHeader from '../components/PhaseHeader.vue'
import ConsensusCard from '../components/ConsensusCard.vue'

interface FeedEvent {
  type: string
  label?: string
  content?: string
  speaker?: string
  slug?: string
}

interface HistoryData {
  topic: string
  participants: string[]
  feed: FeedEvent[]
  timestamp: string
}

const route = useRoute()
const router = useRouter()
const store = useMeetingStore()

const loading = ref(true)
const error = ref('')
const data = ref<HistoryData>({ topic: '', participants: [], feed: [], timestamp: '' })

const feed = computed(() => {
  const items = data.value.feed.filter(e => e.type !== 'done')
  const result = [...items]
  const last = result[result.length - 1]
  if (last && last.type === 'moderator') {
    result[result.length - 1] = { type: 'consensus', content: last.content }
  }
  return result
})

const sidebarParticipants = computed(() =>
  data.value.participants.map(slug => ({
    slug,
    name: store.nameOf(slug),
    color: store.colorOf(slug),
  }))
)

const historyPhaseSteps = [
  { label: 'Phase 1', state: 'done' },
  { label: 'Phase 2', state: 'done' },
  { label: 'Phase 3', state: 'done' },
]

onMounted(async () => {
  try {
    const [histRes] = await Promise.all([
      fetch(`/api/history/${route.params.sessionId}`),
      store.fetchParticipants(),
    ])
    if (!histRes.ok) throw new Error('기록을 찾을 수 없습니다.')
    data.value = await histRes.json()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
})

function startFollowUp(): void {
  router.push({ path: '/', query: { ref: route.params.sessionId as string } })
}
</script>

<style scoped>
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
