<template>
  <div class="bubble fade-in-up" :class="type">
    <!-- 사회자 -->
    <template v-if="type === 'moderator'">
      <div class="mod-text md-body" v-html="renderedContent" />
    </template>

    <!-- 팀원 -->
    <template v-else>
      <div class="avatar" :style="{ background: color }">
        {{ initials }}
      </div>
      <div class="body">
        <div class="header">
          <span class="speaker">{{ speaker }}</span>
          <span class="tag">{{ slug }}</span>
          <!-- 근거 아이콘 -->
          <div v-if="evidence && evidence.length > 0" class="evidence-badge" @click="showEvidenceModal">
            <span class="badge-icon">📎</span>
            <span class="badge-label">근거</span>
          </div>
        </div>
        <div class="content md-body" v-html="renderedContent" />
      </div>
    </template>
  </div>

  <!-- 근거 모달 -->
  <div v-if="isEvidenceModalOpen" class="evidence-modal-overlay" @click.self="isEvidenceModalOpen = false">
    <div class="evidence-modal">
      <div class="modal-header">
        <h3>근거 (관련 과거 발언)</h3>
        <button class="close-btn" @click="isEvidenceModalOpen = false">✕</button>
      </div>
      <div class="modal-body">
        <div v-for="(item, idx) in evidence" :key="idx" class="evidence-item">
          <div class="evidence-index">{{ idx + 1 }}</div>
          <div class="evidence-text">{{ item }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { renderMarkdown } from '../utils/markdown'

interface Props {
  type: 'message' | 'moderator'
  speaker?: string
  slug?: string
  content: string
  color?: string
  evidence?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  speaker: '',
  slug: '',
  color: '#999',
  evidence: undefined,
})

const isEvidenceModalOpen = ref(false)

const initials = computed(() =>
  props.speaker ? props.speaker.slice(0, 2) : '??'
)

const renderedContent = computed(() => renderMarkdown(props.content))

const showEvidenceModal = () => {
  isEvidenceModalOpen.value = true
}
</script>

<style scoped>
.bubble { display: flex; gap: 12px; padding: 6px 0; }

/* 사회자 */
.bubble.moderator {
  justify-content: center;
  padding: 12px 0;
}
.mod-text {
  font-style: italic;
  color: var(--gray-600);
  font-size: 13px;
  text-align: center;
  max-width: 560px;
}

/* 팀원 */
.avatar {
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
}

.body { flex: 1; min-width: 0; }

.header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.speaker {
  font-family: var(--font-head);
  font-size: 13px;
  font-weight: 600;
  color: var(--black);
}
.tag {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 6px;
  border: 1px solid var(--gray-200);
  border-radius: 3px;
  color: var(--gray-600);
}

.content {
  font-size: 14px;
  line-height: 1.65;
  color: var(--gray-800);
  background: var(--gray-50);
  padding: 10px 14px;
  border-radius: 0 8px 8px 8px;
  border: 1px solid var(--gray-200);
  word-break: break-word;
}

/* 근거 배지 */
.evidence-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: #f0f5ff;
  border: 1px solid #b8d4ff;
  border-radius: 12px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
  color: #2563eb;
  transition: all 0.2s ease;
}

.evidence-badge:hover {
  background: #e0ebff;
  border-color: #80b9ff;
}

.badge-icon {
  font-size: 10px;
}

.badge-label {
  font-family: var(--font-mono);
}

/* 근거 모달 */
.evidence-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.evidence-modal {
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  max-width: 500px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid var(--gray-200);
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--black);
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--gray-600);
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.2s ease;
}

.close-btn:hover {
  background: var(--gray-100);
}

.modal-body {
  overflow-y: auto;
  padding: 16px;
  flex: 1;
}

.evidence-item {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--gray-50);
  border-left: 3px solid #2563eb;
  border-radius: 4px;
}

.evidence-index {
  font-size: 12px;
  font-weight: 600;
  color: white;
  background: #2563eb;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.evidence-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--gray-700);
  word-break: break-word;
}
</style>
