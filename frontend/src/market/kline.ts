import type { components } from '../api/schema'

export type MarketKlineSeries = components['schemas']['MarketKlineSeriesRead']
export type MarketKlineBar = components['schemas']['MarketKlineBarRead']
export type MarketKlinePeriod = MarketKlineSeries['period']

export interface KlineChartBar {
  date: string
  open?: string | null
  high?: string | null
  low?: string | null
  close?: string | null
  ma5?: string | null
  ma20?: string | null
  volume_source?: string | null
}

function movingAverage(bars: readonly MarketKlineBar[], index: number, window: number) {
  if (index + 1 < window) return null
  const closes = bars
    .slice(index + 1 - window, index + 1)
    .map((bar) => Number(bar.close))
    .filter(Number.isFinite)
  if (closes.length !== window) return null
  return (closes.reduce((sum, value) => sum + value, 0) / window).toFixed(3)
}

export function klineChartBars(series: MarketKlineSeries | null): KlineChartBar[] {
  if (!series) return []
  return series.bars.map((bar, index) => ({
    date: bar.trading_day,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    ma5: movingAverage(series.bars, index, 5),
    ma20: movingAverage(series.bars, index, 20),
    volume_source: bar.volume_shares,
  }))
}

export function klineLabel(period: MarketKlinePeriod): string {
  return period === 'week' ? '周 K' : '日 K'
}
