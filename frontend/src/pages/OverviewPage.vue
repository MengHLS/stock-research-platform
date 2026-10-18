<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, callApi } from '../api/client'
import type { ApiFailure } from '../api/errors'

type ProbeState = 'checking' | 'connected' | 'unready' | 'failed'

const state = ref<ProbeState>('checking')
const version = ref('—')
const authentication = ref<'not_configured' | null>(null)
const failure = ref<ApiFailure | null>(null)
let controller: AbortController | null = null

/** 健康探活走 diagnostic 策略：5 秒超时、不重试，只回答“现在是否可用”。 */
async function probe() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  state.value = 'checking'
  failure.value = null
  const result = await callApi((signal) => api.GET('/health/live', { signal }), {
    access: 'diagnostic',
    signal: current.signal,
  })
  if (controller !== current) return
  if (!result.ok) {
    // 主动取消（页面已离开）不改变状态，也不展示错误。
    if (result.failure.kind === 'aborted') return
    state.value = 'failed'
    failure.value = result.failure
    version.value = '—'
    authentication.value = null
    return
  }
  state.value = result.data.status === 'ok' ? 'connected' : 'unready'
  version.value = result.data.version
  authentication.value = result.data.authentication
}

const tagType = computed(() => {
  if (state.value === 'connected') return 'success'
  if (state.value === 'failed' || state.value === 'unready') return 'danger'
  return 'info'
})

const label = computed(() => {
  switch (state.value) {
    case 'connected':
      return '已连接'
    case 'unready':
      return '未就绪'
    case 'failed':
      return '未连接'
    default:
      return '检查中'
  }
})

onMounted(probe)
onUnmounted(() => controller?.abort())
</script>

<template>
  <section class="hero panel">
    <div class="eyebrow">FOUNDATION / 01</div>
    <h2>先把基础搭稳，<br />再把研究接进来。</h2>
    <p>
      前后端分离、业务模块清晰、接口类型自动生成。这里展示实际工程状态，不模拟研究收益或任务完成。
    </p>
    <div class="hero-bottom">
      <el-tag :type="tagType">API {{ label }}</el-tag
      ><span>版本 {{ version }}</span>
    </div>
    <el-alert
      v-if="authentication === 'not_configured'"
      title="登录模块尚未接入（AUTH_NOT_CONFIGURED），私人资源不可访问。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert v-if="failure" :title="failure.message" type="error" :closable="false" show-icon>
      <p class="request-id">
        <template v-if="failure.requestId">
          请求编号 request_id：<code>{{ failure.requestId }}</code>
        </template>
        <template v-else>本次失败没有收到 request_id。</template>
      </p>
    </el-alert>
  </section>
  <div class="cards">
    <section class="panel">
      <span class="eyebrow">01 / FRONTEND</span>
      <h3>Vue 3 + TypeScript</h3>
      <p>Vite、Vue Router、Pinia、Element Plus。页面只通过有类型的 HTTP 客户端访问后台。</p>
    </section>
    <section class="panel">
      <span class="eyebrow">02 / BACKEND</span>
      <h3>FastAPI + SQLAlchemy</h3>
      <p>接口、校验和业务实现分开；Alembic 管理新工程结构，迁移不在服务启动时自动执行。</p>
    </section>
    <section class="panel">
      <span class="eyebrow">03 / EXECUTION</span>
      <h3>独立 Worker</h3>
      <p>持久化平台作业、幂等提交、租约与恢复基础。目前只注册数据库诊断，研究执行器待接入。</p>
    </section>
  </div>
  <section class="panel next-step">
    <h3>明确的下一步</h3>
    <p>
      接入真实身份与会话 → 完成私人资源验收 → 迁移模式研究与复盘。当前没有默认用户，也没有生产认证。
    </p>
    <el-alert
      title="这是可运行的开发框架，不是已上线的多用户产品。"
      type="warning"
      :closable="false"
      show-icon
    />
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
