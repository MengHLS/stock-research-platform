import { shallowRef } from 'vue'

import type { ApiFailure, ApiResult } from '../api/client'
import type { MarketKlinePeriod, MarketKlineSeries } from './kline'

type LoadKline = (
  symbol: string,
  period: MarketKlinePeriod,
  limit: number,
  signal: AbortSignal,
) => Promise<ApiResult<MarketKlineSeries>>

export function useMarketKline(loadKline: LoadKline) {
  const series = shallowRef<MarketKlineSeries | null>(null)
  const loading = shallowRef(false)
  const failure = shallowRef<ApiFailure | null>(null)
  let current: { symbol: string; period: MarketKlinePeriod; limit: number } | null = null
  let loadedKey: string | null = null
  let controller: AbortController | null = null
  let requestToken = 0

  function reset() {
    requestToken += 1
    controller?.abort()
    controller = null
    current = null
    loadedKey = null
    series.value = null
    loading.value = false
    failure.value = null
  }

  async function load(
    symbol: string,
    period: MarketKlinePeriod,
    limit: number,
    options: { force?: boolean } = {},
  ) {
    const key = `${symbol}:${period}:${limit}`
    if (!options.force && loadedKey === key && series.value) return
    controller?.abort()
    const next = new AbortController()
    controller = next
    const token = ++requestToken
    current = { symbol, period, limit }
    loading.value = true
    failure.value = null
    if (loadedKey !== key) series.value = null
    const result = await loadKline(symbol, period, limit, next.signal)
    if (token !== requestToken || next.signal.aborted) return
    loading.value = false
    if (!result.ok) {
      if (result.failure.code === 'MARKET_DATA_UNAVAILABLE') {
        series.value = null
        loadedKey = key
      } else if (result.failure.kind !== 'aborted') {
        failure.value = result.failure
      }
      return
    }
    series.value = result.data
    loadedKey = key
  }

  function retry() {
    if (current) {
      void load(current.symbol, current.period, current.limit, { force: true })
    }
  }

  return { series, loading, failure, load, retry, reset }
}
