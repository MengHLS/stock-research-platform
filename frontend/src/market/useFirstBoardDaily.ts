import { onMounted, onUnmounted, ref, watch } from 'vue'

import { api, callApi } from '../api/client'
import type { ApiFailure } from '../api/errors'
import type { components } from '../api/schema'

export function useFirstBoardDaily() {
  const date = ref('')
  const data = ref<components['schemas']['FirstBoardDailyRead'] | null>(null)
  const failure = ref<ApiFailure | null>(null)
  const loading = ref(false)
  let controller: AbortController | null = null

  watch(date, () => {
    controller?.abort()
    data.value = null
    failure.value = null
    loading.value = false
  })

  async function load(offset = 0, keepBatch = offset > 0) {
    const batchId = keepBatch ? data.value?.batch_id : null
    const queryDate = keepBatch ? (data.value?.trading_day ?? date.value) : date.value
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true
    failure.value = null
    data.value = null
    const result = await callApi(
      (signal) =>
        api.GET('/api/v1/research/first-board-classifier/daily', {
          params: { query: { date: queryDate || null, batch_id: batchId, offset, limit: 100 } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    )
    if (current !== controller || current.signal.aborted) return
    loading.value = false
    if (result.ok) data.value = result.data
    else if (result.failure.kind !== 'aborted') failure.value = result.failure
  }

  onMounted(() => load())
  onUnmounted(() => controller?.abort())
  return { date, data, failure, loading, load }
}
