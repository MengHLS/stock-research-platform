<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon'
import MarketBreadthPanel from '../components/market/MarketBreadthPanel.vue'
import MarketHighBoardTrend from '../components/market/MarketHighBoardTrend.vue'
import MarketIndexDetail from '../components/market/MarketIndexDetail.vue'
import MarketIndexPanel from '../components/market/MarketIndexPanel.vue'
import MarketLadderPanel from '../components/market/MarketLadderPanel.vue'
import MarketReviewControls from '../components/market/MarketReviewControls.vue'
import MarketSummaryPanel from '../components/market/MarketSummaryPanel.vue'
import MarketThemeHeatmap from '../components/market/MarketThemeHeatmap.vue'
import ReviewDrawer from '../components/market/ReviewDrawer.vue'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import { useReviewDetail } from '../market/useReviewDetail'
import type {
  LadderRow,
  ReviewContext,
  ReviewIndices,
  ReviewOverview,
  ReviewWindow,
} from '../market/review'
import {
  compareClass,
  formatSignedPercent,
  mergeLadderRows,
  parseReviewWindow,
  previousHistory,
  routeDate,
} from '../market/review'

type DrawerKind = 'index' | 'theme' | 'day' | 'stock'

const route = useRoute()
const router = useRouter()

const context = ref<ReviewContext | null>(null)
const overview = ref<ReviewOverview | null>(null)
const chartOverview = ref<ReviewOverview | null>(null)
const indices = ref<ReviewIndices | null>(null)
const contextFailure = ref<ApiFailure | null>(null)
const overviewFailure = ref<ApiFailure | null>(null)
const indicesFailure = ref<ApiFailure | null>(null)
const chartHistoryFailure = ref<ApiFailure | null>(null)
const loading = ref(false)
const loadingIndices = ref(false)
const localDateError = ref('')
const reloadKey = ref(0)

const drawerKind = ref<DrawerKind | null>(null)
const drawerDate = ref('')
const drawerTheme = ref('')
const drawerIndexSymbol = ref('')
const drawerStock = ref<LadderRow | null>(null)
const detail = useReviewDetail()
const { data: drawerOverview, loading: drawerLoading, failure: drawerFailure } = detail
const returnTo = ref<{ kind: 'theme' | 'day'; date: string; theme?: string } | null>(null)

let requestController: AbortController | null = null
let requestSequence = 0

const maximumWindow = computed(() => context.value?.window_max ?? 120)
const windowOptions = computed(() => {
  const options = [20, 40, 60, 120].filter((window) => window <= maximumWindow.value)
  if (!options.length) options.push(maximumWindow.value)
  return options
})
const selectedWindow = computed(() => parseReviewWindow(route.query.window, maximumWindow.value))
const chartHistoryWindow = computed(() =>
  Math.min(maximumWindow.value, Math.max(60, selectedWindow.value)),
)
const chartHistory = computed(() => chartOverview.value?.history ?? overview.value?.history ?? [])
const previous = computed(() =>
  overview.value ? previousHistory(overview.value.date, overview.value.history) : null,
)
const rawDateQuery = computed(() => route.query.date)
const explicitInvalidDate = computed(
  () =>
    rawDateQuery.value !== undefined &&
    (typeof rawDateQuery.value !== 'string' || !routeDate(rawDateQuery.value)),
)

const selectedIndexSeries = computed(
  () => indices.value?.indices.find((item) => item.symbol === drawerIndexSymbol.value) ?? null,
)

const indexCards = computed(() => {
  if (overview.value) return overview.value.indices
  if (!indices.value) return []
  return indices.value.indices.map((series) => {
    const current = series.bars.find((bar) => bar.date === indices.value?.date) ?? null
    return {
      symbol: series.symbol,
      name: series.name,
      coverage: series.coverage,
      close: current?.close ?? null,
      change_pct: current?.change_pct ?? null,
    }
  })
})

const drawerTitle = computed(() => {
  if (drawerKind.value === 'index') return selectedIndexSeries.value?.name ?? '指数详情'
  if (drawerKind.value === 'theme') return `${drawerTheme.value} · 涨停记录`
  if (drawerKind.value === 'day') return `${drawerDate.value} · 当日涨停`
  if (drawerKind.value === 'stock') return drawerStock.value?.name ?? '股票记录'
  return ''
})

const drawerMeta = computed(() => {
  if (drawerKind.value === 'index') return selectedIndexSeries.value?.symbol ?? ''
  if (drawerKind.value === 'theme') return `${drawerDate.value} · 仅包含当日涨停记录`
  if (drawerKind.value === 'day') return '当日涨停、未知板数与断板分组'
  if (drawerKind.value === 'stock') {
    return `${drawerStock.value?.symbol ?? ''} · ${drawerStock.value?.sector ?? ''}`
  }
  return ''
})

const drawerRows = computed(() => {
  if (!drawerOverview.value) return []
  const ladder = drawerOverview.value.ladder
  const currentRows = [...ladder.connection, ...ladder.first, ...ladder.unknown]
  if (drawerKind.value === 'theme') {
    return currentRows.filter((row) => row.sector === drawerTheme.value)
  }
  return mergeLadderRows(ladder)
})

function failureText(failure: ApiFailure): string {
  if (isAuthNotConfigured(failure)) return '服务端尚未配置认证，无法读取历史复盘数据。'
  if (failure.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
  return failure.message
}

function assessmentText(value: string | undefined): string {
  if (value === 'available') return '统计可评估'
  if (value === 'partial') return '部分'
  if (value === 'missing') return '缺失'
  return '—'
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

function chooseWindow(value: ReviewWindow) {
  updateQuery({ window: String(value) })
}

function goDate(date: string | null | undefined) {
  if (date) updateQuery({ date })
}

function resetToLatest() {
  if (context.value?.default_date) goDate(context.value.default_date)
  else {
    updateQuery({ date: undefined })
  }
}

function closeDrawer() {
  detail.clear()
  drawerKind.value = null
  drawerOverview.value = null
  drawerStock.value = null
  returnTo.value = null
  drawerFailure.value = null
  drawerLoading.value = false
}

function openIndex(symbol: string) {
  detail.clear()
  returnTo.value = null
  drawerIndexSymbol.value = symbol
  drawerKind.value = 'index'
  drawerDate.value = overview.value?.date ?? indices.value?.date ?? ''
}

async function openTheme(date: string, theme: string) {
  returnTo.value = null
  drawerKind.value = 'theme'
  drawerDate.value = date
  drawerTheme.value = theme
  drawerStock.value = null
  await detail.load(date, overview.value)
}

async function openDay(date: string) {
  returnTo.value = null
  drawerKind.value = 'day'
  drawerDate.value = date
  drawerTheme.value = ''
  drawerStock.value = null
  await detail.load(date, overview.value)
}

function openStock(row: LadderRow, date: string, back: 'theme' | 'day' | null = null) {
  returnTo.value = back
    ? { kind: back, date, theme: back === 'theme' ? drawerTheme.value : undefined }
    : null
  drawerStock.value = row
  drawerKind.value = 'stock'
  drawerDate.value = date
}

function backFromStock() {
  const target = returnTo.value
  if (!target) {
    closeDrawer()
    return
  }
  drawerKind.value = target.kind
  drawerDate.value = target.date
  drawerTheme.value = target.theme ?? ''
  drawerStock.value = null
}

async function loadRouteState() {
  requestController?.abort()
  const current = new AbortController()
  requestController = current
  const sequence = ++requestSequence
  closeDrawer()
  localDateError.value = ''
  contextFailure.value = null
  overviewFailure.value = null
  indicesFailure.value = null
  chartHistoryFailure.value = null
  overview.value = null
  chartOverview.value = null
  indices.value = null
  context.value = null
  loading.value = true
  loadingIndices.value = true

  if (explicitInvalidDate.value) {
    localDateError.value = '日期参数必须是有效的 YYYY-MM-DD。'
  }

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
    context.value = null
    overview.value = null
    indices.value = null
    loading.value = false
    loadingIndices.value = false
    return
  }
  context.value = contextResult.data
  if (explicitInvalidDate.value) {
    loading.value = false
    loadingIndices.value = false
    return
  }

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
    overview.value = null
    indices.value = null
    loading.value = false
    loadingIndices.value = false
    return
  }

  const effectiveDate = requested ?? contextResult.data.default_date
  if (!effectiveDate) {
    overview.value = null
    indices.value = null
    loading.value = false
    loadingIndices.value = false
    return
  }

  const extendedHistoryRequest =
    chartHistoryWindow.value > selectedWindow.value
      ? callApi(
          (signal) =>
            api.GET('/api/v1/market/review/overview', {
              params: { query: { date: effectiveDate, window: chartHistoryWindow.value } },
              signal,
            }),
          { access: 'read', signal: current.signal },
        ).then((result) => {
          if (requestController !== current || current.signal.aborted) return
          if (result.ok) chartOverview.value = result.data
          else if (result.failure.kind !== 'aborted') chartHistoryFailure.value = result.failure
        })
      : Promise.resolve()

  await Promise.all([
    callApi(
      (signal) =>
        api.GET('/api/v1/market/review/overview', {
          params: { query: { date: effectiveDate, window: selectedWindow.value } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    ).then((result) => {
      if (requestController !== current || current.signal.aborted) return
      loading.value = false
      if (result.ok) overview.value = result.data
      else if (result.failure.kind !== 'aborted') overviewFailure.value = result.failure
    }),
    callApi(
      (signal) =>
        api.GET('/api/v1/market/review/indices', {
          params: { query: { date: effectiveDate, window: Math.min(60, maximumWindow.value) } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    ).then((result) => {
      if (requestController !== current || current.signal.aborted) return
      loadingIndices.value = false
      if (result.ok) indices.value = result.data
      else if (result.failure.kind !== 'aborted') indicesFailure.value = result.failure
    }),
    extendedHistoryRequest,
  ])
}

watch(() => [route.query.date, route.query.window, reloadKey.value] as const, loadRouteState, {
  immediate: true,
})

onBeforeUnmount(() => {
  requestController?.abort()
  detail.clear()
})
</script>

<template>
  <div class="review-page">
    <section v-if="!overview && (context || localDateError)" class="fallback-controls panel">
      <MarketReviewControls
        :context="context"
        :value="context?.requested_date ?? context?.default_date ?? ''"
        :window-value="selectedWindow"
        :window-options="windowOptions"
        :loading="loading"
        @date="chooseDate"
        @window="chooseWindow"
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
      <p v-if="contextFailure.requestId">请求编号 {{ contextFailure.requestId }}</p>
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
      源内暂无可用的历史复盘日期。
    </section>

    <div v-if="loading && !overview" class="loading-panel panel" aria-live="polite">
      正在读取
      {{ context?.requested_date ?? routeDate(route.query.date) ?? '最近交易日' }} 的复盘数据…
    </div>

    <section v-if="overviewFailure" class="banner banner--error" role="alert">
      <strong>{{ failureText(overviewFailure) }}</strong>
      <p v-if="overviewFailure.requestId">请求编号 {{ overviewFailure.requestId }}</p>
      <button type="button" class="small-button" @click="reloadKey += 1">重新读取总览</button>
    </section>

    <MarketSummaryPanel v-if="overview" :overview="overview" :previous="previous">
      <template #controls>
        <MarketReviewControls
          :context="context"
          :value="overview.date"
          :window-value="selectedWindow"
          :window-options="windowOptions"
          :loading="loading"
          @date="chooseDate"
          @window="chooseWindow"
          @previous="goDate(context?.previous_trading_day)"
          @next="goDate(context?.next_trading_day)"
          @latest="resetToLatest"
          @reload="reloadKey += 1"
        />
      </template>
    </MarketSummaryPanel>
    <MarketIndexPanel
      v-if="indexCards.length || indicesFailure"
      :date="overview?.date ?? indices?.date ?? ''"
      :items="indexCards"
      :series="indices"
      :loading="loadingIndices"
      :failure="indicesFailure ? failureText(indicesFailure) : null"
      :request-id="indicesFailure?.requestId"
      @select="openIndex"
    />
    <section v-if="chartHistoryFailure && overview" class="banner banner--warn" role="status">
      <strong>更长周期图表暂按 {{ chartHistory.length }} 个交易日展示。</strong>
      <span>
        {{
          failureText(chartHistoryFailure)
        }}；市场量能结构、题材热力日历和每日最高连板使用顶部窗口数据。
      </span>
      <button type="button" class="small-button" @click="reloadKey += 1">重试长周期数据</button>
    </section>
    <template v-if="overview">
      <MarketBreadthPanel :history="chartHistory" />
      <MarketLadderPanel
        :ladder="overview.ladder"
        :date="overview.date"
        :total-limit-up="overview.summary.total_limit_up"
        :broken-count="overview.summary.broken_count"
        @select="openStock($event, overview.date)"
      />
      <MarketThemeHeatmap :history="chartHistory" @select="openTheme" />
      <MarketHighBoardTrend
        :history="chartHistory"
        :selected-date="overview.date"
        @open-day="openDay"
      />
    </template>

    <ReviewDrawer
      :open="drawerKind !== null"
      :title="drawerTitle"
      :meta="drawerMeta"
      :variant="
        drawerKind === 'index' || drawerKind === 'theme' || drawerKind === 'day'
          ? 'modal'
          : 'drawer'
      "
      :modal-size="drawerKind === 'index' ? 'chart' : 'default'"
      @close="closeDrawer"
    >
      <template v-if="drawerKind === 'index'">
        <div v-if="loadingIndices && !selectedIndexSeries" class="drawer-state">
          正在读取 {{ drawerDate }} 的指数历史…
        </div>
        <MarketIndexDetail
          v-else-if="selectedIndexSeries"
          :series="selectedIndexSeries"
          :date="drawerDate"
        />
        <div v-else class="drawer-state">
          {{ indicesFailure ? failureText(indicesFailure) : '该指数历史序列不可用。' }}
          <span v-if="indicesFailure?.requestId" class="request-id">
            请求编号 {{ indicesFailure.requestId }}
          </span>
        </div>
      </template>

      <template v-else-if="drawerKind === 'theme' || drawerKind === 'day'">
        <div v-if="drawerLoading" class="drawer-state">正在读取 {{ drawerDate }} 的记录…</div>
        <div v-else-if="drawerFailure" class="drawer-state drawer-state--error">
          {{ failureText(drawerFailure) }}
          <span v-if="drawerFailure.requestId" class="request-id">
            请求编号 {{ drawerFailure.requestId }}
          </span>
        </div>
        <template v-else>
          <div class="drawer-summary">
            <div>
              <span>涨停证券</span>
              <b>{{ drawerOverview?.summary.total_limit_up ?? '—' }}</b>
            </div>
            <div>
              <span>数据完整度</span>
              <b>{{ assessmentText(drawerOverview?.summary.assessment) }}</b>
            </div>
            <div>
              <span>昨日断板</span>
              <b>{{ drawerOverview?.summary.broken_count ?? '—' }}</b>
            </div>
          </div>
          <div v-if="drawerRows.length" class="stock-list">
            <button
              v-for="row in drawerRows"
              :key="`${row.symbol}-${row.broken_kind ?? ''}`"
              type="button"
              class="stock-row"
              @click="
                openStock(
                  row,
                  drawerDate,
                  drawerKind === 'theme' || drawerKind === 'day' ? drawerKind : null,
                )
              "
            >
              <span class="stock-ident">
                <strong>{{ row.name }}</strong>
                <code>{{ row.symbol }}</code>
              </span>
              <span>{{ row.sector }}</span>
              <span class="num">{{ row.boards === null ? '板数未知' : `${row.boards} 板` }}</span>
              <span v-if="row.broken_kind" class="broken">
                {{ row.broken_kind === 'connection' ? '连板中断' : '首板未续' }}
              </span>
              <AppIcon name="chevron-right" :size="14" />
            </button>
          </div>
          <div v-else class="drawer-state">
            {{
              drawerOverview?.summary.assessment === 'missing'
                ? '该日涨停记录缺失。'
                : '没有匹配记录。'
            }}
          </div>
        </template>
      </template>

      <template v-else-if="drawerKind === 'stock' && drawerStock">
        <button v-if="returnTo" type="button" class="back" @click="backFromStock">
          <AppIcon name="chevron-left" :size="14" />返回列表
        </button>
        <dl class="stock-kv">
          <div>
            <dt>题材</dt>
            <dd>{{ drawerStock.sector }}</dd>
          </div>
          <div>
            <dt>板数</dt>
            <dd>{{ drawerStock.boards ?? '未知' }}</dd>
          </div>
          <div>
            <dt>板数日期</dt>
            <dd>{{ drawerStock.boards_as_of_date }}</dd>
          </div>
          <div>
            <dt>封板时间</dt>
            <dd>{{ drawerStock.limit_up_time || '—' }}</dd>
          </div>
          <div>
            <dt>观察日涨跌</dt>
            <dd :class="compareClass(drawerStock.change_pct)">
              {{ formatSignedPercent(drawerStock.change_pct) }}
            </dd>
          </div>
          <div>
            <dt>一字板</dt>
            <dd>
              {{
                drawerStock.one_word_board === null
                  ? '未知'
                  : drawerStock.one_word_board
                    ? '是'
                    : '否'
              }}
            </dd>
          </div>
        </dl>
        <div v-if="drawerStock.boards === null" class="banner banner--warn">
          连板历史不足或前一日记录缺失，不能把该股当作首板。
        </div>
        <div v-if="drawerStock.broken_kind" class="banner banner--warn">
          {{ drawerStock.broken_kind === 'connection' ? '该股为连板中断。' : '该股为首板未续。' }}
          板数属于 {{ drawerStock.boards_as_of_date }}，不是观察日的在榜板数。
        </div>
      </template>
    </ReviewDrawer>
  </div>
</template>

<style scoped>
.review-page {
  --review-pad: 18px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-page :deep(.panel) {
  border-color: color-mix(in oklab, var(--border) 86%, var(--fg) 14%);
  box-shadow:
    0 1px 0 color-mix(in oklab, var(--fg) 3%, transparent),
    0 12px 30px color-mix(in oklab, var(--bg) 72%, transparent);
}

.review-page :deep(.panel-head) {
  min-height: 56px;
  padding: 14px var(--review-pad);
  background: color-mix(in oklab, var(--surface) 96%, var(--fg) 4%);
  border-bottom-color: color-mix(in oklab, var(--border) 82%, transparent);
}

.review-page :deep(.panel-head h2) {
  font-size: 15px;
  font-weight: 680;
  line-height: 1.25;
  letter-spacing: -0.012em;
}

.review-page :deep(.panel-head .sub) {
  font-size: 11.8px;
  line-height: 1.45;
}

.review-page :deep(.panel-body) {
  padding: var(--review-pad);
}

.review-page :deep(.chart-scroll) {
  overscroll-behavior-x: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}

.review-page :deep(button:focus-visible) {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

@media (max-width: 760px) {
  .review-page {
    --review-pad: 14px;
    gap: 14px;
  }

  .review-page :deep(.panel-head) {
    min-height: 0;
    padding-block: 12px;
  }

  .review-page :deep(.panel-head h2) {
    font-size: 14px;
  }

  .review-page :deep(.panel-head .sub) {
    flex-basis: 100%;
    order: 3;
  }
}

@media (min-width: 2200px) {
  .review-page {
    --review-pad: 22px;
  }
}

.panel {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.fallback-controls {
  padding: 9px 11px;
  display: flex;
  justify-content: flex-end;
}

.small-button {
  min-height: 30px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  cursor: pointer;
}

.small-button {
  padding: 4px 9px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
}

.small-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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

.banner p {
  margin: 0;
  color: var(--muted);
  font-size: 10px;
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

.loading-panel {
  min-height: 180px;
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

.drawer-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.drawer-summary div {
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  display: grid;
  gap: 2px;
}

.drawer-summary span {
  color: var(--muted);
  font-size: 10.5px;
}

.drawer-summary b {
  color: var(--fg);
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 650;
}

.stock-list {
  display: grid;
  gap: 6px;
}

.stock-row {
  display: grid;
  grid-template-columns: minmax(130px, 1.4fr) minmax(80px, 0.8fr) 72px auto 18px;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  text-align: left;
  cursor: pointer;
  font-size: 11px;
}

.stock-row:hover {
  border-color: var(--border2);
  background: var(--surface3);
}

.stock-ident {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.stock-ident strong,
.stock-ident code {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stock-ident code {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
}

.broken {
  color: var(--warn);
}

.back {
  margin-bottom: 12px;
  padding: 4px 7px;
  border: 0;
  background: transparent;
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  cursor: pointer;
}

.stock-kv {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0 0 12px;
}

.stock-kv div {
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.stock-kv dt {
  color: var(--muted);
  font-size: 10px;
}

.stock-kv dd {
  margin: 3px 0 0;
  color: var(--fg);
  font-size: 13px;
}

@media (max-width: 620px) {
  .fallback-controls {
    justify-content: flex-start;
  }

  .stock-row {
    grid-template-columns: minmax(120px, 1fr) 70px 18px;
  }

  .drawer-summary {
    grid-template-columns: 1fr;
  }

  .stock-row > :nth-child(2),
  .stock-row > :nth-child(4) {
    display: none;
  }

  .stock-kv {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
