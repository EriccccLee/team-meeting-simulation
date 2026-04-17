import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import SetupView from '../views/SetupView.vue'
import MeetingView from '../views/MeetingView.vue'
import HistoryView from '../views/HistoryView.vue'
import ExtractionView from '../views/ExtractionView.vue'
import NotFoundView from '../views/NotFoundView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', component: SetupView },
  { path: '/meeting', component: MeetingView },
  { path: '/history/:sessionId', component: HistoryView },
  { path: '/extract', component: ExtractionView },
  { path: '/:pathMatch(.*)*', component: NotFoundView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 페이지 로드 시 진행 중인 session_id가 있으면 자동으로 /meeting으로 이동
router.beforeEach((to, from, next) => {
  const activeSessionId = localStorage.getItem('activeSessionId')

  // /meeting 페이지로 가는 경우
  if (to.path === '/meeting') {
    // query에 session이 없으면 localStorage에서 session_id 가져오기
    if (!to.query.session && activeSessionId) {
      next({ path: '/meeting', query: { session: activeSessionId } })
    } else {
      next()
    }
  }
  // /에서 다른 곳으로 가려고 할 때
  else if (to.path !== '/meeting' && to.path !== '/extract' && to.path !== '/history' && activeSessionId) {
    // 진행 중인 session이 있으면 /meeting으로 리디렉트
    next({ path: '/meeting', query: { session: activeSessionId } })
  } else {
    next()
  }
})

export default router
