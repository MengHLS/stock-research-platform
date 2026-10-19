import { shallowRef } from 'vue'

import { api, callApi, type ApiFailure, type ApiResult } from '../api/client'
import type { ReviewOverview } from './review'

type LoadOverview = (date: string, signal: AbortSignal) => Promise<ApiResult<ReviewOverview>>

const fetchOverview: LoadOverview = (date, signal) =>
  callApi(
    (requestSignal) =>
      api.GET('/api/v1/market/review/overview', {
        params: { query: { date, window: 1 } },
        signal: requestSignal,
      }),
    { access: 'read', signal },
  )

/** Each detail selection owns its request, including selections served from page data. */
export function useReviewDetail(loadOverview: LoadOverview = fetchOverview) {
  const data = shallowRef<ReviewOverview | null>(null)
  const loading = shallowRef(false)
  const failure = shallowRef<ApiFailure | null>(null)
  let controller: AbortController | null = null

  function clear() {
    controller?.abort()
    controller = null
    data.value = null
    failure.value = null
    loading.value = false
  }

  async function load(date: string, cached: ReviewOverview | null) {
    clear()
    if (cached?.date === date) {
      data.value = cached
      return
    }
    const current = new AbortController()
    controller = current
    loading.value = true
    const result = await loadOverview(date, current.signal)
    if (controller !== current || current.signal.aborted) return
    loading.value = false
    if (result.ok) data.value = result.data
    else if (result.failure.kind !== 'aborted') failure.value = result.failure
  }

  return { data, loading, failure, load, clear }
}
