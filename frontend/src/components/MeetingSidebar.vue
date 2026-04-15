<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <span class="logo-square" />
      <span class="logo-text">{{ logoText }}</span>
    </div>

    <div class="sidebar-section">
      <p class="sidebar-label">PARTICIPANTS</p>
      <ul class="p-list">
        <li
          v-for="p in participants"
          :key="p.slug"
          class="p-item"
          :class="{ active: activeSpeaker === p.slug && activeSpeaker !== '' }"
        >
          <span
            class="p-dot"
            :style="{ background: activeSpeaker && activeSpeaker !== p.slug ? 'var(--gray-200)' : p.color }"
          />
          <span class="p-name">{{ p.name }}</span>
        </li>
      </ul>
    </div>

    <div class="sidebar-section" v-if="phases.length">
      <p class="sidebar-label">PROGRESS</p>
      <ul class="phase-steps">
        <li
          v-for="(phase, i) in phases"
          :key="i"
          class="phase-step"
          :class="phase.state"
        >
          <span class="step-num">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="step-label">{{ phase.label }}</span>
        </li>
      </ul>
    </div>

    <div class="sidebar-footer">
      <span class="status-dot" :class="statusDot" />
      <span class="status-text">{{ statusText }}</span>
    </div>

    <button class="new-meeting-btn" @click="$emit('new-meeting')">
      ＋ 새 회의 시작
    </button>
  </aside>
</template>

<script setup>
defineProps({
  logoText:     { type: String,  default: 'MEETING' },
  participants: { type: Array,   default: () => [] },
  activeSpeaker:{ type: String,  default: '' },
  phases:       { type: Array,   default: () => [] },
  statusDot:    { type: String,  default: '' },
  statusText:   { type: String,  default: '' },
})

defineEmits(['new-meeting'])
</script>

<style scoped>
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
.sidebar-section { }

/* 참여자 목록 */
.p-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.p-item { display: flex; align-items: center; gap: 8px; }
.p-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; transition: background 0.3s; }
.p-name { font-size: 13px; color: var(--gray-800); }
.p-item.active .p-name { color: var(--black); font-weight: 600; }

/* 페이즈 스텝 */
.phase-steps { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.phase-step { display: flex; align-items: center; gap: 8px; opacity: 0.35; transition: opacity 0.3s; }
.phase-step.active { opacity: 1; }
.phase-step.done { opacity: 0.6; }
.step-num { font-family: var(--font-mono); font-size: 11px; color: var(--orange); width: 20px; }
.step-label { font-size: 12px; color: var(--gray-800); }

/* 상태 표시 */
.sidebar-footer { display: flex; align-items: center; gap: 8px; margin-top: auto; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.running { background: var(--orange); animation: pulse 1.4s ease-in-out infinite; }
.status-dot.done { background: #16A34A; }
.status-dot.error { background: #DC2626; }
.status-text { font-family: var(--font-mono); font-size: 11px; color: var(--gray-600); }

/* 새 회의 버튼 */
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

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
</style>
