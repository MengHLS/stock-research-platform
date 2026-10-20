import { shallowRef } from 'vue'

import { api, callApi, type ApiFailure, type ApiResult } from '../api/client'
import type { MarketStateDescription } from './state-description'

type LoadDescription = (
  date: string,
  signal: AbortSignal,
) => Promise<ApiResult<MarketStateDescription>>

const fetchDescription: LoadDescription = (date, signal) =>
  callApi(
    (requestSignal) =>
      api.GET('/api/v1/market/state/description', {
        params: { query: { date } },
        signal: requestSignal,
      }),
    { access: 'read', signal },
  )

export function useMarketStateDescription(loadDescription: LoadDescription = fetchDescription) {
  const data = shallowRef<MarketStateDescription | null>(null)
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

  async function loadDate(date: string) {
    clear()
    if (!date) return
    const current = new AbortController()
    controller = current
    loading.value = true
    const result = await loadDescription(date, current.signal)
    if (controller !== current || current.signal.aborted) return
    loading.value = false
    if (result.ok) data.value = result.data
    else if (result.failure.kind !== 'aborted') failure.value = result.failure
  }

  return { data, loading, failure, loadDate, clear }
}
