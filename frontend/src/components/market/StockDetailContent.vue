<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'

import LimitUpDetail from './LimitUpDetail.vue'
import { api, callApi } from '../../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../../api/errors'
import type { LimitUpReviewRow } from '../../market/review'
import { useLatestIntraday } from '../../market/useLatestIntraday'
import { useStockFirstBoardEvents } from '../../market/useStockFirstBoardEvents'
import { useStockDetail } from '../../market/useStockDetail'

const props = defineProps<{
  row: LimitUpReviewRow
  windowMax?: number
  note: string
}>()
const emit = defineEmits<{
  'save-note': [note: string]
}>()

const {
  stockSeries,
  stockLoading,
  stockFailure,
  facts,
  factsLoading,
  factsFailure,
  load,
  retrySeries,
  retryFacts,
  clear,
} = useStockDetail(
  async (row, windowMax, signal) =>
    callApi(
      (requestSignal) =>
        api.GET('/api/v1/market/review/stock-series', {
          params: {
            query: {
              symbol: row.symbol,
              date: row.date,
              window: Math.min(120, Math.max(1, windowMax)),
            },
          },
          signal: requestSignal,
        }),
      { access: 'read', signal },
    ),
  async (symbol, tradingDay, signal) =>
    callApi(
      (requestSignal) =>
        api.GET('/api/v1/market/review/stock-facts', {
          params: { query: { symbol, date: tradingDay } },
          signal: requestSignal,
        }),
      { access: 'read', signal },
    ),
)

const {
  bars: intradayBars,
  tradingDay: intradayTradingDay,
  loading: intradayLoading,
  failure: intradayFailure,
  load: loadIntraday,
  retry: retryIntraday,
  reset: resetIntraday,
} = useLatestIntraday(async (symbol, signal) =>
  callApi(
    (requestSignal) =>
      api.GET('/api/v1/market/intraday', {
        params: { query: { symbol, period: 'm1', limit: 800 } },
        signal: requestSignal,
      }),
    { access: 'read', signal },
  ),
)

const {
  events: firstBoardEvents,
  loading: firstBoardLoading,
  failure: firstBoardFailure,
  load: loadFirstBoardEvents,
  retry: retryFirstBoardEvents,
  clear: clearFirstBoardEvents,
} = useStockFirstBoardEvents(async (symbol, signal) =>
  callApi(
    (requestSignal) =>
      api.GET('/api/v1/research/first-board-classifier/stock-history', {
        params: { query: { stock_code: symbol, limit: 100 } },
        signal: requestSignal,
      }),
    { access: 'read', signal },
  ),
)

function failureText(failure: ApiFailure): string {
  if (isAuthNotConfigured(failure)) return '登录服务尚未启用，无法读取历史复盘数据。'
  if (failure.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
  return failure.message
}

watch(
  () => [props.row.symbol, props.row.date, props.windowMax] as const,
  () => {
    resetIntraday()
    void load(props.row, props.windowMax ?? 120)
    void loadFirstBoardEvents(props.row.symbol)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  clear()
  resetIntraday()
  clearFirstBoardEvents()
})

function requestIntraday() {
  void loadIntraday(props.row.symbol)
}
</script>

<template>
  <LimitUpDetail
    :row="row"
    :note="note"
    :stock-series="stockSeries"
    :stock-loading="stockLoading"
    :stock-failure="stockFailure ? failureText(stockFailure) : null"
    :stock-request-id="stockFailure?.requestId"
    :facts="facts"
    :facts-loading="factsLoading"
    :facts-failure="factsFailure ? failureText(factsFailure) : null"
    :facts-request-id="factsFailure?.requestId"
    :intraday-bars="intradayBars"
    :intraday-trading-day="intradayTradingDay"
    :intraday-loading="intradayLoading"
    :intraday-failure="intradayFailure ? failureText(intradayFailure) : null"
    :intraday-request-id="intradayFailure?.requestId"
    :first-board-events="firstBoardEvents"
    :first-board-loading="firstBoardLoading"
    :first-board-failure="firstBoardFailure ? failureText(firstBoardFailure) : null"
    :first-board-request-id="firstBoardFailure?.requestId"
    @save-note="emit('save-note', $event)"
    @retry-stock="retrySeries"
    @retry-facts="retryFacts"
    @request-intraday="requestIntraday"
    @retry-intraday="retryIntraday"
    @retry-first-board="retryFirstBoardEvents"
  />
</template>
