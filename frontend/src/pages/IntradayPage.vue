<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon'
import IntradayChart from '../components/market/IntradayChart.vue'
import MarketSparkline from '../components/market/MarketSparkline.vue'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import {
  INTRADAY_WATCH_LIMIT,
  canonicalWatchCodes,
  exchangeLabel,
  formatAmount,
  formatShares,
  formatShanghaiDate,
  formatShanghaiTime,
  intradaySummary,
  latestTradingDayBars,
  marketPhaseLabel,
  mergeWatchlist,
  normalizeTicker,
  parseTickerInput,
  phaseTone,
  readStoredWatchlist,
  watchlistStorageKey,
  type IntradayBar,
  type IntradayQuote,
  type MarketSession,
  type OpeningAuction,
} from '../market/intraday'
import { chartNumber, compareClass, formatNumber, formatSignedPercent } from '../market/review'
import { useSession } from '../stores/session'

interface WatchQuoteState {
  quote: IntradayQuote | null
  failure: ApiFailure | null
  loading: boolean
}

interface AddFeedback {
  added: string[]
  duplicates: string[]
  invalid: string[]
  overflow: string[]
}

interface Reading {
  key: string
  label: string
  value: string
  note: string
  tone?: string
}

const route = useRoute()
const router = useRouter()
const session = useSession()

const watchCodes = ref<string[]>([])
const watchRecords = ref<Record<string, WatchQuoteState>>({})
const storageLoaded = ref(false)
const tickerInput = ref('')
const addFeedback = ref<AddFeedback | null>(null)

const marketSession = ref<MarketSession | null>(null)
const sessionFailure = ref<ApiFailure | null>(null)

const quote = ref<IntradayQuote | null>(null)
const bars = ref<IntradayBar[]>([])
const intradayLimits = ref<string[]>([])
const intradayTotal = ref(0)
const auction = ref<OpeningAuction | null>(null)

const quoteLoading = ref(false)
const intradayLoading = ref(false)
const auctionLoading = ref(false)
const quoteFailure = ref<ApiFailure | null>(null)
const intradayFailure = ref<ApiFailure | null>(null)
const auctionFailure = ref<ApiFailure | null>(null)

let watchController: AbortController | null = null
let detailController: AbortController | null = null
let sessionController: AbortController | null = null
let detailSequence = 0
const quoteRequestVersions = new Map<string, number>()
const quoteRequestCounts = new Map<string, number>()

const storageKey = computed(() => watchlistStorageKey(session.user?.id))
const routeCode = computed(() => normalizeTicker(route.query.code))
const selectedCode = computed(() => routeCode.value ?? watchCodes.value[0] ?? '')
const selectedWatchState = computed(() =>
  selectedCode.value ? watchRecords.value[selectedCode.value] : undefined,
)
const activePhase = computed(() =>
  sessionFailure.value
    ? (quote.value?.phase ?? null)
    : (marketSession.value?.phase ?? quote.value?.phase ?? null),
)
const activePhaseLabel = computed(() => marketPhaseLabel(activePhase.value))
const activePhaseTone = computed(() => phaseTone(activePhase.value))

const watchRows = computed(() =>
  watchCodes.value
    .map((code, order) => {
      const record = watchRecords.value[code]
      const itemQuote = record?.quote ?? null
      const loading = record?.loading ?? false
      const failed = Boolean(record?.failure)
      const quoteStamp = itemQuote
        ? `${formatShanghaiDate(itemQuote.quote_time).slice(5)} ${formatShanghaiTime(
            itemQuote.quote_time,
          ).slice(0, 5)}`
        : ''
      return {
        code,
        order,
        quote: itemQuote,
        loading,
        failed,
        name: itemQuote?.name ?? `标的 ${code}`,
        symbol: itemQuote?.symbol ?? code,
        changePct: chartNumber(itemQuote?.change_pct),
        statusText: loading
          ? quoteStamp
            ? `读取中 · ${quoteStamp}`
            : '读取中'
          : failed
            ? quoteStamp
              ? `失败 · 保留 ${quoteStamp}`
              : '读取失败'
            : itemQuote
              ? `${itemQuote.symbol} · ${quoteStamp}`
              : '待读取',
      }
    })
    .sort((left, right) => {
      if (left.changePct === null && right.changePct === null) return left.order - right.order
      if (left.changePct === null) return 1
      if (right.changePct === null) return -1
      return right.changePct - left.changePct || left.order - right.order
    }),
)

const summary = computed(() => (quote.value ? intradaySummary(quote.value, bars.value) : null))
const auctionSeries = computed(() =>
  (auction.value?.snapshots ?? []).map((snapshot) => chartNumber(snapshot.price)),
)
const auctionProviderLabel = computed(() => {
  if (!auction.value) return '来源未知'
  if (auction.value.provider === 'eastmoney') return '东方财富'
  if (auction.value.provider === 'sina') return '新浪'
  return '腾讯'
})
const latestBar = computed(() => bars.value.at(-1) ?? null)

const readings = computed<Reading[]>(() => {
  const item = quote.value
  if (!item) return []
  return [
    {
      key: 'price',
      label: '最新价',
      value: formatNumber(item.price, 2),
      note: '真实快照',
      tone: compareClass(item.change_pct),
    },
    {
      key: 'change',
      label: '涨跌幅',
      value: formatSignedPercent(item.change_pct),
      note: '相对昨收',
      tone: compareClass(item.change_pct),
    },
    {
      key: 'amount',
      label: '成交额',
      value: formatAmount(item.amount),
      note: '供应商原始成交金额',
    },
    {
      key: 'turnover',
      label: '换手率',
      value: formatSignedPercent(item.turnover_pct).replace('+', ''),
      note: '缺失时不按 0 处理',
    },
    {
      key: 'quote-volume',
      label: '快照成交量',
      value: `${formatNumber(item.volume_lots, 0)} 手`,
      note: '指数与品种口径可能不同',
    },
    {
      key: 'bar-volume',
      label: '分钟累计量',
      value: formatShares(summary.value?.intradayVolumeShares),
      note: `${summary.value?.barCount ?? 0} 根 1 分钟线`,
    },
    {
      key: 'position',
      label: '日内位置',
      value:
        summary.value?.positionPct === null || summary.value?.positionPct === undefined
          ? '—'
          : `${summary.value.positionPct.toFixed(1)}%`,
      note: '现价在当日高低区间中的位置',
    },
    {
      key: 'gap',
      label: '开盘缺口',
      value: formatSignedPercent(summary.value?.openGapPct),
      note: '开盘相对昨收',
      tone: compareClass(summary.value?.openGapPct),
    },
    {
      key: 'drawdown',
      label: '距今日高点',
      value: formatSignedPercent(summary.value?.drawdownFromHighPct),
      note: '现价相对当日最高',
      tone: compareClass(summary.value?.drawdownFromHighPct),
    },
    {
      key: 'bar-day',
      label: '分钟线交易日',
      value: summary.value?.barTradingDay ?? '—',
      note: lastBarLabel.value,
    },
  ]
})

const lastBarLabel = computed(() =>
  latestBar.value ? `最近 ${formatShanghaiTime(latestBar.value.start)}` : '暂无分钟线',
)

watch(
  storageKey,
  (key) => {
    let raw: string | null
    try {
      raw = localStorage.getItem(key)
    } catch {
      raw = null
    }
    const stored = canonicalWatchCodes(readStoredWatchlist(raw)).codes
    const directCode = normalizeTicker(route.query.code)
    const preferred = preferredStoredCode(route.query.code, stored)
    watchCodes.value =
      directCode && !stored.includes(directCode) && stored.length < INTRADAY_WATCH_LIMIT
        ? [directCode, ...stored]
        : stored
    if (preferred && preferred !== directCode && stored.includes(preferred)) {
      updateCodeQuery(preferred)
    }
    storageLoaded.value = true
    if (watchCodes.value.length) void loadWatchQuotes(watchCodes.value)
  },
  { immediate: true },
)

watch(
  watchCodes,
  (codes) => {
    if (!storageLoaded.value) return
    try {
      localStorage.setItem(storageKey.value, JSON.stringify(codes))
    } catch {
      // A blocked browser storage must not break live quote reading.
    }
  },
  { deep: true },
)

watch(routeCode, (code) => {
  if (code && !watchCodes.value.includes(code) && watchCodes.value.length < INTRADAY_WATCH_LIMIT) {
    watchCodes.value = [code, ...watchCodes.value]
  }
})

watch(
  selectedCode,
  () => {
    void loadSelected()
  },
  { immediate: true },
)

function failureText(value: ApiFailure): string {
  if (isAuthNotConfigured(value)) return '服务端尚未配置认证，无法读取行情。'
  if (value.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
  return value.message
}

function updateCodeQuery(code: string | null) {
  const query = { ...route.query }
  if (code) query.code = code
  else delete query.code
  void router.replace({ path: route.path, query })
}

function selectCode(code: string) {
  if (routeCode.value === code) return
  updateCodeQuery(code)
}

function preferredStoredCode(raw: unknown, stored: string[]): string | null {
  const requested = normalizeTicker(raw)
  if (!requested) return null
  const exact = stored.find((code) => normalizeTicker(code) === requested)
  return exact ?? requested
}

function addTickers() {
  const parsed = parseTickerInput(tickerInput.value)
  const known = new Set(watchCodes.value)
  for (const code of watchCodes.value) {
    const quoteSymbol = watchRecords.value[code]?.quote?.symbol
    if (!quoteSymbol) continue
    known.add(quoteSymbol)
    const bare = quoteSymbol.split('.')[0]
    if (bare) known.add(bare)
  }
  const alreadySaved = parsed.valid.filter((code) => known.has(code))
  const additions = parsed.valid.filter((code) => !known.has(code))
  const merged = mergeWatchlist(watchCodes.value, additions)
  if (merged.added.length) {
    watchCodes.value = [
      ...merged.added,
      ...watchCodes.value.filter((code) => !merged.added.includes(code)),
    ].slice(0, INTRADAY_WATCH_LIMIT)
    selectCode(merged.added[0] ?? merged.codes[0] ?? '')
  }
  addFeedback.value = {
    added: merged.added,
    duplicates: [...new Set([...parsed.duplicates, ...alreadySaved, ...merged.duplicates])],
    invalid: parsed.invalid,
    overflow: merged.overflow,
  }
  tickerInput.value = [...parsed.invalid, ...merged.overflow].join(' ')

  if (merged.added.length) void loadWatchQuotes(watchCodes.value)
}

function removeCode(code: string) {
  const rows = watchRows.value
  const index = rows.findIndex((row) => row.code === code)
  const remaining = watchCodes.value.filter((item) => item !== code)
  watchCodes.value = remaining
  const nextRecords = { ...watchRecords.value }
  delete nextRecords[code]
  watchRecords.value = nextRecords
  addFeedback.value = null

  if (selectedCode.value === code) {
    const neighbor = rows[index + 1]?.code ?? rows[index - 1]?.code ?? remaining[0] ?? null
    updateCodeQuery(neighbor)
  }
}

function retrySelected() {
  void loadSelected()
}

function refreshAll() {
  void loadMarketSession()
  void loadSelected()
  void loadWatchQuotes(watchCodes.value)
}

function requestWatchRows() {
  const pending = watchRows.value.filter((row) => !row.quote && !row.loading && !row.failed)
  if (!pending.length) return
  void loadWatchQuotes(pending.map((row) => row.code))
}

function setWatchQuote(code: string, patch: Partial<WatchQuoteState>) {
  watchRecords.value = {
    ...watchRecords.value,
    [code]: {
      quote: watchRecords.value[code]?.quote ?? null,
      failure: watchRecords.value[code]?.failure ?? null,
      loading: watchRecords.value[code]?.loading ?? false,
      ...patch,
    },
  }
}

function beginQuoteRequest(code: string): number {
  quoteRequestCounts.set(code, (quoteRequestCounts.get(code) ?? 0) + 1)
  const version = (quoteRequestVersions.get(code) ?? 0) + 1
  quoteRequestVersions.set(code, version)
  return version
}

function commitWatchQuote(code: string, version: number, patch: Partial<WatchQuoteState>) {
  settleQuoteRequest(code)
  if (quoteRequestVersions.get(code) !== version) return
  if (patch.quote) patch = { ...patch, failure: null }
  setWatchQuote(code, patch)
}

function settleQuoteRequest(code: string) {
  if (!quoteRequestCounts.has(code)) return
  const remaining = Math.max(0, (quoteRequestCounts.get(code) ?? 1) - 1)
  if (remaining) {
    quoteRequestCounts.set(code, remaining)
    return
  }
  quoteRequestCounts.delete(code)
  if (watchRecords.value[code]?.loading) setWatchQuote(code, { loading: false })
}

function abandonQuoteRequest(code: string) {
  if (quoteRequestCounts.has(code)) settleQuoteRequest(code)
}

async function loadWatchQuotes(codes = watchCodes.value) {
  watchController?.abort()
  const current = new AbortController()
  watchController = current
  const unique = [...new Set(codes)]
  for (const code of unique) {
    setWatchQuote(code, { loading: true, failure: null })
  }

  let cursor = 0
  const workers = Array.from({ length: Math.min(4, unique.length) }, async () => {
    while (cursor < unique.length) {
      const code = unique[cursor]
      cursor += 1
      if (!code) continue
      const quoteVersion = beginQuoteRequest(code)
      const result = await callApi(
        (signal) =>
          api.GET('/api/v1/market/quote', {
            params: { query: { symbol: code } },
            signal,
          }),
        { access: 'read', signal: current.signal },
      )
      if (watchController !== current || current.signal.aborted) {
        abandonQuoteRequest(code)
        return
      }
      if (result.ok) {
        commitWatchQuote(code, quoteVersion, {
          quote: result.data,
          failure: null,
          loading: false,
        })
      } else if (result.failure.kind !== 'aborted') {
        commitWatchQuote(code, quoteVersion, { failure: result.failure, loading: false })
      }
    }
  })
  await Promise.all(workers)
}

async function loadMarketSession() {
  sessionController?.abort()
  const current = new AbortController()
  sessionController = current
  sessionFailure.value = null
  marketSession.value = null
  const result = await callApi((signal) => api.GET('/api/v1/market/session', { signal }), {
    access: 'read',
    signal: current.signal,
  })
  if (sessionController !== current || current.signal.aborted) return
  if (result.ok) marketSession.value = result.data
  else if (result.failure.kind !== 'aborted') sessionFailure.value = result.failure
}

async function loadSelected() {
  detailController?.abort()
  const current = new AbortController()
  detailController = current
  const sequence = ++detailSequence
  const code = selectedCode.value

  quote.value = null
  bars.value = []
  auction.value = null
  quoteFailure.value = null
  intradayFailure.value = null
  auctionFailure.value = null
  intradayLimits.value = []
  intradayTotal.value = 0
  quoteLoading.value = Boolean(code)
  intradayLoading.value = Boolean(code)
  auctionLoading.value = Boolean(code)

  if (!code) return
  const quoteVersion = beginQuoteRequest(code)

  const [quoteResult, intradayResult, auctionResult] = await Promise.all([
    callApi(
      (signal) =>
        api.GET('/api/v1/market/quote', {
          params: { query: { symbol: code } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    ),
    callApi(
      (signal) =>
        api.GET('/api/v1/market/intraday', {
          params: { query: { symbol: code, period: 'm1', limit: 240 } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    ),
    callApi(
      (signal) =>
        api.GET('/api/v1/market/auction', {
          params: { query: { symbol: code } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    ),
  ])
  if (detailController !== current || current.signal.aborted || sequence !== detailSequence) {
    if (current.signal.aborted) abandonQuoteRequest(code)
    else settleQuoteRequest(code)
    return
  }

  quoteLoading.value = false
  intradayLoading.value = false
  auctionLoading.value = false

  if (quoteResult.ok) {
    quote.value = quoteResult.data
    commitWatchQuote(code, quoteVersion, {
      quote: quoteResult.data,
      failure: null,
      loading: false,
    })
  } else if (quoteResult.failure.kind !== 'aborted') {
    quoteFailure.value = quoteResult.failure
    commitWatchQuote(code, quoteVersion, {
      failure: quoteResult.failure,
      loading: false,
    })
  }

  if (intradayResult.ok) {
    bars.value = latestTradingDayBars(intradayResult.data.bars)
    intradayLimits.value = intradayResult.data.limits ?? []
    intradayTotal.value = intradayResult.data.total
  } else if (intradayResult.failure.kind !== 'aborted') {
    intradayFailure.value = intradayResult.failure
  }

  if (auctionResult.ok) auction.value = auctionResult.data
  else if (auctionResult.failure.kind !== 'aborted') auctionFailure.value = auctionResult.failure
}

onMounted(() => {
  void loadMarketSession()
  requestWatchRows()
})

onBeforeUnmount(() => {
  watchController?.abort()
  detailController?.abort()
  sessionController?.abort()
  detailSequence += 1
})
</script>

<template>
  <div class="intraday-page">
    <section class="add-panel panel">
      <div class="add-copy">
        <span class="eyebrow">LIVE CHECKPOINT</span>
        <h2>加入自选，读取盘中事实</h2>
        <p>自选保存在本机浏览器。</p>
      </div>
      <div class="add-control">
        <div class="add-label">
          <label for="intradayTicker">股票代码</label>
          <span>{{ watchCodes.length }}/{{ INTRADAY_WATCH_LIMIT }}</span>
        </div>
        <div class="add-row">
          <input
            id="intradayTicker"
            v-model="tickerInput"
            inputmode="numeric"
            autocomplete="off"
            placeholder="如 600519 000001，空格分隔"
            @keydown.enter.prevent="addTickers"
          />
          <button type="button" class="primary-button" @click="addTickers">
            <AppIcon name="search" :size="15" />
            加入并研判
          </button>
        </div>
        <p class="add-help">
          支持 5–6 位代码，或带交易所的 000001.SZ / sh600519；重复不会重复加入，满 50
          只后不会静默接收。
        </p>
      </div>
      <div v-if="addFeedback" class="add-feedback" role="status">
        <span>
          <b>新增 {{ addFeedback.added.length }}</b>
        </span>
        <span>重复 {{ addFeedback.duplicates.length }}</span>
        <span>非法 {{ addFeedback.invalid.length }}</span>
        <span>超限 {{ addFeedback.overflow.length }}</span>
        <p v-if="addFeedback.invalid.length">未识别：{{ addFeedback.invalid.join('、') }}</p>
        <p v-if="addFeedback.overflow.length">超过上限：{{ addFeedback.overflow.join('、') }}</p>
      </div>
    </section>

    <div class="workbench">
      <aside class="watch-side panel" aria-label="盘中自选">
        <header class="watch-head">
          <div>
            <b>自选</b>
            <span>{{ watchCodes.length }}/{{ INTRADAY_WATCH_LIMIT }}</span>
          </div>
          <div class="watch-actions">
            <span>涨幅降序</span>
            <button type="button" :disabled="!watchCodes.length" @click="loadWatchQuotes()">
              <AppIcon name="refresh" :size="13" />
              刷新
            </button>
          </div>
        </header>

        <div v-if="watchRows.length" class="watch-list" role="list">
          <div
            v-for="row in watchRows"
            :key="row.code"
            class="watch-row"
            :class="{ active: row.code === selectedCode }"
            role="listitem"
          >
            <button
              type="button"
              class="watch-pick"
              :aria-current="row.code === selectedCode ? 'true' : undefined"
              @click="selectCode(row.code)"
            >
              <span class="watch-name">
                <b>{{ row.name }}</b>
                <em>{{ row.code }}</em>
              </span>
              <span class="watch-price num">
                {{ formatNumber(row.quote?.price, 2) }}
              </span>
              <span class="watch-change num" :class="compareClass(row.changePct)">
                {{ formatSignedPercent(row.changePct) }}
              </span>
              <span class="watch-status">
                <i v-if="row.loading" class="status-dot loading" />
                <i v-else-if="row.failed" class="status-dot failed" />
                <i v-else-if="!row.quote" class="status-dot idle" />
                <i v-else class="status-dot ready" />
                {{ row.statusText }}
              </span>
            </button>
            <button
              type="button"
              class="watch-remove"
              :aria-label="`移出自选：${row.name} ${row.code}`"
              title="移出自选"
              @click="removeCode(row.code)"
            >
              <AppIcon name="x" :size="14" />
            </button>
          </div>
        </div>
        <div v-else class="watch-empty">
          <AppIcon name="search" :size="27" />
          <b>自选为空</b>
          <span>加入股票后查看行情、竞价与分时。</span>
        </div>

        <footer class="watch-foot">
          <span>自选仅保存在本机。</span>
          <span v-if="selectedWatchState?.failure">
            {{ failureText(selectedWatchState.failure) }}
          </span>
        </footer>
      </aside>

      <div class="detail-column">
        <div v-if="!selectedCode" class="empty-detail panel">
          <AppIcon name="target" :size="34" />
          <h2>等待第一只自选</h2>
          <p>输入股票代码，开始查看盘中行情。</p>
        </div>

        <template v-else>
          <section v-if="quoteFailure" class="banner banner--error" role="alert">
            <strong>{{ failureText(quoteFailure) }}</strong>
            <span v-if="quoteFailure.requestId">请求编号 {{ quoteFailure.requestId }}</span>
            <button type="button" @click="retrySelected">重新读取标的</button>
          </section>

          <section v-else-if="sessionFailure" class="banner banner--warn" role="status">
            <strong>交易时段读取失败，现显示报价内携带的时段。</strong>
            <span>{{ failureText(sessionFailure) }}</span>
          </section>

          <section v-if="quoteLoading && !quote" class="hero-loading panel" aria-live="polite">
            <span />
            <strong />
            <i />
          </section>

          <section v-else-if="quote" class="hero panel">
            <div class="hero-top">
              <div class="identity">
                <div class="identity-mark">{{ quote.symbol.slice(0, 2) }}</div>
                <div>
                  <h2>{{ quote.name }}</h2>
                  <p>
                    <code>{{ quote.symbol }}</code>
                    <span>{{ exchangeLabel(quote.symbol) }}</span>
                    <span>腾讯快照</span>
                  </p>
                </div>
              </div>
              <div class="quote-block">
                <b class="num" :class="compareClass(quote.change_pct)">
                  {{ formatNumber(quote.price, 2) }}
                </b>
                <span class="num" :class="compareClass(quote.change_pct)">
                  {{ formatSignedPercent(quote.change_pct) }}
                </span>
              </div>
              <button
                type="button"
                class="refresh-button"
                :disabled="quoteLoading"
                @click="refreshAll"
              >
                <AppIcon name="refresh" :size="14" />
                {{ quoteLoading ? '刷新中' : '刷新全部' }}
              </button>
            </div>

            <div class="context-strip">
              <div>
                <span>报价日期</span>
                <b>{{ formatShanghaiDate(quote.quote_time) }}</b>
              </div>
              <div>
                <span>报价时间</span>
                <b>{{ formatShanghaiTime(quote.quote_time) }}</b>
              </div>
              <div>
                <span>交易时段</span>
                <b class="phase" :class="activePhaseTone">{{ activePhaseLabel }}</b>
              </div>
              <div>
                <span>分钟线交易日</span>
                <b>{{ summary?.barTradingDay ?? '—' }}</b>
              </div>
              <p>
                <AppIcon name="info" :size="13" />
                北京时间 · 手动刷新
              </p>
            </div>
          </section>

          <div class="main-layout">
            <section class="panel chart-panel">
              <header class="panel-head">
                <div>
                  <h2>当日分时 · 价格与成交量</h2>
                  <p>{{ selectedCode }} · 1 分钟线 · {{ formatShanghaiTime(latestBar?.start) }}</p>
                </div>
                <span class="panel-tag">
                  同日 {{ bars.length }} / 返回 {{ intradayTotal || bars.length }} 根
                </span>
              </header>
              <div class="panel-body">
                <div
                  class="chart-layout"
                  :class="{ 'chart-layout--with-readings': readings.length }"
                >
                  <div class="chart-main">
                    <div v-if="intradayLoading" class="panel-state">正在读取一分钟行情…</div>
                    <div
                      v-else-if="intradayFailure"
                      class="panel-state panel-state--error"
                      role="alert"
                    >
                      <b>{{ failureText(intradayFailure) }}</b>
                      <span v-if="intradayFailure.requestId">
                        请求编号 {{ intradayFailure.requestId }}
                      </span>
                      <button type="button" @click="retrySelected">重试分钟线</button>
                    </div>
                    <div v-else-if="!bars.length" class="panel-state">暂无分钟线数据。</div>
                    <div v-else class="chart-scroll">
                      <IntradayChart :bars="bars" :previous-close="quote?.previous_close" />
                    </div>
                    <ul v-if="intradayLimits.length" class="limit-list">
                      <li v-for="limit in intradayLimits" :key="limit">{{ limit }}</li>
                    </ul>
                  </div>
                  <aside
                    v-if="readings.length"
                    class="chart-readings"
                    role="group"
                    aria-label="盘中读数"
                  >
                    <div v-for="reading in readings" :key="reading.key" class="reading">
                      <span>{{ reading.label }}</span>
                      <b class="num" :class="reading.tone">{{ reading.value }}</b>
                      <small>{{ reading.note }}</small>
                    </div>
                  </aside>
                </div>
              </div>
            </section>

            <div class="side-stack">
              <section class="panel auction-panel">
                <header class="panel-head">
                  <div>
                    <h2>开盘集合竞价</h2>
                    <p>{{ auctionProviderLabel }} · 09:15–09:25 曲线与撮合结果</p>
                  </div>
                  <span v-if="auction?.degraded" class="panel-tag warn">降级</span>
                </header>
                <div class="panel-body">
                  <div v-if="auctionLoading" class="panel-state">正在读取竞价…</div>
                  <div
                    v-else-if="auctionFailure"
                    class="panel-state panel-state--error"
                    role="alert"
                  >
                    <b>{{ failureText(auctionFailure) }}</b>
                    <span v-if="auctionFailure.requestId">
                      请求编号 {{ auctionFailure.requestId }}
                    </span>
                    <button type="button" @click="retrySelected">重试竞价</button>
                  </div>
                  <template v-else-if="auction">
                    <div class="auction-stats">
                      <div>
                        <span>撮合价</span>
                        <b class="num">{{ formatNumber(auction.matched_price, 2) }}</b>
                      </div>
                      <div>
                        <span>撮合时间</span>
                        <b class="num">{{ formatShanghaiTime(auction.matched_time) }}</b>
                      </div>
                      <div>
                        <span>成交股数</span>
                        <b class="num">{{ formatShares(auction.matched_volume_shares) }}</b>
                      </div>
                      <div>
                        <span>成交额</span>
                        <b class="num">{{ formatAmount(auction.matched_amount) }}</b>
                      </div>
                    </div>
                    <MarketSparkline
                      v-if="auctionSeries.some((value) => value !== null)"
                      class="auction-spark"
                      :values="auctionSeries"
                      :height="56"
                      color="var(--accent)"
                      label="开盘集合竞价虚拟撮合价格曲线"
                    />
                    <p v-if="auction.degraded" class="degraded-note">
                      当前只有撮合结果，虚拟撮合曲线不可用；空曲线不代表没有竞价。
                    </p>
                    <p v-else-if="!auction.snapshots.length" class="degraded-note">
                      源内没有返回虚拟撮合快照。
                    </p>
                    <p v-else class="auction-note">
                      {{ auction.snapshots.length }} 个虚拟撮合快照 · 返回时点
                      {{ formatShanghaiTime(auction.snapshots.at(-1)?.time) }}
                    </p>
                    <ul v-if="auction.limits?.length" class="limit-list">
                      <li v-for="limit in auction.limits" :key="limit">{{ limit }}</li>
                    </ul>
                  </template>
                  <div v-else class="panel-state">竞价结果不可用。</div>
                </div>
              </section>

              <section class="panel pending-panel">
                <header class="panel-head">
                  <div>
                    <h2>研判模块</h2>
                    <p>以下功能待开放</p>
                  </div>
                  <span class="panel-tag">待接入</span>
                </header>
                <div class="pending-list">
                  <div>
                    <AppIcon name="sliders" :size="15" />
                    <span><b>七维评分</b><small>待开放</small></span>
                    <em>未接入</em>
                  </div>
                  <div>
                    <AppIcon name="shield" :size="15" />
                    <span><b>避雷规则</b><small>待开放</small></span>
                    <em>未接入</em>
                  </div>
                  <div>
                    <AppIcon name="file-text" :size="15" />
                    <span><b>个人战绩</b><small>待开放</small></span>
                    <em>未接入</em>
                  </div>
                  <div>
                    <AppIcon name="target" :size="15" />
                    <span><b>参考计划</b><small>不生成买点、止损、目标价或仓位建议</small></span>
                    <em>未接入</em>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.intraday-page {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.add-panel {
  padding: 17px 18px;
  display: grid;
  grid-template-columns: minmax(240px, 0.8fr) minmax(360px, 1.2fr);
  gap: 12px 24px;
  align-items: center;
  background:
    radial-gradient(
      circle at 4% 0,
      color-mix(in oklab, var(--brand) 12%, transparent),
      transparent 36%
    ),
    var(--surface);
}

.eyebrow {
  color: var(--brand);
  font-family: var(--mono);
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.add-copy h2 {
  margin: 3px 0 3px;
  font-size: 18px;
  letter-spacing: -0.025em;
}

.add-copy p,
.add-help {
  margin: 0;
  color: var(--muted);
  font-size: 10.5px;
  line-height: 1.55;
}

.add-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 5px;
  color: var(--fg2);
  font-size: 10.5px;
}

.add-label span {
  color: var(--muted);
  font-family: var(--mono);
}

.add-row {
  display: flex;
  gap: 7px;
}

.add-row input {
  min-width: 0;
  flex: 1;
  height: 36px;
  padding: 0 11px;
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg);
  font: inherit;
  font-size: 12px;
}

.add-row input::placeholder {
  color: var(--muted);
}

.primary-button,
.refresh-button {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  cursor: pointer;
}

.primary-button {
  min-height: 36px;
  padding: 0 12px;
  border-color: color-mix(in oklab, var(--brand) 54%, var(--border));
  background: color-mix(in oklab, var(--brand) 15%, var(--surface2));
  color: var(--fg);
  font-size: 11.5px;
  font-weight: 650;
}

.add-help {
  margin-top: 5px;
}

.add-feedback {
  grid-column: 1 / -1;
  padding-top: 9px;
  border-top: 1px dashed var(--border);
  display: flex;
  align-items: center;
  gap: 8px 16px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 10.5px;
}

.add-feedback b {
  color: var(--down);
}

.add-feedback p {
  flex-basis: 100%;
  margin: 0;
  color: var(--warn);
}

.workbench {
  display: grid;
  grid-template-columns: 286px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.watch-side {
  position: sticky;
  top: calc(var(--topbar-h) + 14px);
  max-height: calc(100vh - var(--topbar-h) - 34px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.watch-head {
  flex: none;
  padding: 10px 11px;
  border-bottom: 1px solid var(--border);
  background: var(--surface2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.watch-head > div:first-child {
  display: flex;
  align-items: baseline;
  gap: 7px;
}

.watch-head b {
  font-size: 12px;
}

.watch-head span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9.5px;
}

.watch-actions {
  display: flex;
  align-items: center;
  gap: 7px;
}

.watch-actions button {
  height: 25px;
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--surface);
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 9.5px;
  cursor: pointer;
}

.watch-actions button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.watch-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.watch-row {
  position: relative;
  border-bottom: 1px solid var(--border);
}

.watch-row.active {
  background: color-mix(in oklab, var(--brand) 9%, var(--surface));
}

.watch-row.active::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--brand);
}

.watch-pick {
  width: 100%;
  min-height: 67px;
  padding: 8px 30px 8px 11px;
  border: 0;
  background: transparent;
  color: var(--fg);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 8px;
  text-align: left;
  cursor: pointer;
}

.watch-pick:hover {
  background: var(--surface2);
}

.watch-name {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.watch-name b {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.watch-name em,
.watch-status {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
  font-style: normal;
}

.watch-price {
  justify-self: end;
  font-size: 12px;
  font-weight: 650;
}

.watch-change {
  justify-self: end;
  font-size: 10.5px;
  font-weight: 650;
}

.watch-status {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 5px;
}

.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--muted);
}

.status-dot.ready {
  background: var(--down);
}

.status-dot.failed {
  background: var(--up);
}

.status-dot.idle {
  background: var(--border2);
}

.status-dot.loading {
  background: var(--warn);
  animation: pulse-dot 850ms ease-in-out infinite alternate;
}

.watch-remove {
  position: absolute;
  top: 6px;
  right: 5px;
  width: 21px;
  height: 21px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted);
  display: grid;
  place-items: center;
  opacity: 0;
  cursor: pointer;
}

.watch-row:hover .watch-remove,
.watch-row:focus-within .watch-remove {
  opacity: 1;
}

.watch-remove:hover {
  background: color-mix(in oklab, var(--up) 12%, var(--surface2));
  color: var(--up);
}

.watch-empty {
  min-height: 250px;
  padding: 26px 20px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 7px;
  color: var(--muted);
  text-align: center;
}

.watch-empty b {
  color: var(--fg2);
  font-size: 12.5px;
}

.watch-empty span {
  font-size: 10.5px;
  line-height: 1.55;
}

.watch-foot {
  flex: none;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  background: var(--surface2);
  color: var(--muted);
  display: grid;
  gap: 4px;
  font-size: 9px;
  line-height: 1.45;
}

.detail-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-detail {
  min-height: 420px;
  padding: 30px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 8px;
  color: var(--muted);
  text-align: center;
}

.empty-detail h2 {
  margin: 0;
  color: var(--fg2);
  font-size: 16px;
}

.empty-detail p {
  max-width: 390px;
  margin: 0;
  font-size: 11px;
  line-height: 1.65;
}

.banner {
  padding: 11px 13px;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  font-size: 11.5px;
}

.banner--error {
  border: 1px solid color-mix(in oklab, var(--up) 36%, var(--border));
  background: color-mix(in oklab, var(--up) 9%, transparent);
  color: var(--up);
}

.banner--warn {
  border: 1px solid color-mix(in oklab, var(--warn) 34%, var(--border));
  background: color-mix(in oklab, var(--warn) 8%, transparent);
  color: var(--warn);
}

.banner span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9.5px;
}

.banner button,
.panel-state button {
  min-height: 27px;
  padding: 2px 8px;
  border: 1px solid currentColor;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  font-size: 10px;
  cursor: pointer;
}

.banner button {
  margin-left: auto;
}

.hero-loading {
  min-height: 180px;
  padding: 22px;
  display: grid;
  align-content: center;
  gap: 12px;
}

.hero-loading span,
.hero-loading strong,
.hero-loading i {
  display: block;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--surface2), var(--surface3), var(--surface2));
  background-size: 200% 100%;
  animation: shimmer 1.2s linear infinite;
}

.hero-loading span {
  width: 28%;
  height: 12px;
}

.hero-loading strong {
  width: 42%;
  height: 38px;
}

.hero-loading i {
  width: 100%;
  height: 52px;
}

.hero {
  position: relative;
  overflow: hidden;
  padding: 17px 18px 15px;
  background:
    radial-gradient(
      circle at 88% 0,
      color-mix(in oklab, var(--accent) 9%, transparent),
      transparent 32%
    ),
    linear-gradient(135deg, color-mix(in oklab, var(--brand) 5%, var(--surface)), var(--surface));
}

.hero-top {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}

.identity {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 11px;
}

.identity-mark {
  width: 42px;
  height: 42px;
  flex: none;
  border: 1px solid color-mix(in oklab, var(--brand) 36%, var(--border));
  border-radius: 10px;
  background: color-mix(in oklab, var(--brand) 11%, var(--surface2));
  color: var(--brand);
  display: grid;
  place-items: center;
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 750;
  letter-spacing: 0.04em;
}

.identity h2 {
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
  letter-spacing: -0.025em;
}

.identity p {
  margin: 4px 0 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 9.5px;
}

.identity code {
  color: var(--fg2);
  font-family: var(--mono);
}

.identity p span {
  padding-left: 8px;
  border-left: 1px solid var(--border2);
}

.quote-block {
  margin-left: auto;
  display: flex;
  align-items: baseline;
  gap: 9px;
}

.quote-block b {
  font-size: clamp(28px, 2.6vw, 36px);
  line-height: 1;
  letter-spacing: -0.035em;
}

.quote-block span {
  font-size: 13px;
  font-weight: 650;
}

.refresh-button {
  min-height: 32px;
  padding: 0 9px;
  background: var(--surface2);
  color: var(--fg2);
  font-size: 10.5px;
}

.refresh-button:disabled {
  opacity: 0.45;
  cursor: wait;
}

.context-strip {
  margin-top: 13px;
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: color-mix(in oklab, var(--surface2) 84%, transparent);
  display: flex;
  align-items: stretch;
  gap: 8px 18px;
  flex-wrap: wrap;
}

.context-strip > div {
  display: grid;
  gap: 1px;
}

.context-strip span {
  color: var(--muted);
  font-size: 9px;
}

.context-strip b {
  color: var(--fg2);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.context-strip .phase.live {
  color: var(--down);
}

.context-strip .phase.warn {
  color: var(--warn);
}

.context-strip .phase.muted {
  color: var(--muted);
}

.context-strip p {
  flex: 1 1 100%;
  margin: 0;
  padding-top: 7px;
  border-top: 1px dashed var(--border);
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  font-size: 9.5px;
}

.main-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(310px, 0.8fr);
  gap: 16px;
  align-items: start;
}

.side-stack {
  min-width: 0;
  display: grid;
  gap: 16px;
}

.panel-head {
  min-height: 52px;
  padding: 11px 13px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.panel-head h2 {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.25;
}

.panel-head p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 9.5px;
  line-height: 1.4;
}

.panel-tag {
  flex: none;
  padding: 2px 6px;
  border: 1px solid var(--border2);
  border-radius: 999px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 8.5px;
}

.panel-tag.warn {
  border-color: color-mix(in oklab, var(--warn) 40%, var(--border));
  color: var(--warn);
}

.panel-body {
  padding: 12px 13px 13px;
}

.chart-panel .panel-body {
  padding-bottom: 10px;
}

.chart-panel {
  container-type: inline-size;
}

.chart-layout {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 13px;
  align-items: start;
}

.chart-layout--with-readings {
  grid-template-columns: minmax(0, 1fr) minmax(210px, 238px);
}

.chart-main {
  min-width: 0;
}

.chart-scroll {
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

.panel-state {
  min-height: 128px;
  padding: 18px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 6px;
  color: var(--muted);
  text-align: center;
  font-size: 10.5px;
}

.panel-state--error {
  color: var(--up);
}

.panel-state span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
}

.limit-list {
  margin: 8px 0 0;
  padding: 0 0 0 15px;
  color: var(--muted);
  font-size: 9px;
  line-height: 1.55;
}

.chart-readings {
  min-width: 0;
  padding-left: 13px;
  border-left: 1px solid var(--border);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  align-content: start;
}

.reading {
  min-width: 0;
  padding: 8px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  display: grid;
  gap: 1px;
}

.reading span,
.reading small {
  color: var(--muted);
  font-size: 8.5px;
}

.reading b {
  color: var(--fg);
  font-size: 12px;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.auction-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.auction-stats div {
  padding: 8px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  display: grid;
  gap: 1px;
}

.auction-stats span {
  color: var(--muted);
  font-size: 8.5px;
}

.auction-stats b {
  color: var(--fg);
  font-size: 11.5px;
}

.auction-spark {
  margin-top: 9px;
}

.auction-note,
.degraded-note {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 9.5px;
  line-height: 1.5;
}

.degraded-note {
  color: var(--warn);
}

.pending-list {
  display: grid;
}

.pending-list > div {
  min-height: 54px;
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  color: var(--muted);
}

.pending-list > div:first-child {
  border-top: 0;
}

.pending-list span {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.pending-list b {
  color: var(--fg2);
  font-size: 10.5px;
}

.pending-list small {
  overflow: hidden;
  color: var(--muted);
  font-size: 8.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-list em {
  padding: 1px 5px;
  border: 1px solid var(--border2);
  border-radius: 999px;
  color: var(--muted);
  font-size: 8px;
  font-style: normal;
}

@keyframes shimmer {
  to {
    background-position: -200% 0;
  }
}

@keyframes pulse-dot {
  from {
    opacity: 0.4;
  }
  to {
    opacity: 1;
  }
}

@media (max-width: 1720px) {
  .main-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .side-stack {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }
}

@media (max-width: 1050px) {
  .workbench {
    grid-template-columns: minmax(0, 1fr);
  }

  .watch-side {
    position: static;
    max-height: none;
  }

  .watch-list {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 8px;
  }

  .watch-row {
    flex: 0 0 230px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .watch-row.active::before {
    display: none;
  }

  .watch-row.active {
    box-shadow: inset 0 0 0 1px var(--brand);
  }

  .watch-remove {
    opacity: 1;
  }

  .watch-foot {
    display: none;
  }
}

@media (max-width: 820px) {
  .add-panel {
    grid-template-columns: 1fr;
    padding: 15px;
  }

  .add-feedback {
    grid-column: auto;
  }

  .quote-block {
    margin-left: 0;
  }

  .refresh-button {
    margin-left: auto;
  }

  .side-stack {
    grid-template-columns: 1fr;
  }
}

@container (max-width: 760px) {
  .chart-layout--with-readings {
    grid-template-columns: minmax(0, 1fr);
  }

  .chart-layout--with-readings > .chart-readings {
    padding-top: 12px;
    padding-left: 0;
    border-top: 1px solid var(--border);
    border-left: 0;
  }
}

@media (max-width: 560px) {
  .intraday-page {
    gap: 13px;
  }

  .add-row {
    flex-direction: column;
  }

  .primary-button {
    width: 100%;
  }

  .hero {
    padding: 15px;
  }

  .identity h2 {
    font-size: 18px;
  }

  .quote-block {
    width: 100%;
  }

  .refresh-button {
    margin-left: 0;
  }

  .context-strip {
    gap: 8px 14px;
  }

  .context-strip > div {
    flex: 1 1 calc(50% - 14px);
  }

  .chart-panel .panel-head {
    flex-wrap: wrap;
  }
}
</style>
