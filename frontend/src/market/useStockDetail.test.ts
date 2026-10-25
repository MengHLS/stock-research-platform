import { describe, expect, it } from 'vitest'

import type { ApiResult } from '../api/client'
import type { LimitUpReviewRow, ReviewStockSeries } from './review'
import type { ReviewStockFacts } from './stock-facts'
import { useStockDetail } from './useStockDetail'

function row(symbol = '600519.SH'): LimitUpReviewRow {
  return {
    date: '2026-10-20',
    symbol,
    name: '贵州茅台',
    board_category: 'main',
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

function facts(symbol: string, turnover = '4.12'): ReviewStockFacts {
  return {
    symbol,
    date: '2026-10-20',
    industry: {
      code: 'C39',
      name: '计算机、通信和其他电子设备制造业',
      source: 'baostock',
      effective_from: '2026-08-31',
      effective_to: null,
    },
    valuation: {
      date: '2026-10-20',
      turnover_pct: turnover,
      total_market_cap_cny: '120000000000.00',
      circulation_market_cap_cny: '95000000000.00',
      source: 'baostock-daily',
      unknown_fields: [],
    },
    trade: {
      date: '2026-10-20',
      volume_shares: '52345678.00',
      amount_cny: '612000500.00',
      source: 'tushare',
      unknown_fields: [],
    },
    issues: [],
    methodology: {},
  } as unknown as ReviewStockFacts
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
  it('publishes series and facts independently when one source is slower', async () => {
    const stock = deferred<ApiResult<ReviewStockSeries>>()
    const factsResult = deferred<ApiResult<ReviewStockFacts>>()
    const detail = useStockDetail(
      () => stock.promise,
      () => factsResult.promise,
    )

    const load = detail.load(row(), 60)
    factsResult.resolve({ ok: true, data: facts('600519.SH'), requestId: null })
    await flush()

    expect(detail.facts.value?.valuation.turnover_pct).toBe('4.12')
    expect(detail.factsLoading.value).toBe(false)
    expect(detail.stockLoading.value).toBe(true)
    expect(detail.stockSeries.value).toBeNull()

    stock.resolve({ ok: true, data: series('600519.SH'), requestId: null })
    await load

    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')
    expect(detail.stockLoading.value).toBe(false)
  })

  it('publishes series while the facts request is still pending', async () => {
    const stock = deferred<ApiResult<ReviewStockSeries>>()
    const factsResult = deferred<ApiResult<ReviewStockFacts>>()
    const detail = useStockDetail(
      () => stock.promise,
      () => factsResult.promise,
    )

    const load = detail.load(row(), 60)
    stock.resolve({ ok: true, data: series('600519.SH'), requestId: null })
    await flush()

    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')
    expect(detail.stockLoading.value).toBe(false)
    expect(detail.factsLoading.value).toBe(true)
    expect(detail.facts.value).toBeNull()

    factsResult.resolve({ ok: true, data: facts('600519.SH'), requestId: null })
    await load

    expect(detail.facts.value?.industry?.name).toBe('计算机、通信和其他电子设备制造业')
    expect(detail.factsLoading.value).toBe(false)
  })

  it('does not let old facts overwrite the latest selection', async () => {
    const first = deferred<ApiResult<ReviewStockFacts>>()
    const second = deferred<ApiResult<ReviewStockFacts>>()
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
    second.resolve({ ok: true, data: facts('000001.SZ', '0.65'), requestId: null })
    await latestLoad
    first.resolve({ ok: true, data: facts('600519.SH'), requestId: null })
    await oldLoad

    expect(detail.facts.value?.symbol).toBe('000001.SZ')
    expect(detail.facts.value?.valuation.turnover_pct).toBe('0.65')
  })

  it('ignores an older review day response for the same stock', async () => {
    const older = deferred<ApiResult<ReviewStockFacts>>()
    const newer = deferred<ApiResult<ReviewStockFacts>>()
    const signals: AbortSignal[] = []
    const detail = useStockDetail(
      async (current) => ({ ok: true, data: series(current.symbol), requestId: null }),
      (_symbol, day, signal) => {
        signals.push(signal)
        return day === '2026-10-19' ? older.promise : newer.promise
      },
    )
    const oldLoad = detail.load({ ...row(), date: '2026-10-19' }, 60)
    const newLoad = detail.load(row(), 60)
    newer.resolve({ ok: true, data: facts('600519.SH', '8.00'), requestId: null })
    await newLoad
    older.resolve({ ok: true, data: facts('600519.SH', '1.00'), requestId: null })
    await oldLoad
    expect(signals[0]?.aborted).toBe(true)
    expect(detail.facts.value?.valuation.turnover_pct).toBe('8.00')
  })

  it('does not publish responses after the detail is cleared on unmount', async () => {
    const pending = deferred<ApiResult<ReviewStockFacts>>()
    const detail = useStockDetail(
      async (current) => ({ ok: true, data: series(current.symbol), requestId: null }),
      () => pending.promise,
    )
    const load = detail.load(row(), 60)
    detail.clear()
    pending.resolve({ ok: true, data: facts('600519.SH'), requestId: null })
    await load
    expect(detail.facts.value).toBeNull()
    expect(detail.stockSeries.value).toBeNull()
    expect(detail.factsLoading.value).toBe(false)
  })

  it('requests facts for the selected review day, not the latest day', async () => {
    const requested: Array<[string, string]> = []
    const detail = useStockDetail(
      async (current) => ({
        ok: true,
        data: series(current.symbol),
        requestId: null,
      }),
      async (symbol, tradingDay) => {
        requested.push([symbol, tradingDay])
        return { ok: true, data: facts(symbol), requestId: null }
      },
    )

    await detail.load(row(), 60)

    expect(requested).toEqual([['600519.SH', '2026-10-20']])
  })

  it('retries the facts request without clearing the loaded series', async () => {
    let factsCall = 0
    const detail = useStockDetail(
      async (current) => ({
        ok: true,
        data: series(current.symbol),
        requestId: null,
      }),
      async () => {
        factsCall += 1
        if (factsCall === 1) {
          return {
            ok: false,
            failure: {
              kind: 'network',
              code: null,
              status: null,
              message: '复盘数据库不可用',
              requestId: 'req-facts',
              retryable: true,
              fields: [],
            },
          }
        }
        return { ok: true, data: facts('600519.SH'), requestId: null }
      },
    )

    await detail.load(row(), 60)
    expect(detail.factsFailure.value?.requestId).toBe('req-facts')
    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')

    detail.retryFacts()
    await flush()

    expect(detail.facts.value?.industry?.code).toBe('C39')
    expect(detail.factsFailure.value).toBeNull()
    expect(detail.stockSeries.value?.symbol).toBe('600519.SH')
  })
})
