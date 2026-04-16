<template>
  <div class="not-found-page">
    <div class="not-found-content">
      <span class="not-found-code">404</span>
      <p class="not-found-msg">페이지를 찾을 수 없습니다</p>
      <button class="btn" @click="router.push('/')">메인으로 돌아가기</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<style scoped>
.not-found-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}

.not-found-content {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.not-found-code {
  font-family: var(--font-mono);
  font-size: 72px;
  font-weight: 700;
  color: var(--gray-200);
  letter-spacing: 0.05em;
}

.not-found-msg {
  font-size: 16px;
  color: var(--gray-600);
}
</style>
