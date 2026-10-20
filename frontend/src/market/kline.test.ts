import { describe, expect, it } from 'vitest'

import { klineChartBars, klineLabel, type MarketKlineSeries } from './kline'

function series(): MarketKlineSeries {
  return {
    symbol: '600519.SH',
    period: 'day',
    provider: 'tencent',
    adjustment: 'none',
    week_in_progress: false,
    total: 25,
    limits: [],
    bars: Array.from({ length: 25 }, (_, index) => ({
      trading_day: `2026-09-${String(index + 1).padStart(2, '0')}`,
      open: String(100 + index),
      high: String(102 + index),
      low: String(99 + index),
      close: String(101 + index),
      volume_shares: '1000',
    })),
  }
}

describe('market kline presentation', () => {
  it('computes MA5 and MA20 from the supplied period bars', () => {
    const bars = klineChartBars(series())

    expect(bars).toHaveLength(25)
    expect(bars[3]?.ma5).toBeNull()
    expect(bars[4]?.ma5).toBe('103.000')
    expect(bars[18]?.ma20).toBeNull()
    expect(bars[19]?.ma20).toBe('110.500')
  })

  it('labels daily and weekly periods explicitly', () => {
    expect(klineLabel('day')).toBe('日 K')
    expect(klineLabel('week')).toBe('周 K')
  })
})
