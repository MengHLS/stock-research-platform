import { describe, expect, it } from 'vitest'

import type { ApiResult } from '../api/client'
import type { LimitUpReviewRow, ReviewStockSeries } from './review'
import type { StockProfile } from './stock-profile'
import { useStockDetail } from './useStockDetail'

function row(symbol = '600519.SH'): LimitUpReviewRow {
  return {
    date: '2026-10-20',
    symbol,
    name: '贵州茅台',
    sector: '白酒',
    status: 'limit_up',
    boards: 1,
    boards_as_of_date: '2026-10-20',
    limit_up_time: '09:35:00',
    limit_up_time_as_of_date: '2026-10-20',
    broken_kind: null,
    change_pct: '10.00',
    one_word_board: false,
  }
}

function series(symbol: string): ReviewStockSeries {
  return {
    symbol,
    date: '2026-10-20',
    window_requested: 60,
    window_actual: 0,
    bars: [],
    issues: [],
  } as unknown as ReviewStockSeries
}

function profile(symbol: string): StockProfile {
  return { symbol, name: '贵州茅台', industry: '白酒Ⅱ', provider: 'eastmoney' }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

describe('stock detail request ownership', () => {
  it('publishes series and industry independently when one source is slower', async () => {
    const stock = deferred<ApiResult<ReviewStockSeries>>()
    const industry = deferred<ApiResult<StockProfile>>()
    const detail = useStockDetail(
      () => stock.promise,
      () => industry.promise,
    )

    const load = detail.load(row(), 60)
    industry.resolve({ ok: true, data: profile('600519.SH'), requestId: null })
    await flush()

    expect(detail.profile.value?.industry).toBe('白酒Ⅱ')
    expect(detail.profileLoading.value).toBe(false)
    expect(detail.stockLoading.value).toBe(true)
    expect(detail.stockSeries.value).toBeNull()

    stock.resolve({ ok: true, data: series('600519.SH'), requestId: null })
    await load

    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')
    expect(detail.stockLoading.value).toBe(false)
  })

  it('publishes series while the industry request is still pending', async () => {
    const stock = deferred<ApiResult<ReviewStockSeries>>()
    const industry = deferred<ApiResult<StockProfile>>()
    const detail = useStockDetail(
      () => stock.promise,
      () => industry.promise,
    )

    const load = detail.load(row(), 60)
    stock.resolve({ ok: true, data: series('600519.SH'), requestId: null })
    await flush()

    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')
    expect(detail.stockLoading.value).toBe(false)
    expect(detail.profileLoading.value).toBe(true)
    expect(detail.profile.value).toBeNull()

    industry.resolve({ ok: true, data: profile('600519.SH'), requestId: null })
    await load

    expect(detail.profile.value?.industry).toBe('白酒Ⅱ')
    expect(detail.profileLoading.value).toBe(false)
  })

  it('does not let an old stock profile overwrite the latest selection', async () => {
    const first = deferred<ApiResult<StockProfile>>()
    const second = deferred<ApiResult<StockProfile>>()
    let call = 0
    const detail = useStockDetail(
      async (current) => ({
        ok: true,
        data: series(current.symbol),
        requestId: null,
      }),
      () => (++call === 1 ? first.promise : second.promise),
    )

    const oldLoad = detail.load(row('600519.SH'), 60)
    const latestLoad = detail.load(row('000001.SZ'), 60)
    second.resolve({ ok: true, data: profile('000001.SZ'), requestId: null })
    await latestLoad
    first.resolve({ ok: true, data: profile('600519.SH'), requestId: null })
    await oldLoad

    expect(detail.profile.value?.symbol).toBe('000001.SZ')
  })

  it('retries the industry request without clearing the loaded series', async () => {
    let profileCall = 0
    const detail = useStockDetail(
      async (current) => ({
        ok: true,
        data: series(current.symbol),
        requestId: null,
      }),
      async () => {
        profileCall += 1
        if (profileCall === 1) {
          return {
            ok: false,
            failure: {
              kind: 'network',
              code: null,
              status: null,
              message: '行业源不可用',
              requestId: 'req-industry',
              retryable: true,
              fields: [],
            },
          }
        }
        return { ok: true, data: profile('600519.SH'), requestId: null }
      },
    )

    await detail.load(row(), 60)
    expect(detail.profileFailure.value?.requestId).toBe('req-industry')
    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')

    detail.retryProfile()
    await flush()

    expect(detail.profile.value?.industry).toBe('白酒Ⅱ')
    expect(detail.profileFailure.value).toBeNull()
    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')
  })
})
