<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, describeApiError } from '../api/client'
import type { components } from '../api/schema'

const rows = ref<components['schemas']['EntryRead'][]>([])
const loading = ref(false)
const message = ref('')
async function load() {
  loading.value = true
  message.value = ''
  try {
    const { data, error } = await api.GET('/api/v1/catalog', {
      params: { query: { offset: 0, limit: 20 } },
    })
    if (error) message.value = describeApiError(error)
    rows.value = data?.items ?? []
  } catch {
    message.value = '后台连接失败，请先启动 API。'
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <section class="panel">
    <div class="panel-title">
      <div>
        <span class="eyebrow">MODULE / CATALOG</span>
        <h2>模式目录</h2>
      </div>
      <el-button :loading="loading" @click="load">重新加载</el-button>
    </div>
    <p>这条接口已实现服务端个人范围过滤；认证接入前会拒绝访问，不回退为共享演示列表。</p>
    <el-alert v-if="message" :title="message" type="warning" :closable="false" show-icon />
    <el-table v-loading="loading" :data="rows" empty-text="暂无可访问记录">
      <el-table-column prop="name" label="模式名称" min-width="180" />
      <el-table-column prop="description" label="描述" min-width="240" />
      <el-table-column prop="row_version" label="版本" width="100" />
    </el-table>
  </section>
</template>
