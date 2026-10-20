import { shallowRef } from 'vue'

import type { ApiFailure, ApiResult } from '../api/client'
import type { LimitUpReviewRow, ReviewStockSeries } from './review'
import type { StockProfile } from './stock-profile'

type LoadSeries = (
  row: LimitUpReviewRow,
  windowMax: number,
  signal: AbortSignal,
) => Promise<ApiResult<ReviewStockSeries>>

type LoadProfile = (symbol: string, signal: AbortSignal) => Promise<ApiResult<StockProfile>>

export function useStockDetail(loadSeries: LoadSeries, loadProfile: LoadProfile) {
  const stockSeries = shallowRef<ReviewStockSeries | null>(null)
  const stockLoading = shallowRef(false)
  const stockFailure = shallowRef<ApiFailure | null>(null)
  const profile = shallowRef<StockProfile | null>(null)
  const profileLoading = shallowRef(false)
  const profileFailure = shallowRef<ApiFailure | null>(null)

  let current: { row: LimitUpReviewRow; windowMax: number } | null = null
  let generation = 0
  let seriesToken = 0
  let profileToken = 0
  let seriesController: AbortController | null = null
  let profileController: AbortController | null = null

  function clear() {
    generation += 1
    seriesToken += 1
    profileToken += 1
    seriesController?.abort()
    profileController?.abort()
    seriesController = null
    profileController = null
    current = null
    stockSeries.value = null
    stockFailure.value = null
    stockLoading.value = false
    profile.value = null
    profileFailure.value = null
    profileLoading.value = false
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

  async function fetchProfile(symbol: string, requestGeneration: number) {
    profileController?.abort()
    const controller = new AbortController()
    profileController = controller
    const requestToken = ++profileToken
    profileLoading.value = true
    profileFailure.value = null
    const result = await loadProfile(symbol, controller.signal)
    if (
      generation !== requestGeneration ||
      requestToken !== profileToken ||
      controller.signal.aborted
    ) {
      return
    }
    profileLoading.value = false
    if (result.ok) profile.value = result.data
    else if (result.failure.kind !== 'aborted') profileFailure.value = result.failure
  }

  async function load(row: LimitUpReviewRow, windowMax: number) {
    clear()
    current = { row, windowMax }
    const requestGeneration = generation
    await Promise.allSettled([
      fetchSeries(row, windowMax, requestGeneration),
      fetchProfile(row.symbol, requestGeneration),
    ])
  }

  function retrySeries() {
    if (current) void fetchSeries(current.row, current.windowMax, generation)
  }

  function retryProfile() {
    if (current) void fetchProfile(current.row.symbol, generation)
  }

  return {
    stockSeries,
    stockLoading,
    stockFailure,
    profile,
    profileLoading,
    profileFailure,
    load,
    retrySeries,
    retryProfile,
    clear,
  }
}
