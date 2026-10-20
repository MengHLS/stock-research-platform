import { describe, expect, it } from 'vitest'

import type { ApiResult } from '../api/client'
import type { IntradaySeries } from './intraday'
import { useLatestIntraday } from './useLatestIntraday'

function bar(day: string, start: string) {
  return {
    start,
    trading_day: day,
    open: '10',
    high: '10.2',
    low: '9.9',
    close: '10.1',
    volume_shares: '1000',
  }
}

function series(symbol: string, latest = '2026-10-20', previous = '2026-10-19'): IntradaySeries {
  return {
    symbol,
    period: 'm1',
    provider: 'tencent',
    bars: [
      bar(previous, `${previous}T01:31:00Z`),
      bar(latest, `${latest}T01:31:00Z`),
      bar(latest, `${latest}T01:32:00Z`),
    ],
    total: 3,
    limits: [],
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('latest intraday loading', () => {
  it('keeps only the latest trading day and reuses the loaded symbol', async () => {
    let calls = 0
    const detail = useLatestIntraday(async (symbol) => {
      calls += 1
      return { ok: true, data: series(symbol), requestId: null }
    })

    await detail.load('600519.SH')
    await detail.load('600519.SH')

    expect(calls).toBe(1)
    expect(detail.bars.value).toHaveLength(2)
    expect(detail.bars.value.every((item) => item.trading_day === '2026-10-20')).toBe(true)
    expect(detail.tradingDay.value).toBe('2026-10-20')
  })

  it('does not let an older symbol overwrite the latest selection', async () => {
    const first = deferred<ApiResult<IntradaySeries>>()
    const second = deferred<ApiResult<IntradaySeries>>()
    let call = 0
    const detail = useLatestIntraday(() => (++call === 1 ? first.promise : second.promise))

    const oldLoad = detail.load('600519.SH')
    const latestLoad = detail.load('000001.SZ')
    second.resolve({ ok: true, data: series('000001.SZ'), requestId: null })
    await latestLoad
    first.resolve({
      ok: true,
      data: series('600519.SH', '2026-10-18', '2026-10-17'),
      requestId: null,
    })
    await oldLoad

    expect(detail.bars.value[0]?.trading_day).toBe('2026-10-20')
    expect(detail.tradingDay.value).toBe('2026-10-20')
  })

  it('retries a failed request with the current symbol', async () => {
    let calls = 0
    const detail = useLatestIntraday(async (symbol) => {
      calls += 1
      if (calls === 1) {
        return {
          ok: false,
          failure: {
            kind: 'network',
            code: null,
            message: '分时不可用',
            status: null,
            requestId: 'req-intraday',
            retryable: true,
            fields: [],
          },
        }
      }
      return { ok: true, data: series(symbol), requestId: null }
    })

    await detail.load('600519.SH')
    expect(detail.failure.value?.requestId).toBe('req-intraday')

    detail.retry()
    await Promise.resolve()
    await Promise.resolve()

    expect(detail.failure.value).toBeNull()
    expect(detail.bars.value).toHaveLength(2)
  })

  it('treats an explicit no-data response as empty and still allows a forced retry', async () => {
    let calls = 0
    const detail = useLatestIntraday(async (symbol) => {
      calls += 1
      if (calls === 1) {
        return {
          ok: false,
          failure: {
            kind: 'business',
            code: 'MARKET_DATA_UNAVAILABLE',
            message: '没有可用分时。',
            status: 404,
            requestId: 'req-empty',
            retryable: false,
            fields: [],
          },
        }
      }
      return { ok: true, data: series(symbol), requestId: null }
    })

    await detail.load('600519.SH')
    expect(detail.failure.value).toBeNull()
    expect(detail.bars.value).toEqual([])

    detail.retry()
    await Promise.resolve()
    await Promise.resolve()

    expect(calls).toBe(2)
    expect(detail.bars.value).toHaveLength(2)
  })

  it('clears data and aborts the current request on reset', async () => {
    const pending = deferred<ApiResult<IntradaySeries>>()
    const signals: AbortSignal[] = []
    const detail = useLatestIntraday((_symbol, signal) => {
      signals.push(signal)
      return pending.promise
    })

    const load = detail.load('600519.SH')
    expect(detail.loading.value).toBe(true)
    detail.reset()
    expect(detail.loading.value).toBe(false)
    expect(signals[0]?.aborted).toBe(true)

    pending.resolve({ ok: true, data: series('600519.SH'), requestId: null })
    await load
    expect(detail.bars.value).toEqual([])
    expect(detail.loading.value).toBe(false)
  })
})
