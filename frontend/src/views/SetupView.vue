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
              <span class="drop-sub">.md .txt .pdf .xlsx .csv .docx .pptx 지원</span>
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

    <!-- 회의 기록 -->
    <section v-if="historyList.length" class="history-section">
      <p class="history-label">HISTORY</p>
      <ul class="history-list">
        <li
          v-for="h in historyList"
          :key="h.session_id"
          class="history-item"
          @click="router.push(`/history/${h.session_id}`)"
        >
          <div class="h-left">
            <span class="h-topic">{{ h.topic }}</span>
            <span class="h-participants">{{ h.participants.join(' · ') }}</span>
          </div>
          <div class="h-right">
            <span class="h-date">{{ formatDate(h.timestamp) }}</span>
            <button class="h-del" @click.stop="deleteHistory(h.session_id)" title="삭제">×</button>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const historyList = ref([])

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

  try {
    const res = await fetch('/api/history')
    historyList.value = await res.json()
  } catch (_) {}
})

function formatDate(iso) {
  const d = new Date(iso)
  return `${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,'0')}.${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

async function deleteHistory(sessionId) {
  await fetch(`/api/history/${sessionId}`, { method: 'DELETE' })
  historyList.value = historyList.value.filter(h => h.session_id !== sessionId)
}

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

    sessionStorage.setItem('participants', JSON.stringify(allParticipants.value))
    sessionStorage.setItem('topic', topic.value.trim())
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

/* 회의 기록 */
.history-section {
  padding: 32px 0 48px;
  border-top: 1px solid var(--gray-200);
  margin-top: 8px;
}
.history-label {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--gray-400);
  text-transform: uppercase;
  margin-bottom: 12px;
}
.history-list { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.history-item:hover { border-color: var(--gray-400); background: var(--gray-50); }
.h-left { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.h-topic {
  font-size: 14px;
  font-weight: 500;
  color: var(--black);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 480px;
}
.h-participants { font-family: var(--font-mono); font-size: 11px; color: var(--gray-400); }
.h-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.h-date { font-family: var(--font-mono); font-size: 11px; color: var(--gray-600); }
.h-del {
  background: none; border: none; cursor: pointer;
  font-size: 16px; color: var(--gray-400); line-height: 1; padding: 0 4px;
}
.h-del:hover { color: #DC2626; }
</style>
