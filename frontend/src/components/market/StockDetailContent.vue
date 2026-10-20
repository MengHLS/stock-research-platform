<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import LimitUpDetail from './LimitUpDetail.vue'
import { api, callApi } from '../../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../../api/errors'
import type { LimitUpReviewRow, ReviewStockSeries } from '../../market/review'

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

const stockSeries = ref<ReviewStockSeries | null>(null)
const stockLoading = ref(false)
const stockFailure = ref<ApiFailure | null>(null)
let controller: AbortController | null = null
let sequence = 0

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

async function loadStockSeries() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  const requestSequence = ++sequence
  stockLoading.value = true
  stockFailure.value = null
  stockSeries.value = null
  const result = await callApi(
    (signal) =>
      api.GET('/api/v1/market/review/stock-series', {
        params: {
          query: {
            symbol: props.row.symbol,
            date: props.row.date,
            window: Math.min(60, Math.max(1, props.windowMax ?? 60)),
          },
        },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (controller !== current || requestSequence !== sequence) return
  stockLoading.value = false
  if (result.ok) stockSeries.value = result.data
  else if (result.failure.kind !== 'aborted') stockFailure.value = result.failure
}

watch(
  () => [props.row.symbol, props.row.date, props.windowMax] as const,
  () => {
    void loadStockSeries()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  controller?.abort()
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
    @save-note="emit('save-note', $event)"
    @select="emit('select', $event)"
    @retry-stock="loadStockSeries"
  />
</template>
