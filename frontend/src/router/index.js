import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'

const routes = [
  { path: '/', name: 'dashboard', component: DashboardView },
  // TODO: 组员各自加自己的页面路由
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
