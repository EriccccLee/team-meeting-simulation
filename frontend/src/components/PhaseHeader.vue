<template>
  <div class="phase-header fade-in-up">
    <div class="line" />
    <span class="label">{{ label }}</span>
    <div class="line" />
  </div>
</template>

<script setup lang="ts">
defineProps<{ label: string }>()
</script>

<style scoped>
.phase-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 0 12px;
}
.line {
  flex: 1;
  height: 1px;
  background: var(--gray-200);
}
.label {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--orange);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}
</style>
