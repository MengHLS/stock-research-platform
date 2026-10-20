<script setup lang="ts">
/**
 * Engineering overview: real probe results, no simulated research numbers.
 *
 * This page is the "data-health" view in the navigation model, so it reports what
 * the running backend actually says. A failed probe is shown as a failure with its
 * request id — never replaced by placeholder data.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import AppIcon from '../components/AppIcon'
import { api, callApi } from '../api/client'
import type { ApiFailure } from '../api/errors'
import { useSession } from '../stores/session'

type ProbeState = 'checking' | 'connected' | 'unready' | 'failed'

const session = useSession()
const state = ref<ProbeState>('checking')
const version = ref('—')
const failure = ref<ApiFailure | null>(null)
let controller: AbortController | null = null

/** Health probes use the diagnostic policy: 5s timeout, no retry. */
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
    if (result.failure.kind === 'aborted') return
    state.value = 'failed'
    failure.value = result.failure
    version.value = '—'
    return
  }
  state.value = result.data.status === 'ok' ? 'connected' : 'unready'
  version.value = result.data.version
}

const stateClass = computed(() => {
  if (state.value === 'connected') return 'ok'
  if (state.value === 'checking') return 'muted'
  return 'bad'
})

const label = computed(() => {
  switch (state.value) {
    case 'connected':
      return 'API 已连接'
    case 'unready':
      return 'API 未就绪'
    case 'failed':
      return 'API 未连接'
    default:
      return '检查中'
  }
})

onMounted(probe)
onUnmounted(() => controller?.abort())
</script>

<template>
  <div class="overview">
    <section class="panel">
      <span class="eyebrow">FOUNDATION</span>
      <h2>磐石为基，研究其上。</h2>
      <p class="lede">
        前后端分离、业务模块清晰、接口类型自动生成。这里展示实际工程状态，不模拟研究收益或任务完成。
      </p>
      <div class="status-row">
        <span class="pill" :class="`pill--${stateClass}`">
          <AppIcon name="activity" :size="13" />
          {{ label }}
        </span>
        <span class="muted">版本 {{ version }}</span>
        <span v-if="session.isAuthenticated" class="pill pill--ok">
          <AppIcon name="user" :size="13" />
          {{ session.user?.email }}
        </span>
      </div>
      <div v-if="failure" class="failure" role="alert">
        <strong>{{ failure.message }}</strong>
        <p v-if="failure.requestId">
          请求编号 <code>{{ failure.requestId }}</code>
        </p>
        <p v-else>本次失败没有收到 request_id。</p>
      </div>
    </section>

    <div class="cards">
      <section class="panel card">
        <span class="eyebrow">01 / 行情</span>
        <h3>历史复盘总览已接入</h3>
        <p>
          腾讯快照与分钟K线、新浪竞价成交、东方财富竞价曲线、Tushare
          日线；旧研究源的共享历史复盘也已接入。页面区分缺失、部分可评估和真实零值。
        </p>
        <RouterLink class="card__link" to="/market/overview">行情复盘总览 →</RouterLink>
      </section>
      <section class="panel card">
        <span class="eyebrow">02 / 身份</span>
        <h3>注册登录</h3>
        <p>自建账号体系，scrypt 密码哈希与服务端可撤销会话；私人资源按用户隔离。</p>
        <RouterLink class="card__link" to="/research/patterns">模式库 →</RouterLink>
      </section>
      <section class="panel card">
        <span class="eyebrow">03 / 执行</span>
        <h3>独立 Worker</h3>
        <p>持久化作业、幂等提交、租约与恢复。目前只注册数据库诊断，研究执行器待接入。</p>
      </section>
    </div>

    <section class="panel">
      <h3>下一步</h3>
      <p>按原型继续补齐策略与版本、数据集和决策日志。页面在设计就绪前不显示示例数据。</p>
    </section>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
}

.panel {
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--muted);
}

h2 {
  margin: 10px 0 10px;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.35;
}

h3 {
  margin: 8px 0 8px;
  font-size: 15px;
  font-weight: 600;
}

.lede {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--fg2);
  max-width: 640px;
}

p {
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--fg2);
}

.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid var(--border2);
  color: var(--fg2);
}

.pill--ok {
  color: var(--down);
  border-color: color-mix(in oklab, var(--down) 40%, transparent);
}

.pill--bad {
  color: var(--up);
  border-color: color-mix(in oklab, var(--up) 40%, transparent);
}

.pill--muted {
  color: var(--muted);
}

.muted {
  font-size: 12px;
  color: var(--muted);
}

.failure {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: color-mix(in oklab, var(--up) 12%, transparent);
  border: 1px solid color-mix(in oklab, var(--up) 32%, transparent);
}

.failure strong {
  color: var(--up);
  font-size: 13px;
}

.failure p {
  margin-top: 4px;
  font-size: 11px;
  color: var(--muted);
}

.failure code {
  font-family: var(--mono);
  user-select: all;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card__link {
  margin-top: 10px;
  font-size: 12px;
  color: var(--brand);
}

.card__link:hover {
  text-decoration: underline;
}
</style>
