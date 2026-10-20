<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import LimitUpDetail from './LimitUpDetail.vue'
import { api, callApi } from '../../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../../api/errors'
import type { LimitUpReviewRow, ReviewStockSeries } from '../../market/review'
import type { StockProfile } from '../../market/stock-profile'

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
const stockProfile = ref<StockProfile | null>(null)
const profileLoading = ref(false)
const profileFailure = ref<ApiFailure | null>(null)
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

async function loadDetail() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  const requestSequence = ++sequence
  stockLoading.value = true
  profileLoading.value = true
  stockFailure.value = null
  profileFailure.value = null
  stockSeries.value = null
  stockProfile.value = null
  const [seriesResult, profileResult] = await Promise.all([
    callApi(
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
    ),
    callApi(
      (signal) =>
        api.GET('/api/v1/market/stock-profile', {
          params: { query: { symbol: props.row.symbol } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    ),
  ])
  if (controller !== current || requestSequence !== sequence) return
  stockLoading.value = false
  profileLoading.value = false
  if (seriesResult.ok) stockSeries.value = seriesResult.data
  else if (seriesResult.failure.kind !== 'aborted') stockFailure.value = seriesResult.failure
  if (profileResult.ok) stockProfile.value = profileResult.data
  else if (profileResult.failure.kind !== 'aborted') profileFailure.value = profileResult.failure
}

watch(
  () => [props.row.symbol, props.row.date, props.windowMax] as const,
  () => {
    void loadDetail()
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
    :industry="stockProfile?.industry ?? null"
    :industry-provider="stockProfile?.provider ?? null"
    :industry-loading="profileLoading"
    :industry-failure="profileFailure ? failureText(profileFailure) : null"
    @save-note="emit('save-note', $event)"
    @select="emit('select', $event)"
    @retry-stock="loadDetail"
  />
</template>
