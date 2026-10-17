import { createRouter, createWebHistory } from 'vue-router'
import OverviewPage from './pages/OverviewPage.vue'
import CatalogPage from './pages/CatalogPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: OverviewPage, meta: { title: '工程概览' } },
    { path: '/patterns', component: CatalogPage, meta: { title: '模式目录' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
