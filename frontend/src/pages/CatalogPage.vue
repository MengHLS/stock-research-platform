<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import type { components } from '../api/schema'

const rows = ref<components['schemas']['EntryRead'][]>([])
const loading = ref(false)
const failure = ref<ApiFailure | null>(null)
/** 已成功加载过（区分“确实没有记录”和“还没加载成功”）。 */
const loaded = ref(false)
let controller: AbortController | null = null

const state = computed(() => {
  if (loading.value) return 'loading'
  if (failure.value) return isAuthNotConfigured(failure.value) ? 'auth' : 'failed'
  if (loaded.value && rows.value.length === 0) return 'empty'
  return 'ready'
})

/**
 * 列表走 read 策略：15 秒超时、网络错误与 502/503/504 最多重试 1 次。
 * 每次加载先取消上一次请求，卸载时也取消；旧响应不会再覆盖新结果。
 */
async function load() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  failure.value = null
  const result = await callApi(
    (signal) =>
      api.GET('/api/v1/catalog', {
        params: { query: { offset: 0, limit: 20 } },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (controller !== current) return
  loading.value = false
  if (result.ok) {
    rows.value = result.data.items
    loaded.value = true
    return
  }
  // 主动取消（重新加载或离开页面）不提示错误，也不清掉已有数据。
  if (result.failure.kind === 'aborted') return (failure.value = result.failure)
  rows.value = []
  loaded.value = false
}

function describeFailure(value: ApiFailure): string {
  switch (value.kind) {
    case 'network':
      return '连接失败：无法连接后台服务，请先启动 API。'
    case 'timeout':
      return '连接超时：后台在限定时间内没有响应。'
    case 'invalid-response':
      return '响应异常：后台返回了无法解析的内容。'
    default:
      return value.message
  }
}

/** 表格空态文案必须和失败/认证状态一致，不能把失败说成“没有记录”。 */
const emptyText = computed(() => {
  switch (state.value) {
    case 'auth':
      return '登录模块尚未接入，无法判断目录是否为空'
    case 'failed':
      return '加载失败，未展示任何替代数据'
    case 'empty':
      return '暂无可访问记录'
    default:
      return '加载中'
  }
})

async function copyRequestId(requestId: string) {
  try {
    await navigator.clipboard.writeText(requestId)
  } catch {
    // 剪贴板不可用时编号仍然可见，无需额外报错。
  }
}

onMounted(load)
onUnmounted(() => controller?.abort())
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

    <el-alert
      v-if="state === 'auth'"
      title="登录模块尚未接入（AUTH_NOT_CONFIGURED），暂时无法读取私人目录。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="state === 'failed' && failure"
      :title="describeFailure(failure)"
      type="error"
      :closable="false"
      show-icon
    >
      <p class="request-id">
        <template v-if="failure.requestId">
          请求编号 request_id：<code>{{ failure.requestId }}</code>
          <el-button size="small" text @click="copyRequestId(failure.requestId)">复制</el-button>
        </template>
        <template v-else>本次失败没有收到 request_id。</template>
      </p>
    </el-alert>
    <el-alert
      v-else-if="state === 'empty'"
      title="暂无可访问记录：请求成功，但当前账号范围内没有目录记录。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-table v-loading="loading" :data="rows" :empty-text="emptyText">
      <el-table-column prop="name" label="模式名称" min-width="180" />
      <el-table-column prop="description" label="描述" min-width="240" />
      <el-table-column prop="row_version" label="版本" width="100" />
    </el-table>
  </section>
</template>

<style scoped>
.request-id {
  margin: 8px 0 0;
  font-size: 12px;
}
.request-id code {
  user-select: all;
}
</style>
