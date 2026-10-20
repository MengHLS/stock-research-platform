<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'

import LimitUpDetail from './LimitUpDetail.vue'
import { api, callApi } from '../../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../../api/errors'
import type { LimitUpReviewRow } from '../../market/review'
import { useStockDetail } from '../../market/useStockDetail'

const props = defineProps<{
  row: LimitUpReviewRow
  peerRows: LimitUpReviewRow[]
  windowMax?: number
  note: string
}>()
const emit = defineEmits<{
  select: [row: LimitUpReviewRow]
  'save-note': [note: string]
}>()

const {
  stockSeries,
  stockLoading,
  stockFailure,
  profile: stockProfile,
  profileLoading,
  profileFailure,
  load,
  retrySeries,
  retryProfile,
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
              window: Math.min(60, Math.max(1, windowMax)),
            },
          },
          signal: requestSignal,
        }),
      { access: 'read', signal },
    ),
  async (symbol, signal) =>
    callApi(
      (requestSignal) =>
        api.GET('/api/v1/market/stock-profile', {
          params: { query: { symbol } },
          signal: requestSignal,
        }),
      { access: 'read', signal },
    ),
)

const sameSector = computed(() => {
  const row = props.row
  return props.peerRows.filter(
    (item) =>
      item.date === row.date &&
      item.sector === row.sector &&
      item.status === 'limit_up' &&
      !(item.symbol === row.symbol && item.status === row.status),
  )
})
function failureText(failure: ApiFailure): string {
  if (isAuthNotConfigured(failure)) return '登录服务尚未启用，无法读取历史复盘数据。'
  if (failure.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
  return failure.message
}

watch(
  () => [props.row.symbol, props.row.date, props.windowMax] as const,
  () => {
    void load(props.row, props.windowMax ?? 60)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  clear()
})
</script>

<template>
  <LimitUpDetail
    :row="row"
    :same-sector="sameSector"
    :note="note"
    :stock-series="stockSeries"
    :stock-loading="stockLoading"
    :stock-failure="stockFailure ? failureText(stockFailure) : null"
    :stock-request-id="stockFailure?.requestId"
    :industry="stockProfile?.industry ?? null"
    :industry-provider="stockProfile?.provider ?? null"
    :industry-loading="profileLoading"
    :industry-failure="profileFailure ? failureText(profileFailure) : null"
    :industry-request-id="profileFailure?.requestId"
    @save-note="emit('save-note', $event)"
    @select="emit('select', $event)"
    @retry-stock="retrySeries"
    @retry-industry="retryProfile"
  />
</template>
