import { describe, expect, it } from 'vitest'

import {
  canonicalWatchCodes,
  continuousIntradaySegments,
  exchangeLabel,
  formatAmount,
  formatShanghaiDate,
  formatShanghaiTime,
  formatShares,
  INTRADAY_CONTINUOUS_SLOTS,
  INTRADAY_TIME_TICKS,
  intradaySummary,
  intradaySlotIndex,
  latestTradingDayBars,
  marketPhaseLabel,
  mergeWatchlist,
  normalizeTicker,
  parseTickerInput,
  percentDistance,
  positivePrice,
  readStoredWatchlist,
  symmetricIntradayRange,
  watchlistStorageKey,
  type IntradayBar,
  type IntradayQuote,
} from './intraday'

const quote: IntradayQuote = {
  symbol: '600519.SH',
  name: '贵州茅台',
  price: '10.00',
  previous_close: '9.50',
  open: '9.80',
  high: '11.00',
  low: '9.00',
  quote_time: '2026-10-20T02:15:30Z',
  change_pct: '5.26',
  volume_lots: '1200',
  amount: '123456789',
  turnover_pct: '1.20',
  limit_up: '10.45',
  limit_down: '8.55',
  volume_note: 'test note',
  phase: 'continuous',
}

function bar(start: string, volume: string): IntradayBar {
  return {
    start,
    trading_day: '2026-10-20',
    open: '9.90',
    high: '10.10',
    low: '9.80',
    close: '10.00',
    volume_shares: volume,
  }
}

describe('intraday ticker input', () => {
  it('separates valid, duplicate and invalid tokens without silently dropping errors', () => {
    expect(
      parseTickerInput('600519, 000001 600519 603618；920982 abc 1234567 000001.SZ sh600519'),
    ).toEqual({
      valid: ['600519.SH', '000001.SZ', '603618.SH', '920982.BJ'],
      invalid: ['abc', '1234567'],
      duplicates: ['600519', '000001.SZ', 'sh600519'],
    })
  })

  it('enforces the watch limit and keeps existing order', () => {
    expect(mergeWatchlist(['600519', '000001'], ['000001', '603618', '920982'], 3)).toEqual({
      codes: ['600519', '000001', '603618'],
      added: ['603618'],
      duplicates: ['000001'],
      overflow: ['920982'],
    })
  })

  it('collapses equivalent ticker forms before storing or requesting them', () => {
    const result = canonicalWatchCodes(['600519', '600519.SH', '000001', '000001.SZ'])
    expect(result.codes).toEqual(['600519.SH', '000001.SZ'])
    expect(result.aliases.get('600519')).toBe('600519.SH')
  })

  it('reads canonical symbols and ignores malformed browser storage', () => {
    expect(normalizeTicker('600519.SH')).toBe('600519.SH')
    expect(normalizeTicker(['000001'])).toBe('000001.SZ')
    expect(normalizeTicker('000001')).toBe('000001.SZ')
    expect(normalizeTicker('sh000001')).toBe('000001.SH')
    expect(normalizeTicker('sh600519')).toBe('600519.SH')
    expect(normalizeTicker('sh600519')).toBe('600519.SH')
    expect(normalizeTicker('000001.sz')).toBe('000001.SZ')
    expect(readStoredWatchlist('["600519.SH","600519","bad","920982"]')).toEqual([
      '600519.SH',
      '920982.BJ',
    ])
    expect(readStoredWatchlist('{broken')).toEqual([])
    expect(watchlistStorageKey(7)).toBe('rp.intraday.watchlist.v1:7')
  })
})

describe('intraday presentation helpers', () => {
  it('uses exchange suffix, session phase and Beijing time without UTC date drift', () => {
    expect(exchangeLabel('600519.SH')).toBe('上交所')
    expect(exchangeLabel('000001.SZ')).toBe('深交所')
    expect(exchangeLabel('920982.BJ')).toBe('北交所')
    expect(marketPhaseLabel('opening_auction')).toBe('集合竞价')
    expect(marketPhaseLabel('lunch_break')).toBe('午间休市')
    expect(formatShanghaiDate('2026-10-19T16:30:00Z')).toMatch(/2026.*10.*20/)
    expect(formatShanghaiTime('2026-10-19T16:30:00Z')).toMatch(/00:30:00/)
  })

  it('formats amounts, shares and signed distances without treating missing as zero', () => {
    expect(formatAmount('123456789')).toBe('1.23 亿')
    expect(formatAmount(null)).toBe('—')
    expect(formatShares('12000')).toBe('1.20 万股')
    expect(formatShares(undefined)).toBe('—')
    expect(percentDistance('105', '100')).toBeCloseTo(5, 10)
    expect(percentDistance(null, '100')).toBeNull()
  })

  it('summarizes only values backed by quote and minute bars', () => {
    const summary = intradaySummary(quote, [
      bar('2026-10-20T01:30:00Z', '100'),
      bar('2026-10-20T01:31:00Z', '200'),
    ])
    expect(summary.barCount).toBe(2)
    expect(summary.latestBarTime).toBe('2026-10-20T01:31:00Z')
    expect(summary.barTradingDay).toBe('2026-10-20')
    expect(summary.intradayVolumeShares).toBe(300)
    expect(summary.positionPct).toBe(50)
    expect(summary.openGapPct).toBeCloseTo(3.1579, 3)
    expect(summary.drawdownFromHighPct).toBeCloseTo(-9.0909, 3)
  })

  it('keeps only the latest trading day and sorts provider rows by time', () => {
    const previous = {
      ...bar('2026-10-19T05:02:00Z', '50'),
      trading_day: '2026-10-19',
    }
    const todayLate = bar('2026-10-20T03:30:00Z', '200')
    const todayEarly = bar('2026-10-20T01:30:00Z', '100')
    expect(
      latestTradingDayBars([previous, todayLate, todayEarly]).map((item) => item.start),
    ).toEqual(['2026-10-20T01:30:00Z', '2026-10-20T03:30:00Z'])
  })

  it('places bars on a fixed 240-slot continuous-session axis', () => {
    expect(INTRADAY_CONTINUOUS_SLOTS).toBe(240)
    expect(intradaySlotIndex('2026-10-20T01:31:00Z')).toBe(0)
    expect(intradaySlotIndex('2026-10-20T03:30:00Z')).toBe(119)
    expect(intradaySlotIndex('2026-10-20T05:01:00Z')).toBe(120)
    expect(intradaySlotIndex('2026-10-20T07:00:00Z')).toBe(239)
    expect(intradaySlotIndex('2026-10-20T01:30:00Z')).toBeNull()
    expect(intradaySlotIndex('2026-10-20T03:31:00Z')).toBeNull()
    expect(intradaySlotIndex('2026-10-20T05:00:00Z')).toBeNull()
  })

  it('keeps every time label aligned with the fixed-slot mapping', () => {
    const samples = [
      '2026-10-20T01:31:00Z',
      '2026-10-20T02:30:00Z',
      '2026-10-20T03:30:00Z',
      '2026-10-20T05:30:00Z',
      '2026-10-20T07:00:00Z',
    ]
    expect(INTRADAY_TIME_TICKS.map((tick) => tick.slot)).toEqual(
      samples.map((sample) => intradaySlotIndex(sample)),
    )
    expect(INTRADAY_TIME_TICKS.find((tick) => tick.label === '13:30')?.slot).toBe(149)
  })

  it('centers the price axis on previous close with equal upside and downside bounds', () => {
    const axis = symmetricIntradayRange('100', ['101', '103', '99'])
    expect(axis?.center).toBe(100)
    expect(axis?.boundPct).toBeCloseTo(0.0324, 6)
    expect((axis!.top / 100 - 1) * 100).toBeCloseTo((1 - axis!.bottom / 100) * 100, 10)
    expect(symmetricIntradayRange(null, ['100'])).toBeNull()
  })

  it('accepts only finite positive prices for drawing and percentage calculations', () => {
    expect(positivePrice('10.50')).toBe(10.5)
    expect(positivePrice(0)).toBeNull()
    expect(positivePrice('-1')).toBeNull()
    expect(positivePrice(null)).toBeNull()
    const axis = symmetricIntradayRange('100', ['0', '-1', '101'])
    expect(axis?.center).toBe(100)
    expect(axis?.boundPct).toBeCloseTo(0.0108, 10)
  })

  it('breaks price lines at missing or invalid minutes but not at lunch', () => {
    const segments = continuousIntradaySegments([
      { ...bar('2026-10-20T01:31:00Z', '100'), close: '10.00' },
      { ...bar('2026-10-20T01:32:00Z', '100'), close: '' },
      { ...bar('2026-10-20T01:33:00Z', '100'), close: '10.01' },
      { ...bar('2026-10-20T03:30:00Z', '100'), close: '10.02' },
      { ...bar('2026-10-20T05:01:00Z', '100'), close: '10.03' },
      { ...bar('2026-10-20T05:02:00Z', '100'), close: '0' },
      { ...bar('2026-10-20T05:03:00Z', '100'), close: '10.04' },
    ])

    expect(segments.map((segment) => segment.map((point) => point.slot))).toEqual([
      [0],
      [2],
      [119, 120],
      [122],
    ])
  })

  it('keeps position unknown when the day has no usable high-low span', () => {
    const flat = { ...quote, high: null, low: null }
    expect(intradaySummary(flat, []).positionPct).toBeNull()
    expect(intradaySummary(flat, []).intradayVolumeShares).toBeNull()
  })
})
