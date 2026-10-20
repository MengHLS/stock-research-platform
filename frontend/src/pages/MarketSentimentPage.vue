<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon'
import MarketReviewControls from '../components/market/MarketReviewControls.vue'
import MarketSentimentLeaders from '../components/market/MarketSentimentLeaders.vue'
import MarketSentimentTimeline from '../components/market/MarketSentimentTimeline.vue'
import MarketSentimentTrendPanel from '../components/market/MarketSentimentTrendPanel.vue'
import ReviewDrawer from '../components/market/ReviewDrawer.vue'
import StockDetailContent from '../components/market/StockDetailContent.vue'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import type {
  LadderRow,
  LimitUpReviewRow,
  ReviewContext,
  ReviewLimitUp,
  ReviewOverview,
} from '../market/review'
import { routeDate } from '../market/review'
import { SENTIMENT_WINDOWS, parseSentimentWindow } from '../market/sentiment'

const route = useRoute()
const router = useRouter()

const context = ref<ReviewContext | null>(null)
const overview = ref<ReviewOverview | null>(null)
const contextFailure = ref<ApiFailure | null>(null)
const overviewFailure = ref<ApiFailure | null>(null)
const localDateError = ref('')
const loading = ref(false)
const reloadKey = ref(0)
const drawerOpen = ref(false)
const drawerLoading = ref(false)
const drawerFailure = ref<ApiFailure | null>(null)
const drawerMessage = ref('')
const selectedLeader = ref<LadderRow | null>(null)
const selectedRow = ref<LimitUpReviewRow | null>(null)
const peerRows = ref<LimitUpReviewRow[]>([])
const drawer = ref<InstanceType<typeof ReviewDrawer> | null>(null)
const notes = reactive<Record<string, string>>({})

let requestController: AbortController | null = null
let drawerController: AbortController | null = null
let requestSequence = 0
let drawerSequence = 0

const rawDateQuery = computed(() => route.query.date)
const explicitInvalidDate = computed(
  () =>
    rawDateQuery.value !== undefined &&
    (typeof rawDateQuery.value !== 'string' || !routeDate(rawDateQuery.value)),
)
const maximumWindow = computed(() => context.value?.window_max ?? 120)
const windowOptions = computed(() => {
  const values: number[] = SENTIMENT_WINDOWS.filter((item) => item <= maximumWindow.value)
  if (!values.length) values.push(maximumWindow.value)
  if (!values.includes(maximumWindow.value)) values.push(maximumWindow.value)
  return Array.from(new Set(values)).sort((left, right) => left - right)
})
const selectedWindow = computed(() => parseSentimentWindow(route.query.window, maximumWindow.value))
const selectedDate = computed(
  () =>
    routeDate(rawDateQuery.value) ??
    context.value?.requested_date ??
    context.value?.default_date ??
    '',
)
const history = computed(() => overview.value?.history ?? [])
const showInitialLoading = computed(
  () => loading.value && !overview.value && !contextFailure.value && !localDateError.value,
)
const drawerTitle = computed(() => selectedLeader.value?.name ?? '股票记录')
const drawerMeta = computed(() => {
  const row = selectedLeader.value
  return row ? `${row.symbol} · ${row.sector} · ${overview.value?.date ?? selectedDate.value}` : ''
})
const noteKey = computed(() =>
  selectedRow.value
    ? `${selectedRow.value.date}|${selectedRow.value.symbol}|${selectedRow.value.status}`
    : '',
)

function failureText(failure: ApiFailure): string {
  if (isAuthNotConfigured(failure)) return '登录服务尚未启用，无法读取历史复盘数据。'
  if (failure.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
  return failure.message
}

function updateQuery(patch: Record<string, string | undefined>) {
  const query = { ...route.query, ...patch }
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === '') delete query[key]
  }
  void router.push({ path: route.path, query })
}

function chooseDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return
  updateQuery({ date: value, window: String(selectedWindow.value) })
}

function chooseWindow(value: number) {
  updateQuery({ window: String(value) })
}

function goDate(value: string | null | undefined) {
  if (value) updateQuery({ date: value })
}

function resetToLatest() {
  updateQuery({ date: undefined, window: String(selectedWindow.value) })
}

function closeDrawer() {
  drawerController?.abort()
  drawerSequence += 1
  drawerOpen.value = false
  drawerLoading.value = false
  drawerFailure.value = null
  drawerMessage.value = ''
  selectedLeader.value = null
  selectedRow.value = null
  peerRows.value = []
}

async function openLeader(row: LadderRow) {
  drawerController?.abort()
  const current = new AbortController()
  drawerController = current
  const sequence = ++drawerSequence
  selectedLeader.value = row
  selectedRow.value = null
  peerRows.value = []
  drawerFailure.value = null
  drawerMessage.value = ''
  drawerLoading.value = true
  drawerOpen.value = true
  await nextTick()
  drawer.value?.focusPanel()

  const date = overview.value?.date ?? selectedDate.value
  const result = await callApi(
    (signal) =>
      api.GET('/api/v1/market/review/limit-up', {
        params: { query: { date, window: 1 } },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (drawerController !== current || sequence !== drawerSequence) return
  drawerLoading.value = false
  if (!result.ok) {
    if (result.failure.kind !== 'aborted') drawerFailure.value = result.failure
    return
  }
  const payload: ReviewLimitUp = result.data
  peerRows.value = payload.rows
  selectedRow.value =
    payload.rows.find(
      (item) => item.date === date && item.symbol === row.symbol && item.status === 'limit_up',
    ) ??
    payload.rows.find((item) => item.date === date && item.symbol === row.symbol) ??
    null
  if (!selectedRow.value) {
    drawerMessage.value = `${date} 的涨停明细中没有找到 ${row.symbol} ${row.name}。`
  }
}

async function selectStockFromDetail(row: LimitUpReviewRow) {
  selectedRow.value = row
  await nextTick()
  drawer.value?.focusPanel()
}

function saveNote(value: string) {
  if (noteKey.value) notes[noteKey.value] = value
}

async function loadRouteState() {
  requestController?.abort()
  closeDrawer()
  const current = new AbortController()
  requestController = current
  const sequence = ++requestSequence
  context.value = null
  overview.value = null
  contextFailure.value = null
  overviewFailure.value = null
  localDateError.value = ''

  if (explicitInvalidDate.value) {
    localDateError.value = '日期参数必须是有效的 YYYY-MM-DD。'
    loading.value = false
    return
  }

  loading.value = true
  const requested = routeDate(rawDateQuery.value)
  const contextResult = await callApi(
    (signal) =>
      api.GET('/api/v1/market/review/context', {
        params: { query: requested ? { date: requested } : {} },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (requestController !== current || sequence !== requestSequence) return
  if (!contextResult.ok) {
    if (contextResult.failure.kind !== 'aborted') contextFailure.value = contextResult.failure
    loading.value = false
    return
  }

  context.value = contextResult.data
  if (!requested && contextResult.data.default_date) {
    await router.replace({
      path: route.path,
      query: {
        ...route.query,
        date: contextResult.data.default_date,
        window: String(selectedWindow.value),
      },
    })
    return
  }
  if (requested && contextResult.data.requested_date_known !== true) {
    loading.value = false
    return
  }

  const effectiveDate = requested ?? contextResult.data.default_date
  if (!effectiveDate) {
    loading.value = false
    return
  }
  const overviewResult = await callApi(
    (signal) =>
      api.GET('/api/v1/market/review/overview', {
        params: { query: { date: effectiveDate, window: selectedWindow.value } },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (requestController !== current || sequence !== requestSequence) return
  loading.value = false
  if (overviewResult.ok) overview.value = overviewResult.data
  else if (overviewResult.failure.kind !== 'aborted') overviewFailure.value = overviewResult.failure
}

watch(() => [route.query.date, route.query.window, reloadKey.value] as const, loadRouteState, {
  immediate: true,
})

onBeforeUnmount(() => {
  requestController?.abort()
  drawerController?.abort()
  drawerSequence += 1
})
</script>

<template>
  <div class="sentiment-page">
    <section v-if="!overview && (context || localDateError)" class="fallback-controls panel">
      <MarketReviewControls
        :context="context"
        :value="context?.requested_date ?? context?.default_date ?? ''"
        :window-value="selectedWindow"
        :window-options="windowOptions"
        :loading="loading"
        :show-window="false"
        @date="chooseDate"
        @previous="goDate(context?.previous_trading_day)"
        @next="goDate(context?.next_trading_day)"
        @latest="resetToLatest"
        @reload="reloadKey += 1"
      />
    </section>

    <section v-if="localDateError" class="banner banner--warn" role="alert">
      {{ localDateError }}
      <button type="button" class="small-button" @click="resetToLatest">查看最近有记录日</button>
    </section>
    <section v-else-if="contextFailure" class="banner banner--error" role="alert">
      <strong>{{ failureText(contextFailure) }}</strong>
      <span v-if="contextFailure.requestId">请求编号 {{ contextFailure.requestId }}</span>
      <button type="button" class="small-button" @click="reloadKey += 1">重试</button>
    </section>
    <section
      v-else-if="context && context.requested_date_known === false"
      class="banner banner--warn"
      role="alert"
    >
      {{ context.requested_date }} 未被交易日数据收录；页面没有自动替换成其他日期。
      <button v-if="context.default_date" type="button" class="small-button" @click="resetToLatest">
        查看 {{ context.default_date }}
      </button>
    </section>
    <section v-else-if="context && !context.default_date" class="banner banner--info">
      暂无可用的历史复盘日期。
    </section>

    <div v-if="showInitialLoading" class="loading-panel panel" aria-live="polite">
      正在读取 {{ selectedDate || '最近交易日' }} 的情绪周期数据…
    </div>

    <section v-if="overviewFailure" class="banner banner--error" role="alert">
      <strong>{{ failureText(overviewFailure) }}</strong>
      <span v-if="overviewFailure.requestId">请求编号 {{ overviewFailure.requestId }}</span>
      <button type="button" class="small-button" @click="reloadKey += 1">重新读取情绪周期</button>
    </section>

    <template v-if="overview">
      <MarketSentimentTrendPanel
        :history="history"
        :selected-date="overview.date"
        :window-value="selectedWindow"
        :window-options="windowOptions"
        :window-requested="overview.window_requested"
        :window-actual="overview.window_actual"
        @window="chooseWindow"
        @select="chooseDate"
      >
        <template #controls>
          <MarketReviewControls
            :context="context"
            :value="overview.date"
            :window-value="selectedWindow"
            :window-options="windowOptions"
            :loading="loading"
            :show-window="false"
            @date="chooseDate"
            @previous="goDate(context?.previous_trading_day)"
            @next="goDate(context?.next_trading_day)"
            @latest="resetToLatest"
            @reload="reloadKey += 1"
          />
        </template>
      </MarketSentimentTrendPanel>

      <MarketSentimentTimeline
        :history="history"
        :selected-date="overview.date"
        @select="chooseDate"
      />

      <MarketSentimentLeaders
        :ladder="overview.ladder"
        :date="overview.date"
        @select="openLeader"
      />

      <details v-if="overview.issues.length" class="issues">
        <summary>
          <AppIcon name="alert-triangle" :size="14" />
          {{ overview.issues.length }} 条数据口径与缺失提示
        </summary>
        <ul>
          <li v-for="issue in overview.issues" :key="`${issue.code}-${issue.scope}`">
            <span v-if="/^\d{4}-\d{2}-\d{2}$/.test(issue.scope ?? '')">
              涉及日期 {{ issue.scope }} ·
            </span>
            {{ issue.message }}
          </li>
        </ul>
      </details>
    </template>

    <ReviewDrawer
      ref="drawer"
      :open="drawerOpen"
      :title="drawerTitle"
      :meta="drawerMeta"
      variant="modal"
      modal-size="detail"
      @close="closeDrawer"
    >
      <div v-if="drawerLoading" class="drawer-state">
        正在读取 {{ overview?.date ?? selectedDate }} 的股票记录…
      </div>
      <div v-else-if="drawerFailure" class="drawer-state drawer-state--error" role="alert">
        <span>{{ failureText(drawerFailure) }}</span>
        <span v-if="drawerFailure.requestId" class="request-id">
          请求编号 {{ drawerFailure.requestId }}
        </span>
        <button
          v-if="selectedLeader"
          type="button"
          class="small-button"
          @click="openLeader(selectedLeader)"
        >
          重试股票明细
        </button>
      </div>
      <div v-else-if="drawerMessage" class="drawer-state">{{ drawerMessage }}</div>
      <StockDetailContent
        v-else-if="selectedRow"
        :row="selectedRow"
        :peer-rows="peerRows"
        :window-max="maximumWindow"
        :note="notes[noteKey] ?? ''"
        @select="selectStockFromDetail"
        @save-note="saveNote"
      />
    </ReviewDrawer>
  </div>
</template>

<style scoped>
.sentiment-page {
  --review-pad: 18px;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sentiment-page :deep(.panel) {
  border-color: color-mix(in oklab, var(--border) 86%, var(--fg) 14%);
  box-shadow:
    0 1px 0 color-mix(in oklab, var(--fg) 3%, transparent),
    0 12px 30px color-mix(in oklab, var(--bg) 72%, transparent);
}

.sentiment-page :deep(.panel-head) {
  min-height: 56px;
  padding: 14px var(--review-pad);
  background: color-mix(in oklab, var(--surface) 96%, var(--fg) 4%);
}

.sentiment-page :deep(.panel-head h2) {
  font-size: 15px;
  font-weight: 680;
  line-height: 1.25;
  letter-spacing: -0.012em;
}

.sentiment-page :deep(.panel-body) {
  padding: var(--review-pad);
}

.sentiment-page :deep(.controls) {
  flex: 0 1 auto;
}

.sentiment-page :deep(.chart-scroll) {
  overscroll-behavior-x: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}

.fallback-controls {
  padding: 9px 11px;
  display: flex;
  justify-content: flex-end;
}

.banner {
  padding: 11px 13px;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  font-size: 12px;
}

.banner span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10.5px;
}

.banner--warn {
  border: 1px solid color-mix(in oklab, var(--warn) 36%, var(--border));
  background: color-mix(in oklab, var(--warn) 10%, transparent);
  color: var(--warn);
}

.banner--error {
  border: 1px solid color-mix(in oklab, var(--up) 36%, var(--border));
  background: color-mix(in oklab, var(--up) 10%, transparent);
  color: var(--up);
}

.banner--info {
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--fg2);
}

.small-button {
  min-height: 30px;
  padding: 4px 9px;
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  background: transparent;
  color: inherit;
  font-size: 11px;
  cursor: pointer;
}

.loading-panel {
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 12px;
}

.drawer-state {
  padding: 26px 12px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}

.drawer-state--error {
  color: var(--up);
}

.request-id {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
  user-select: all;
}

.drawer-state .small-button {
  display: block;
  margin: 10px auto 0;
  color: var(--fg2);
}

.issues {
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--muted);
  font-size: 12px;
}

.issues summary {
  width: fit-content;
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}

.issues ul {
  margin: 8px 0 0;
  padding-left: 20px;
  display: grid;
  gap: 5px;
}

.issues li {
  color: var(--fg2);
  line-height: 1.55;
}

@media (max-width: 760px) {
  .sentiment-page {
    --review-pad: 14px;
    gap: 14px;
  }

  .sentiment-page :deep(.panel-head) {
    min-height: 0;
    padding-block: 12px;
  }

  .sentiment-page :deep(.panel-head h2) {
    font-size: 14px;
  }
}

@media (min-width: 2200px) {
  .sentiment-page {
    --review-pad: 22px;
  }
}
</style>
