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
            :color="colorOf(item.slug)"
          />
        </template>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatDate } from '../utils/format'
import MeetingSidebar from '../components/MeetingSidebar.vue'
import ChatBubble from '../components/ChatBubble.vue'
import PhaseHeader from '../components/PhaseHeader.vue'
import ConsensusCard from '../components/ConsensusCard.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref('')
const data = ref({ topic: '', participants: [], feed: [], timestamp: '' })
const participants = ref([])  // [{slug, name, color}]

const feed = computed(() => {
  const items = data.value.feed.filter(e => e.type !== 'done')
  // 마지막 moderator → consensus 로 변환 (MeetingView 와 동일 로직)
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
    name: nameOf(slug),
    color: colorOf(slug),
  }))
)

const historyPhaseSteps = [
  { label: 'Phase 1', state: 'done' },
  { label: 'Phase 2', state: 'done' },
  { label: 'Phase 3', state: 'done' },
]

function colorOf(slug) {
  return participants.value.find(p => p.slug === slug)?.color ?? '#999'
}
function nameOf(slug) {
  return participants.value.find(p => p.slug === slug)?.name ?? slug
}
onMounted(async () => {
  try {
    const [histRes, partRes] = await Promise.all([
      fetch(`/api/history/${route.params.sessionId}`),
      fetch('/api/participants'),
    ])
    if (!histRes.ok) throw new Error('기록을 찾을 수 없습니다.')
    if (!partRes.ok) throw new Error('참여자 정보를 불러올 수 없습니다.')
    data.value = await histRes.json()
    participants.value = await partRes.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.meeting-page {
  display: flex;
  height: 100vh;
  overflow: hidden;
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

.loading-wrap, .error-wrap {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--gray-600); font-size: 14px;
}

.topic-header { margin-bottom: 24px; }
.topic-label {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.08em; color: var(--gray-400);
  text-transform: uppercase; margin-bottom: 4px;
}
.topic-title { font-size: 22px; font-weight: 700; color: var(--black); line-height: 1.3; }
</style>
