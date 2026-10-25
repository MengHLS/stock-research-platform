import { shallowRef } from 'vue'

import type { ApiFailure, ApiResult } from '../api/errors'
import {
  classifyRecursiveFailure,
  type FirstBoardRecursiveStatus,
  type FirstBoardRecursiveTargetDetail,
} from './first-board-recursive'

type LoadDetail = (
  symbol: string,
  signal: AbortSignal,
) => Promise<ApiResult<FirstBoardRecursiveTargetDetail>>

/**
 * State for one stock's frozen recursive detail.
 *
 * Same discipline as `useStockDetail` / `useStockFirstBoardEvents`: a new stock aborts the
 * previous request, a sequence token drops late responses, and switching stocks resets the
 * view instead of mixing two stocks. A 404 `..._TARGET_NOT_FOUND` is normal frozen scope
 * (`missing`), not a failure; a 404 `..._SNAPSHOT_NOT_FOUND` is `unavailable`, which the
 * panel explains as "not imported yet" with a retry rather than an error.
 *
 * The request deliberately carries no `trade_date`: the frozen snapshot is a fixed research
 * delivery whose own `trade_date` is shown in the panel, so the tab does not pretend to
 * recompute per review day.
 */
export function useFirstBoardRecursive(loadDetail: LoadDetail) {
  const detail = shallowRef<FirstBoardRecursiveTargetDetail | null>(null)
  const status = shallowRef<FirstBoardRecursiveStatus>('idle')
  const failure = shallowRef<ApiFailure | null>(null)
  let currentSymbol: string | null = null
  let controller: AbortController | null = null
  let requestToken = 0

  async function fetchDetail(symbol: string) {
    controller?.abort()
    const current = new AbortController()
    controller = current
    const token = ++requestToken
    status.value = 'loading'
    failure.value = null
    const result = await loadDetail(symbol, current.signal)
    if (controller !== current || token !== requestToken || current.signal.aborted) return
    if (result.ok) {
      detail.value = result.data
      status.value = 'ready'
      return
    }
    const state = classifyRecursiveFailure(result.failure)
    if (state === 'aborted') return
    detail.value = null
    if (state === 'missing' || state === 'unavailable') {
      status.value = state
      failure.value = null
      return
    }
    status.value = 'failure'
    failure.value = result.failure
  }

  async function load(symbol: string) {
    currentSymbol = symbol
    detail.value = null
    failure.value = null
    await fetchDetail(symbol)
  }

  function retry() {
    if (currentSymbol) void fetchDetail(currentSymbol)
  }

  function clear() {
    currentSymbol = null
    requestToken += 1
    controller?.abort()
    controller = null
    detail.value = null
    status.value = 'idle'
    failure.value = null
  }

  return { detail, status, failure, load, retry, clear }
}
