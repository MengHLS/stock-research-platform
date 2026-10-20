<script setup lang="ts">
/**
 * Private pattern catalog (the prototype's "模式库").
 *
 * State handling is deliberate and is the point of this page: loading, empty,
 * failed and "not signed in" are four different things, and the table never
 * substitutes sample rows for a failure. Authentication is now real, so the
 * AUTH_NOT_CONFIGURED branch only appears when the server has no secret configured.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import AppIcon from '../components/AppIcon'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import type { components } from '../api/schema'

type Entry = components['schemas']['EntryRead']

const rows = ref<Entry[]>([])
const loading = ref(false)
const failure = ref<ApiFailure | null>(null)
/** True once a load succeeded; distinguishes "empty list" from "never loaded". */
const loaded = ref(false)
let controller: AbortController | null = null

const state = computed(() => {
  if (loading.value) return 'loading'
  if (failure.value) return isAuthNotConfigured(failure.value) ? 'auth' : 'failed'
  if (loaded.value && rows.value.length === 0) return 'empty'
  return 'ready'
})

/**
 * List reads use the `read` policy: 15s timeout, one retry on network/502-504.
 * Each load cancels the previous request so a stale response cannot overwrite a
 * newer one.
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
  if (result.failure.kind === 'aborted') return
  failure.value = result.failure
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

/** Empty-state text must match the real state; never call a failure "no records". */
const emptyText = computed(() => {
  switch (state.value) {
    case 'auth':
      return '登录服务尚未启用，暂时无法读取模式目录'
    case 'failed':
      return '加载失败，未展示替代数据'
    case 'empty':
      return '暂无记录'
    default:
      return '加载中'
  }
})

async function copyRequestId(requestId: string) {
  try {
    await navigator.clipboard.writeText(requestId)
  } catch {
    // Clipboard unavailable: the id is still visible on screen.
  }
}

onMounted(load)
onUnmounted(() => controller?.abort())
</script>

<template>
  <section class="panel">
    <div class="panel__head">
      <div>
        <span class="eyebrow">RESEARCH / CATALOG</span>
        <h2>模式库</h2>
      </div>
      <button type="button" class="btn" :disabled="loading" @click="load">
        <AppIcon name="refresh" :size="15" />
        {{ loading ? '加载中…' : '重新加载' }}
      </button>
    </div>

    <p class="lede">模式目录按账号隔离，只能看到本账号的记录。</p>

    <div v-if="state === 'auth'" class="banner banner--warn" role="status">
      登录服务尚未启用，暂时无法读取模式目录。
    </div>
    <div v-else-if="state === 'failed' && failure" class="banner banner--error" role="alert">
      <strong>{{ describeFailure(failure) }}</strong>
      <p v-if="failure.requestId">
        请求编号 <code>{{ failure.requestId }}</code>
        <button type="button" class="btn btn--tiny" @click="copyRequestId(failure.requestId)">
          复制
        </button>
      </p>
      <p v-else>本次失败没有收到 request_id。</p>
    </div>
    <div v-else-if="state === 'empty'" class="banner banner--info" role="status">
      当前账号还没有目录记录。
    </div>

    <table class="table">
      <thead>
        <tr>
          <th scope="col">模式名称</th>
          <th scope="col">描述</th>
          <th scope="col" class="table__num">版本</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id">
          <td>{{ row.name }}</td>
          <td class="table__desc">{{ row.description || '—' }}</td>
          <td class="table__num num">{{ row.row_version }}</td>
        </tr>
        <tr v-if="rows.length === 0">
          <td colspan="3" class="table__empty">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.panel {
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--muted);
}

h2 {
  margin: 8px 0 0;
  font-size: 20px;
  font-weight: 600;
}

.lede {
  margin: 10px 0 16px;
  font-size: 13px;
  line-height: 1.75;
  color: var(--fg2);
  max-width: 720px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  background: var(--surface2);
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  color: var(--fg2);
  font-size: 12px;
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  color: var(--fg);
  border-color: var(--border2);
  background: var(--surface3);
}

.btn:disabled {
  opacity: 0.6;
  cursor: progress;
}

.btn--tiny {
  padding: 1px 6px;
  font-size: 11px;
  margin-left: 6px;
}

.banner {
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.banner p {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--muted);
}

.banner code {
  font-family: var(--mono);
  user-select: all;
}

.banner--warn {
  background: color-mix(in oklab, var(--warn) 12%, transparent);
  border: 1px solid color-mix(in oklab, var(--warn) 32%, transparent);
  color: var(--warn);
}

.banner--error {
  background: color-mix(in oklab, var(--up) 12%, transparent);
  border: 1px solid color-mix(in oklab, var(--up) 32%, transparent);
}

.banner--error strong {
  color: var(--up);
}

.banner--info {
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--fg2);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.table th {
  text-align: left;
  font-weight: 500;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--muted);
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}

.table td {
  padding: 10px;
  border-bottom: 1px solid var(--grid);
  color: var(--fg2);
  vertical-align: top;
}

.table tbody tr:hover td {
  background: var(--surface2);
}

.table__num {
  text-align: right;
  width: 80px;
}

.table__desc {
  color: var(--muted);
}

.table__empty {
  text-align: center;
  color: var(--muted);
  padding: 24px 10px;
}
</style>
