import { createRouter, createWebHistory } from 'vue-router'
import SetupView from '../views/SetupView.vue'
import MeetingView from '../views/MeetingView.vue'
import HistoryView from '../views/HistoryView.vue'
import ExtractionView from '../views/ExtractionView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: SetupView },
    { path: '/meeting', component: MeetingView },
    { path: '/history/:sessionId', component: HistoryView },
    { path: '/extract', component: ExtractionView },
  ],
})
