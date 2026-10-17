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
import { router } from './router'
import './style.css'

createApp(App)
  .use(createPinia())
  .use(router)
  .use(ElAlert)
  .use(ElButton)
  .use(ElLoading)
  .use(ElTable)
  .use(ElTableColumn)
  .use(ElTag)
  .mount('#app')
