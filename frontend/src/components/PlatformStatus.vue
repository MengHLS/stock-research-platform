<script setup lang="ts">
/**
 * The real system state, as a compact "console" panel.
 *
 * This replaces the prototype's fake terminal preview (which showed invented
 * quote numbers on the login screen). Every value here comes from a request that
 * actually ran:
 *
 * - `GET /health/live` → the API process is alive, and its version;
 * - `GET /api/v1/market/session` → the exchange phase by the server's clock;
 * - `GET /api/v1/market/sources` → which upstreams are *configured*.
 *
 * The wording is deliberately weaker than the data might suggest:
 * `/health/live` does not touch the database, and `/market/sources` does not
 * contact any provider — so neither is described as "healthy" or "reachable".
 * Saying "已配置" instead of "可用" is the difference between a fact and a guess.
 *
 * A failure is displayed as a failure, with its request id. Nothing here falls
 * back to a plausible-looking number.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import AppIcon from './AppIcon'
import { api, callApi } from '../api/client'
import type { ApiFailure } from '../api/errors'

interface SourceRow {
  name: string
  configured: boolean
}

const version = ref('—')
const apiState = ref<'checking' | 'ok' | 'unavailable' | 'failed'>('checking')
const apiFailure = ref<ApiFailure | null>(null)

const sources = ref<SourceRow[]>([])
const sourcesState = ref<'checking' | 'ok' | 'failed'>('checking')
const sourcesFailure = ref<ApiFailure | null>(null)

/**
 * `/market/sources` reports `upstream_enabled` separately from per-source
 * `configured`. When upstream access is switched off the three public sources
 * still report `configured: true` but every market call fails with
 * `MARKET_SOURCE_DISABLED`, so rendering "3/4 configured" unqualified would read
 * as healthy. This flag is what stops that.
 */
const upstreamEnabled = ref<boolean | null>(null)

/** Exchange phase from the server's clock; null until the first answer. */
const phase = ref<string | null>(null)
const phaseState = ref<'checking' | 'ok' | 'failed'>('checking')
const phaseFailure = ref<ApiFailure | null>(null)

let controller: AbortController | null = null

const sourceLabels: Record<string, string> = {
  tencent: '腾讯',
  eastmoney: '东方财富',
  sina: '新浪',
  tushare: 'Tushare',
}

/** Only the labels the API documents; an unknown value is shown verbatim. */
const phaseLabels: Record<string, string> = {
  opening_auction: '集合竞价',
  pre_open: '竞价已结束',
  continuous: '连续交易',
  lunch_break: '午间休市',
  closed: '休市',
}

async function probe() {
  controller?.abort()
  const current = new AbortController()
  controller = current

  apiState.value = 'checking'
  apiFailure.value = null
  sourcesState.value = 'checking'
  sourcesFailure.value = null
  phaseState.value = 'checking'
  phaseFailure.value = null

  const [health, sourceList, session] = await Promise.all([
    callApi((signal) => api.GET('/health/live', { signal }), {
      access: 'diagnostic',
      signal: current.signal,
    }),
    callApi((signal) => api.GET('/api/v1/market/sources', { signal }), {
      access: 'diagnostic',
      signal: current.signal,
    }),
    callApi((signal) => api.GET('/api/v1/market/session', { signal }), {
      access: 'diagnostic',
      signal: current.signal,
    }),
  ])
  if (controller !== current) return

  if (health.ok) {
    apiState.value = health.data.status === 'ok' ? 'ok' : 'unavailable'
    version.value = health.data.version
  } else if (health.failure.kind !== 'aborted') {
    apiState.value = 'failed'
    apiFailure.value = health.failure
    version.value = '—'
  }

  // The phase is a convenience label, but its failure must still be visible: a
  // dash alone is indistinguishable from "still loading", which is the exact
  // silent-degradation the rest of this panel avoids.
  if (session.ok) {
    phase.value = session.data.phase
    phaseState.value = 'ok'
  } else if (session.failure.kind !== 'aborted') {
    phase.value = null
    phaseState.value = 'failed'
    phaseFailure.value = session.failure
  }

  if (sourceList.ok) {
    sources.value = sourceList.data.items.map((item) => ({
      name: item.name,
      configured: item.configured,
    }))
    upstreamEnabled.value = sourceList.data.upstream_enabled
    sourcesState.value = 'ok'
  } else if (sourceList.failure.kind !== 'aborted') {
    sources.value = []
    upstreamEnabled.value = null
    sourcesState.value = 'failed'
    sourcesFailure.value = sourceList.failure
  }
}

/**
 * `/health/live` answers exactly one question: the process is serving. It does
 * not check the database (`/health/ready` does), so the label says "运行中".
 */
const apiLabel = computed(() => {
  switch (apiState.value) {
    case 'ok':
      return '运行中'
    case 'unavailable':
      return '未就绪'
    case 'failed':
      return '未连接'
    default:
      return '检查中'
  }
})

/**
 * Status colours use the accent, never `--up`/`--down`: those carry the A-share
 * red-up / green-down meaning everywhere else in the app, so green would read as
 * a falling price and red as a rising one. Failure uses `--warn`.
 */
const apiTone = computed(() =>
  apiState.value === 'ok' ? 'ok' : apiState.value === 'checking' ? 'muted' : 'bad',
)

const configuredCount = computed(() => sources.value.filter((row) => row.configured).length)

onMounted(probe)
onUnmounted(() => controller?.abort())
</script>

<template>
  <section class="status" aria-label="系统实时状态">
    <header class="status__bar">
      <span class="status__dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <span class="status__title">本机服务状态</span>
      <span class="status__live" :class="`status__live--${apiTone}`">
        <span class="status__bulb" aria-hidden="true"></span>
        {{ apiLabel }}
      </span>
    </header>

    <div class="status__body">
      <dl class="status__grid">
        <div class="status__cell">
          <dt>版本</dt>
          <dd class="num">{{ version }}</dd>
        </div>
        <div class="status__cell">
          <dt>时段</dt>
          <dd v-if="phaseState === 'ok'">{{ phase ? (phaseLabels[phase] ?? phase) : '—' }}</dd>
          <dd v-else-if="phaseState === 'failed'" class="status__cell--bad">读取失败</dd>
          <dd v-else class="status__cell--dim">…</dd>
        </div>
        <div class="status__cell">
          <dt>已配置源</dt>
          <dd class="num">
            <template v-if="sourcesState === 'ok' && upstreamEnabled === false"> 已关闭 </template>
            <template v-else-if="sourcesState === 'ok'">
              {{ configuredCount }}<span class="status__unit">/{{ sources.length }}</span>
            </template>
            <template v-else-if="sourcesState === 'failed'">—</template>
            <template v-else>…</template>
          </dd>
        </div>
      </dl>

      <p v-if="upstreamEnabled === false" class="status__note status__note--warn" role="status">
        <AppIcon name="alert-triangle" :size="12" />
        <span> 外部行情已关闭：下方的"已配置"只表示配置存在，行情调用会失败。 </span>
      </p>

      <ul v-if="sourcesState === 'ok'" class="status__sources">
        <li v-for="row in sources" :key="row.name" :class="{ 'is-off': !row.configured }">
          <span class="status__pip" aria-hidden="true"></span>
          <span class="status__name">{{ sourceLabels[row.name] ?? row.name }}</span>
          <span class="status__state">{{ row.configured ? '已配置' : '未配置' }}</span>
        </li>
      </ul>

      <p v-else-if="sourcesState === 'failed'" class="status__note">
        数据源配置读取失败（{{ sourcesFailure?.message ?? '未知原因' }}）
        <span v-if="sourcesFailure?.requestId" class="mono">· {{ sourcesFailure.requestId }}</span>
      </p>
      <p v-else class="status__note">正在读取数据源配置…</p>

      <p v-if="phaseState === 'failed'" class="status__note status__note--bad">
        <AppIcon name="alert-triangle" :size="12" />
        <span>
          交易时段读取失败（{{ phaseFailure?.message ?? '未知原因' }}）
          <span v-if="phaseFailure?.requestId" class="mono">· {{ phaseFailure.requestId }}</span>
        </span>
      </p>

      <p v-if="apiState === 'failed'" class="status__note status__note--bad">
        <AppIcon name="alert-triangle" :size="12" />
        <span>
          {{ apiFailure?.message ?? '无法连接后台服务' }}
          <span v-if="apiFailure?.requestId" class="mono">· {{ apiFailure.requestId }}</span>
        </span>
      </p>
    </div>

    <footer class="status__foot">
      <span>状态来自本服务实际响应</span>
      <span class="status__sep" aria-hidden="true"></span>
      <button type="button" class="status__retry" @click="probe">
        <AppIcon name="refresh" :size="11" />
        刷新
      </button>
    </footer>
  </section>
</template>

<style scoped>
.status {
  max-width: 520px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.status__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--surface2);
}

.status__dots {
  display: flex;
  gap: 5px;
}

.status__dots i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border2);
  display: block;
}

.status__title {
  font-size: 10.5px;
  color: var(--fg2);
}

.status__live {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--fg2);
}

.status__bulb {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

.status__live--ok {
  color: var(--accent);
}

/* Failure uses --warn, not --up: --up means "price rose" in this product, and
   reusing it for errors is the same semantic collision as using green for OK.
   --warn also clears 4.5:1 on --surface2 where --up does not. */
.status__live--bad {
  color: var(--warn);
}

.status__body {
  padding: 14px;
  display: grid;
  gap: 12px;
}

.status__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.status__cell {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 9px;
  display: grid;
  gap: 1px;
  min-width: 0;
}

.status__cell dt {
  font-size: 10px;
  color: var(--fg2);
}

.status__cell dd {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status__cell--bad {
  color: var(--warn);
  font-size: 12px;
}

.status__cell--dim {
  color: var(--fg2);
}

.status__unit {
  font-size: 10px;
  font-weight: 500;
  color: var(--fg2);
}

.num {
  font-variant-numeric: tabular-nums;
}

.mono {
  font-family: var(--mono);
}

.status__sources {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}

.status__sources li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  font-size: 11.5px;
}

/* Unconfigured is information, not a disabled control: dim only the marker and
   keep the label at full contrast. `--muted` would sit at 4.29:1 on --surface2,
   so the text uses --fg2; the pip carries the dimming instead. */
.status__sources li.is-off .status__name,
.status__sources li.is-off .status__state {
  color: var(--fg2);
}

.status__pip {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  flex: none;
}

.status__sources li.is-off .status__pip {
  background: var(--fg2);
}

.status__name {
  font-weight: 600;
}

.status__state {
  margin-left: auto;
  font-size: 10px;
  color: var(--fg2);
}

.status__note {
  margin: 0;
  display: flex;
  align-items: flex-start;
  gap: 5px;
  font-size: 10.5px;
  line-height: 1.6;
  color: var(--fg2);
}

.status__note svg {
  flex: none;
  margin-top: 2px;
}

.status__note--bad {
  color: var(--warn);
}

.status__note--warn {
  color: var(--warn);
  align-items: flex-start;
}

.status__foot {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  background: var(--surface2);
  font-size: 9.5px;
  color: var(--fg2);
}

.status__sep {
  flex: 1;
}

.status__retry {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 24px;
  padding: 2px 8px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--fg2);
  font-size: 10px;
  cursor: pointer;
}

.status__retry:hover {
  color: var(--fg);
  border-color: var(--border2);
}

@media (max-width: 560px) {
  .status {
    max-width: none;
  }
}
</style>
