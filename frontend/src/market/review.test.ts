import { describe, expect, it } from 'vitest'

import type { LadderRead, ReviewHistoryRow } from './review'
import {
  buildCandleData,
  buildHeatmap,
  buildLadderGroups,
  chartNumber,
  compareClass,
  emotionRating,
  findPriceExtremes,
  formatSignedPercent,
  heatmapDatesNewestFirst,
  parseReviewWindow,
  previousHistory,
  routeDate,
  trendPeakIndexes,
} from './review'

function history(
  date: string,
  assessment: ReviewHistoryRow['assessment'],
  themes: Array<[string, number]>,
): ReviewHistoryRow {
  return {
    date,
    assessment,
    themes: themes.map(([theme, count]) => ({ theme, count })),
  }
}

const row = (symbol: string, boards: number | null, sector = '半导体') => ({
  symbol,
  name: symbol,
  sector,
  limit_up_time: '09:30:00',
  boards,
  boards_as_of_date: '2026-09-18',
  broken_kind: null,
  change_pct: null,
  one_word_board: null,
})

describe('review presentation model', () => {
  it('normalizes route date and supported windows', () => {
    expect(routeDate(['2026-09-18', '2026-09-17'])).toBe('2026-09-18')
    expect(routeDate('bad')).toBeNull()
    expect(routeDate('2026-02-30')).toBeNull()
    expect(parseReviewWindow('40')).toBe(40)
    expect(parseReviewWindow(41)).toBe(60)
  })

  it('formats market direction without treating invalid values as zero', () => {
    expect(compareClass('1.2')).toBe('up')
    expect(compareClass('-0.1')).toBe('down')
    expect(compareClass(null)).toBe('flat')
    expect(formatSignedPercent(null)).toBe('—')
    expect(formatSignedPercent('0')).toBe('0.00%')
    expect(chartNumber(null)).toBeNull()
    expect(chartNumber('0')).toBe(0)
  })

  it('finds the actual previous row in date order', () => {
    const rows = [history('2026-09-18', 'available', []), history('2026-09-17', 'available', [])]
    expect(previousHistory('2026-09-18', rows)?.date).toBe('2026-09-17')
  })

  it('groups current and broken rows by board height like the prototype', () => {
    const ladder = {
      connection: [row('A', 3)],
      first: [row('B', 1)],
      broken: [
        { ...row('C', 2), broken_kind: 'connection' as const },
        { ...row('D', 1), broken_kind: 'first' as const },
      ],
      unknown: [row('E', null)],
    } satisfies LadderRead
    const groups = buildLadderGroups(ladder)
    expect(groups.map((group) => group.key)).toEqual([
      'height-3',
      'height-2',
      'height-1',
      'unknown',
    ])
    expect(
      groups.find((group) => group.key === 'height-2')?.rows.map((item) => item.symbol),
    ).toEqual(['C'])
    expect(
      groups.find((group) => group.key === 'height-1')?.rows.map((item) => item.symbol),
    ).toEqual(['B', 'D'])
  })

  it('maps emotion scores to the prototype rating bands', () => {
    expect(emotionRating(90).label).toBe('亢奋')
    expect(emotionRating(72).label).toBe('活跃')
    expect(emotionRating(60).label).toBe('正常')
    expect(emotionRating(40).label).toBe('低迷')
    expect(emotionRating(10).label).toBe('冰点')
    expect(emotionRating(null).label).toBe('不可评估')
  })

  it('marks spaced local high-board peaks without crowding the chart', () => {
    const rows = [
      { ...history('2026-09-10', 'available', []), max_board: 2 },
      { ...history('2026-09-11', 'available', []), max_board: 5 },
      { ...history('2026-09-12', 'available', []), max_board: 3 },
      { ...history('2026-09-13', 'available', []), max_board: 4 },
      { ...history('2026-09-14', 'available', []), max_board: 3 },
      { ...history('2026-09-15', 'available', []), max_board: 2 },
      { ...history('2026-09-16', 'available', []), max_board: 3 },
    ]
    expect(trendPeakIndexes(rows)).toEqual([1, 6])
  })

  it('distinguishes missing days from true zero in the heatmap', () => {
    const model = buildHeatmap([
      history('2026-09-16', 'missing', []),
      history('2026-09-17', 'available', [['半导体', 2]]),
      history('2026-09-18', 'partial', [
        ['半导体', 1],
        ['未知', 1],
      ]),
    ])
    expect(model.cells.get('2026-09-16|半导体')?.count).toBeNull()
    expect(model.cells.get('2026-09-17|半导体')?.count).toBe(2)
    expect(model.themes.at(-1)).toBe('未知')
    expect(model.hasMissingDays).toBe(true)
  })

  it('keeps every heatmap theme instead of silently truncating the list', () => {
    const themes: Array<[string, number]> = Array.from({ length: 15 }, (_, index) => [
      `题材${index + 1}`,
      1,
    ])
    const model = buildHeatmap([history('2026-09-18', 'available', [...themes, ['未知', 2]])])
    expect(model.themes).toHaveLength(16)
    expect(model.themes.at(-1)).toBe('未知')
  })

  it('can keep only the most relevant themes while retaining unknown data', () => {
    const themes: Array<[string, number]> = Array.from({ length: 15 }, (_, index) => [
      `题材${index + 1}`,
      index + 1,
    ])
    const model = buildHeatmap(
      [history('2026-09-18', 'available', [...themes, ['未知', 2]])],
      30,
      8,
    )
    expect(model.themes).toHaveLength(8)
    expect(model.themes[0]).toBe('题材15')
    expect(model.themes.at(-1)).toBe('未知')
  })

  it('limits the heatmap to 30 trading days with the newest date first', () => {
    const rows = Array.from({ length: 35 }, (_, index) => {
      const date = new Date(Date.UTC(2026, 7, index + 1)).toISOString().slice(0, 10)
      return history(date, 'available', [['半导体', 1]])
    })
    const model = buildHeatmap(rows, 30, 8)
    const columns = heatmapDatesNewestFirst(model)
    expect(columns).toHaveLength(30)
    expect(columns[0]).toBe('2026-09-04')
    expect(columns.at(-1)).toBe('2026-08-06')
  })

  it('finds the visible highest and lowest index prices without inventing missing values', () => {
    const bars = [
      { date: '2026-09-16', open: '2', close: '2.6', high: '3.2', low: '1.4' },
      { date: '2026-09-17', open: null, close: null, high: '9.9', low: '0.1' },
      { date: '2026-09-18', open: '2.4', close: '2.2', high: '2.8', low: '1.2' },
    ] as const
    expect(findPriceExtremes([...bars])).toEqual([
      { index: 0, date: '2026-09-16', value: 3.2, kind: 'high' },
      { index: 2, date: '2026-09-18', value: 1.2, kind: 'low' },
    ])
  })

  it('keeps the candle axis position for days without complete OHLC', () => {
    const bars = [
      { date: '2026-09-16', open: '1', close: '2', low: '1', high: '3', ma5: '1.5', ma20: null },
      {
        date: '2026-09-17',
        open: null,
        close: '2.2',
        low: '2',
        high: '2.5',
        ma5: '1.7',
        ma20: null,
      },
      {
        date: '2026-09-18',
        open: '2.2',
        close: '2.4',
        low: '2.1',
        high: '2.6',
        ma5: '1.9',
        ma20: null,
      },
    ] as const
    expect(buildCandleData([...bars])).toEqual([[1, 2, 1, 3], null, [2.2, 2.4, 2.1, 2.6]])
  })

  it('does not draw omitted or non-finite OHLC from optional API fields', () => {
    expect(
      buildCandleData([
        { date: '2026-09-17', high: '3', low: '1', close: '2' },
        { date: '2026-09-18', open: 'NaN', high: '3', low: '1', close: '2' },
      ]),
    ).toEqual([null, null])
  })
})
