import { shallowRef } from 'vue'

import type { ApiFailure, ApiResult } from '../api/errors'
import type { FirstBoardHistory } from './first-board-classifier'

type LoadHistory = (symbol: string, signal: AbortSignal) => Promise<ApiResult<FirstBoardHistory>>

export function useStockFirstBoardEvents(loadHistory: LoadHistory) {
  const events = shallowRef<FirstBoardHistory | null>(null)
  const loading = shallowRef(false)
  const failure = shallowRef<ApiFailure | null>(null)
  let currentSymbol: string | null = null
  let controller: AbortController | null = null
  let requestToken = 0

  async function fetchHistory(symbol: string) {
    controller?.abort()
    const current = new AbortController()
    controller = current
    const token = ++requestToken
    loading.value = true
    failure.value = null
    const result = await loadHistory(symbol, current.signal)
    if (controller !== current || token !== requestToken || current.signal.aborted) return
    loading.value = false
    if (result.ok) {
      events.value = result.data
    } else if (result.failure.kind !== 'aborted') {
      events.value = null
      failure.value = result.failure
    }
  }

  async function load(symbol: string) {
    currentSymbol = symbol
    events.value = null
    await fetchHistory(symbol)
  }

  function retry() {
    if (currentSymbol) void fetchHistory(currentSymbol)
  }

  function clear() {
    currentSymbol = null
    requestToken += 1
    controller?.abort()
    controller = null
    events.value = null
    loading.value = false
    failure.value = null
  }

  return { events, loading, failure, load, retry, clear }
}
