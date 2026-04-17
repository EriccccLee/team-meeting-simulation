<template>
  <div class="participant-info fade-in-up">
    <div class="info-header">
      <span class="info-title">👥 팀원 및 초기 입장</span>
    </div>
    <div class="participant-grid">
      <div v-for="p in participants" :key="p.slug" class="participant-item">
        <div class="participant-avatar">{{ p.name.slice(0, 2) }}</div>
        <div class="participant-content">
          <div class="participant-name">{{ p.name }}</div>
          <div class="stance-badge" :class="`stance-${p.stance}`">
            {{ stanceLabel(p.stance) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Participant {
  name: string
  slug: string
  stance: string
}

interface Props {
  participants: Participant[]
}

defineProps<Props>()

const stanceLabel = (stance: string): string => {
  const labels: Record<string, string> = {
    support: '✓ 지지',
    oppose: '✗ 반대',
    neutral: '◇ 중립',
    pending: '◯ 대기중',
  }
  return labels[stance] || stance
}
</script>

<style scoped>
.participant-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  margin: 8px 0;
}

.info-header {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--black);
}

.info-title {
  font-family: var(--font-head);
}

.participant-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.participant-item {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px;
  background: white;
  border-radius: 6px;
  border: 1px solid var(--gray-150);
  transition: all 0.2s ease;
}

.participant-item:hover {
  border-color: var(--gray-300);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.participant-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: white;
  background: #666;
  flex-shrink: 0;
}

.participant-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.participant-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--black);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stance-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  width: fit-content;
  font-family: var(--font-mono);
}

.stance-support {
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.stance-oppose {
  background: #fee2e2;
  color: #7f1d1d;
  border: 1px solid #fecaca;
}

.stance-neutral {
  background: #fed7aa;
  color: #7c2d12;
  border: 1px solid #fdba74;
}

.stance-pending {
  background: #e5e7eb;
  color: #374151;
  border: 1px solid #d1d5db;
}
</style>
