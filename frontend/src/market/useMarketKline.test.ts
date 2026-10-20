import { describe, expect, it } from 'vitest'

import type { ApiResult } from '../api/client'
import type { MarketKlineSeries } from './kline'
import { useMarketKline } from './useMarketKline'

function series(symbol: string, period: 'day' | 'week'): MarketKlineSeries {
  return {
    symbol,
    period,
    provider: 'tencent',
    adjustment: 'none',
    week_in_progress: period === 'week',
    total: 1,
    limits: [],
    bars: [
      {
        trading_day: '2026-10-20',
        open: '100',
        high: '102',
        low: '99',
        close: '101',
        volume_shares: '1000',
      },
    ],
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('market kline request ownership', () => {
  it('reuses the same symbol-period-limit result', async () => {
    let calls = 0
    const detail = useMarketKline(async (symbol, period) => {
      calls += 1
      return { ok: true, data: series(symbol, period), requestId: null }
    })

    await detail.load('600519.SH', 'day', 120)
    await detail.load('600519.SH', 'day', 120)

    expect(calls).toBe(1)
    expect(detail.series.value?.period).toBe('day')
  })

  it('does not let an older period overwrite the latest selection', async () => {
    const day = deferred<ApiResult<MarketKlineSeries>>()
    const week = deferred<ApiResult<MarketKlineSeries>>()
    let call = 0
    const detail = useMarketKline(() => (++call === 1 ? day.promise : week.promise))

    const dayLoad = detail.load('600519.SH', 'day', 120)
    const weekLoad = detail.load('600519.SH', 'week', 60)
    week.resolve({ ok: true, data: series('600519.SH', 'week'), requestId: null })
    await weekLoad
    day.resolve({ ok: true, data: series('600519.SH', 'day'), requestId: null })
    await dayLoad

    expect(detail.series.value?.period).toBe('week')
  })

  it('cancels a delayed period when switching back to already loaded data', async () => {
    const week = deferred<ApiResult<MarketKlineSeries>>()
    let weekSignal: AbortSignal | undefined
    const detail = useMarketKline((symbol, period, _limit, signal) => {
      if (period === 'week') {
        weekSignal = signal
        return week.promise
      }
      return Promise.resolve({ ok: true, data: series(symbol, period), requestId: null })
    })

    await detail.load('600519.SH', 'day', 120)
    const weekLoad = detail.load('600519.SH', 'week', 60)
    await detail.load('600519.SH', 'day', 120)

    expect(weekSignal?.aborted).toBe(true)
    expect(detail.loading.value).toBe(false)
    expect(detail.series.value?.period).toBe('day')

    week.resolve({ ok: true, data: series('600519.SH', 'week'), requestId: null })
    await weekLoad

    expect(detail.series.value?.period).toBe('day')
  })

  it('ignores a delayed failure from a period the user already left', async () => {
    const week = deferred<ApiResult<MarketKlineSeries>>()
    const detail = useMarketKline((symbol, period) => {
      if (period === 'week') return week.promise
      return Promise.resolve({ ok: true, data: series(symbol, period), requestId: null })
    })

    await detail.load('600519.SH', 'day', 120)
    const weekLoad = detail.load('600519.SH', 'week', 60)
    await detail.load('600519.SH', 'day', 120)

    week.resolve({
      ok: false,
      failure: {
        kind: 'network',
        code: 'NETWORK_UNAVAILABLE',
        message: '周线失败。',
        status: null,
        requestId: 'req-week',
        retryable: true,
        fields: [],
      },
    })
    await weekLoad

    expect(detail.failure.value).toBeNull()
    expect(detail.loading.value).toBe(false)
    expect(detail.series.value?.period).toBe('day')
  })

  it('treats explicit no-data as empty and supports a forced retry', async () => {
    let calls = 0
    const detail = useMarketKline(async (symbol, period) => {
      calls += 1
      if (calls === 1) {
        return {
          ok: false,
          failure: {
            kind: 'business',
            code: 'MARKET_DATA_UNAVAILABLE',
            message: '没有 K 线。',
            status: 404,
            requestId: 'req-empty',
            retryable: false,
            fields: [],
          },
        }
      }
      return { ok: true, data: series(symbol, period), requestId: null }
    })

    await detail.load('600519.SH', 'day', 120)
    expect(detail.failure.value).toBeNull()
    expect(detail.series.value).toBeNull()

    detail.retry()
    await Promise.resolve()
    await Promise.resolve()

    expect(calls).toBe(2)
    expect(detail.series.value?.period).toBe('day')
  })
})
