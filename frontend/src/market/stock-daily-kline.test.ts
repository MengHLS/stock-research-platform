import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import StockDailyKline from '../components/market/StockDailyKline.vue'
import type { ReviewStockSeries } from './review'

function series(overrides: Partial<ReviewStockSeries> = {}): ReviewStockSeries {
  return {
    symbol: '002889.SZ',
    window_requested: 3,
    window_actual: 3,
    coverage: { status: 'available', row_count: 3, completeness: 'presence_only' },
    missing_days: 0,
    volume_missing_days: 0,
    bars: [
      {
        date: '2026-10-16',
        open: '10.00',
        high: '10.40',
        low: '9.90',
        close: '10.30',
        change_pct: '3.00',
        ma5: null,
        ma20: null,
        volume_shares: '5200000.00',
        amount_cny: '53000000.00',
      },
      {
        date: '2026-10-19',
        open: '10.30',
        high: '10.60',
        low: '10.20',
        close: '10.10',
        change_pct: '-1.94',
        ma5: null,
        ma20: null,
        volume_shares: '4100000.00',
        amount_cny: '42000000.00',
      },
      {
        date: '2026-10-20',
        open: '10.10',
        high: '10.50',
        low: '10.00',
        close: '10.45',
        change_pct: '3.47',
        ma5: null,
        ma20: null,
        volume_shares: null,
        amount_cny: null,
      },
    ],
    issues: [],
    methodology: {},
    ...overrides,
  } as unknown as ReviewStockSeries
}

describe('stock daily kline volume', () => {
  it('draws one volume bar per known day and keeps unknown days blank', async () => {
    const html = await renderToString(
      createSSRApp(StockDailyKline, {
        series: series({ volume_missing_days: 1 }),
        selectedDate: '2026-10-19',
      }),
    )

    expect(html.match(/class="(?:candle-up|candle-down|volume-flat) volume-bar"/g)).toHaveLength(2)
    expect(html.match(/class="candle-(?:up|down) body"/g)).toHaveLength(3)
    expect(html).toContain('量柱缺失 1 日')
    expect(html).toContain('成交量按手展示')
    expect(html).toContain('5.20 万手')
    expect(html).toContain('MA20 与成交量')
  })

  it('keeps real zero volume distinct from unknown volume', async () => {
    const bars = series().bars.map((bar) => ({ ...bar, volume_shares: '0' }))
    const html = await renderToString(
      createSSRApp(StockDailyKline, {
        series: series({ bars }),
        selectedDate: '2026-10-20',
      }),
    )
    expect(html).toContain('0.00 手')
    expect(html).not.toContain('成交量未知')
    expect(html).not.toContain('volume-bar')
  })

  it('keeps known volume when price data is missing using a neutral color', async () => {
    const bars = series().bars.map((bar) => ({ ...bar, open: null }))
    const html = await renderToString(
      createSSRApp(StockDailyKline, {
        series: series({ bars, missing_days: 3 }),
        selectedDate: '2026-10-20',
      }),
    )
    expect(html.match(/class="volume-flat volume-bar"/g)).toHaveLength(2)
    expect(html).not.toContain('class="candle-up body"')
  })

  it('reports an unknown volume axis instead of a fake zero when all bars lack volume', async () => {
    const blank = series({ volume_missing_days: 3 }).bars.map((bar) => ({
      ...bar,
      volume_shares: null,
      amount_cny: null,
    }))
    const html = await renderToString(
      createSSRApp(StockDailyKline, {
        series: series({ volume_missing_days: 3, bars: blank }),
        selectedDate: '2026-10-20',
      }),
    )

    expect(html).not.toContain('volume-bar')
    expect(html).toContain('成交量未知')
    expect(html.match(/class="candle-(?:up|down) body"/g)).toHaveLength(3)
  })
})
