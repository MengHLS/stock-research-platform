import { shallowRef } from 'vue'

import type { ApiFailure, ApiResult } from '../api/client'
import type { LimitUpReviewRow, ReviewStockSeries } from './review'
import type { ReviewStockFacts } from './stock-facts'

type LoadSeries = (
  row: LimitUpReviewRow,
  windowMax: number,
  signal: AbortSignal,
) => Promise<ApiResult<ReviewStockSeries>>

type LoadFacts = (
  symbol: string,
  tradingDay: string,
  signal: AbortSignal,
) => Promise<ApiResult<ReviewStockFacts>>

export function useStockDetail(loadSeries: LoadSeries, loadFacts: LoadFacts) {
  const stockSeries = shallowRef<ReviewStockSeries | null>(null)
  const stockLoading = shallowRef(false)
  const stockFailure = shallowRef<ApiFailure | null>(null)
  const facts = shallowRef<ReviewStockFacts | null>(null)
  const factsLoading = shallowRef(false)
  const factsFailure = shallowRef<ApiFailure | null>(null)

  let current: { row: LimitUpReviewRow; windowMax: number } | null = null
  let generation = 0
  let seriesToken = 0
  let factsToken = 0
  let seriesController: AbortController | null = null
  let factsController: AbortController | null = null

  function clear() {
    generation += 1
    seriesToken += 1
    factsToken += 1
    seriesController?.abort()
    factsController?.abort()
    seriesController = null
    factsController = null
    current = null
    stockSeries.value = null
    stockFailure.value = null
    stockLoading.value = false
    facts.value = null
    factsFailure.value = null
    factsLoading.value = false
  }

  async function fetchSeries(row: LimitUpReviewRow, windowMax: number, requestGeneration: number) {
    seriesController?.abort()
    const controller = new AbortController()
    seriesController = controller
    const requestToken = ++seriesToken
    stockLoading.value = true
    stockFailure.value = null
    const result = await loadSeries(row, windowMax, controller.signal)
    if (
      generation !== requestGeneration ||
      requestToken !== seriesToken ||
      controller.signal.aborted
    ) {
      return
    }
    stockLoading.value = false
    if (result.ok) stockSeries.value = result.data
    else if (result.failure.kind !== 'aborted') stockFailure.value = result.failure
  }

  async function fetchFacts(symbol: string, tradingDay: string, requestGeneration: number) {
    factsController?.abort()
    const controller = new AbortController()
    factsController = controller
    const requestToken = ++factsToken
    factsLoading.value = true
    factsFailure.value = null
    const result = await loadFacts(symbol, tradingDay, controller.signal)
    if (
      generation !== requestGeneration ||
      requestToken !== factsToken ||
      controller.signal.aborted
    ) {
      return
    }
    factsLoading.value = false
    if (result.ok) facts.value = result.data
    else if (result.failure.kind !== 'aborted') factsFailure.value = result.failure
  }

  async function load(row: LimitUpReviewRow, windowMax: number) {
    clear()
    current = { row, windowMax }
    const requestGeneration = generation
    await Promise.allSettled([
      fetchSeries(row, windowMax, requestGeneration),
      fetchFacts(row.symbol, row.date, requestGeneration),
    ])
  }

  function retrySeries() {
    if (current) void fetchSeries(current.row, current.windowMax, generation)
  }

  function retryFacts() {
    if (current) void fetchFacts(current.row.symbol, current.row.date, generation)
  }

  return {
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
  }
}
