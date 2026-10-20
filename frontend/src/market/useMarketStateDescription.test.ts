import { describe, expect, it } from 'vitest'

import type { ApiResult } from '../api/client'
import type { MarketStateDescription } from './state-description'
import { useMarketStateDescription } from './useMarketStateDescription'

function description(date: string): MarketStateDescription {
  return { date } as MarketStateDescription
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('market state description request ownership', () => {
  it('does not let an older date overwrite the latest selection', async () => {
    const old = deferred<ApiResult<MarketStateDescription>>()
    const latest = deferred<ApiResult<MarketStateDescription>>()
    const detail = useMarketStateDescription((date) =>
      date === '2026-09-18' ? old.promise : latest.promise,
    )

    const oldLoad = detail.loadDate('2026-09-18')
    const latestLoad = detail.loadDate('2026-09-19')
    latest.resolve({ ok: true, data: description('2026-09-19'), requestId: null })
    await latestLoad
    old.resolve({ ok: true, data: description('2026-09-18'), requestId: null })
    await oldLoad

    expect(detail.data.value?.date).toBe('2026-09-19')
  })

  it('clears loading and aborts the current request when unmounted', async () => {
    const pending = deferred<ApiResult<MarketStateDescription>>()
    const signals: AbortSignal[] = []
    const detail = useMarketStateDescription((_date, nextSignal) => {
      signals.push(nextSignal)
      return pending.promise
    })

    const load = detail.loadDate('2026-09-19')
    expect(detail.loading.value).toBe(true)
    detail.clear()
    expect(detail.loading.value).toBe(false)
    expect(signals).toHaveLength(1)
    expect(signals[0]?.aborted).toBe(true)

    pending.resolve({ ok: true, data: description('2026-09-19'), requestId: null })
    await load
    expect(detail.data.value).toBeNull()
  })
})
