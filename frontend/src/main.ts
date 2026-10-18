import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElAlert, ElButton, ElLoading, ElTable, ElTableColumn, ElTag } from 'element-plus'
import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-loading.css'
import 'element-plus/theme-chalk/el-table.css'
import 'element-plus/theme-chalk/el-table-column.css'
import 'element-plus/theme-chalk/el-tag.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import { setUnauthorizedHandler } from './api/client'
import { router } from './router'
import { useSession } from './stores/session'
import './styles/base.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(ElAlert)
app.use(ElButton)
app.use(ElLoading)
app.use(ElTable)
app.use(ElTableColumn)
app.use(ElTag)

// Wire "401 means the session is gone" once, at composition time. The request
// layer stays UI-agnostic; this is the single place that connects it to the store
// and to navigation.
const session = useSession(pinia)
setUnauthorizedHandler(() => {
  if (!session.isAuthenticated) return
  session.expire()
  const current = router.currentRoute.value
  if (current.meta.public !== true) {
    void router.replace({ name: 'login', query: { redirect: current.fullPath } })
  }
})

app.mount('#app')
