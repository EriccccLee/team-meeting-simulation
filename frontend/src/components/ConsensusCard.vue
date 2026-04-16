<template>
  <div class="consensus-wrap fade-in-up">
    <PhaseHeader label="최종 합의안" />
    <div class="card">
      <div class="card-header">
        <span class="card-tag">CONSENSUS</span>
        <span class="card-sub">팀 합의 결과</span>
      </div>
      <div class="card-body md-body" v-html="renderedContent" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../utils/markdown'
import PhaseHeader from './PhaseHeader.vue'

const props = defineProps<{ content: string }>()

const renderedContent = computed(() => renderMarkdown(props.content))
</script>

<style scoped>
.consensus-wrap { padding-bottom: 40px; }

.card {
  border: 1px solid var(--orange);
  border-radius: 6px;
  overflow: hidden;
}

.card-header {
  background: var(--orange);
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.card-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--white);
  letter-spacing: 0.1em;
}
.card-sub {
  font-size: 12px;
  color: rgba(255,255,255,0.8);
}

.card-body {
  padding: 20px 24px;
  background: var(--white);
  font-size: 14px;
  line-height: 1.7;
  color: var(--gray-800);
}
</style>
