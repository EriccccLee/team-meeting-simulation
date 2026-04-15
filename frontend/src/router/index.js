import { createRouter, createWebHistory } from 'vue-router'
import SetupView from '../views/SetupView.vue'
import MeetingView from '../views/MeetingView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: SetupView },
    { path: '/meeting', component: MeetingView },
  ],
})
