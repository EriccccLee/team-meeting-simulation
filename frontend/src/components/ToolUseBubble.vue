<template>
  <div class="tool-bubble fade-in-up" :class="{ failed }">
    <div class="tool-avatar" :style="{ background: failed ? '#9CA3AF' : color }">
      {{ initials }}
    </div>
    <div class="tool-body">
      <div class="tool-header">
        <span class="tool-speaker">{{ speaker }}</span>
        <span class="tool-badge">
          <span class="tool-icon">{{ failed ? '⚠️' : toolIcon }}</span>
          {{ toolName }}
          <span v-if="failed" class="tool-fail-label">차단됨</span>
        </span>
      </div>
      <div class="tool-query" v-if="queryText">
        <span class="tool-query-label">{{ failed ? '시도' : '검색' }}</span>
        <span class="tool-query-text">{{ queryText }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  speaker: string
  slug: string
  toolName: string
  toolInput: Record<string, unknown>
  color?: string
  failed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  color: '#999',
  failed: false,
})

const initials = computed(() =>
  props.speaker ? props.speaker.slice(0, 2) : '??'
)

const toolIcon = computed(() => {
  const name = props.toolName.toLowerCase()
  if (name.includes('search')) return '🔍'
  if (name.includes('fetch') || name.includes('web')) return '🌐'
  if (name.includes('read') || name.includes('file')) return '📄'
  if (name.includes('bash') || name.includes('shell')) return '💻'
  return '⚙️'
})

const queryText = computed(() => {
  const input = props.toolInput
  if (typeof input.query === 'string') return input.query
  if (typeof input.url === 'string') return input.url
  const firstStr = Object.values(input).find(v => typeof v === 'string')
  return typeof firstStr === 'string' ? firstStr : ''
})
</script>

<style scoped>
.tool-bubble {
  display: flex;
  gap: 12px;
  padding: 4px 0;
  opacity: 0.75;
}

.tool-bubble.failed {
  opacity: 0.5;
}

.tool-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  flex-shrink: 0;
  margin-top: 2px;
  opacity: 0.6;
}

.tool-body { flex: 1; min-width: 0; }

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.tool-speaker {
  font-family: var(--font-head);
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-500);
}

/* 성공 배지 — 파란색 */
.tool-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
  padding: 2px 7px;
  background: #EFF6FF;
  color: #2563EB;
  border: 1px solid #BFDBFE;
  border-radius: 3px;
  letter-spacing: 0.03em;
}

/* 실패 배지 — 회색/주황 */
.failed .tool-badge {
  background: #F9FAFB;
  color: #6B7280;
  border-color: #D1D5DB;
}

.tool-fail-label {
  font-size: 9px;
  color: #F59E0B;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.tool-icon { font-size: 11px; }

/* 성공 쿼리 박스 */
.tool-query {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: #F8FAFF;
  border: 1px dashed #BFDBFE;
  border-radius: 0 6px 6px 6px;
  max-width: 480px;
}

/* 실패 쿼리 박스 */
.failed .tool-query {
  background: #F9FAFB;
  border-color: #D1D5DB;
  border-style: dashed;
}

.tool-query-label {
  font-family: var(--font-mono);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #93C5FD;
  flex-shrink: 0;
}
.failed .tool-query-label { color: #9CA3AF; }

.tool-query-text {
  font-size: 12px;
  color: #3B82F6;
  font-style: italic;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.failed .tool-query-text {
  color: #9CA3AF;
  text-decoration: line-through;
}
</style>
