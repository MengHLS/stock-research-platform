import { shallowRef } from 'vue'

import type { ApiFailure, ApiResult } from '../api/client'
import { latestTradingDayBars, type IntradayBar, type IntradaySeries } from './intraday'

type LoadIntraday = (symbol: string, signal: AbortSignal) => Promise<ApiResult<IntradaySeries>>

export function useLatestIntraday(loadIntraday: LoadIntraday) {
  const bars = shallowRef<IntradayBar[]>([])
  const tradingDay = shallowRef<string | null>(null)
  const loading = shallowRef(false)
  const failure = shallowRef<ApiFailure | null>(null)
  let currentSymbol: string | null = null
  let loadedSymbol: string | null = null
  let controller: AbortController | null = null
  let requestToken = 0

  function reset() {
    requestToken += 1
    controller?.abort()
    controller = null
    currentSymbol = null
    loadedSymbol = null
    bars.value = []
    tradingDay.value = null
    loading.value = false
    failure.value = null
  }

  async function load(symbol: string, options: { force?: boolean } = {}) {
    const force = options.force ?? false
    if (!force && loadedSymbol === symbol) return
    controller?.abort()
    const next = new AbortController()
    controller = next
    const token = ++requestToken
    if (loadedSymbol !== symbol) {
      loadedSymbol = null
      bars.value = []
      tradingDay.value = null
    }
    currentSymbol = symbol
    loading.value = true
    failure.value = null
    const result = await loadIntraday(symbol, next.signal)
    if (token !== requestToken || next.signal.aborted) return
    loading.value = false
    if (!result.ok) {
      if (result.failure.kind !== 'aborted') failure.value = result.failure
      return
    }
    const latest = latestTradingDayBars(result.data.bars)
    bars.value = latest
    tradingDay.value = latest[0]?.trading_day ?? null
    loadedSymbol = symbol
  }

  function retry() {
    if (currentSymbol) void load(currentSymbol, { force: true })
  }

  return { bars, tradingDay, loading, failure, load, retry, reset }
}
