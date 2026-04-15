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
          <li v-for="slug in data.participants" :key="slug" class="p-item">
            <span class="p-dot" :style="{ background: colorOf(slug) }" />
            <span class="p-name">{{ nameOf(slug) }}</span>
          </li>
        </ul>
      </div>

      <div class="sidebar-section">
        <p class="sidebar-label">PROGRESS</p>
        <ul class="phase-steps">
          <li v-for="n in 3" :key="n" class="phase-step done">
            <span class="step-num">0{{ n }}</span>
            <span class="step-label">Phase {{ n }}</span>
          </li>
        </ul>
      </div>

      <div class="sidebar-footer">
        <span class="status-dot done" />
        <span class="status-text">{{ formatDate(data.timestamp) }}</span>
      </div>

      <button class="new-meeting-btn" @click="router.push('/')">
        ＋ 새 회의 시작
      </button>
    </aside>

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

function colorOf(slug) {
  return participants.value.find(p => p.slug === slug)?.color ?? '#999'
}
function nameOf(slug) {
  return participants.value.find(p => p.slug === slug)?.name ?? slug
}
function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,'0')}.${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

onMounted(async () => {
  try {
    const [histRes, partRes] = await Promise.all([
      fetch(`/api/history/${route.params.sessionId}`),
      fetch('/api/participants'),
    ])
    if (!histRes.ok) throw new Error('기록을 찾을 수 없습니다.')
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

/* 사이드바 — MeetingView 와 동일 */
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

.p-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.p-item { display: flex; align-items: center; gap: 8px; }
.p-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.p-name { font-size: 13px; color: var(--gray-800); }

.phase-steps { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.phase-step { display: flex; align-items: center; gap: 8px; opacity: 0.6; }
.phase-step.done { opacity: 0.6; }
.step-num { font-family: var(--font-mono); font-size: 11px; color: var(--orange); width: 20px; }
.step-label { font-size: 12px; color: var(--gray-800); }

.sidebar-footer { margin-top: auto; display: flex; align-items: center; gap: 8px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.done { background: #16A34A; }
.status-text { font-family: var(--font-mono); font-size: 11px; color: var(--gray-600); }

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
