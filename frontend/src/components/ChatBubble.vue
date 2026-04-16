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
        </div>
        <div class="content md-body" v-html="renderedContent" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../utils/markdown'

interface Props {
  type: 'message' | 'moderator'
  speaker?: string
  slug?: string
  content: string
  color?: string
}

const props = withDefaults(defineProps<Props>(), {
  speaker: '',
  slug: '',
  color: '#999',
})

const initials = computed(() =>
  props.speaker ? props.speaker.slice(0, 2) : '??'
)

const renderedContent = computed(() => renderMarkdown(props.content))
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
</style>
