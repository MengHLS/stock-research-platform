import { describe, expect, it } from 'vitest'

import type { LimitUpReviewDay, LimitUpReviewRow, ReviewDate } from './review'
import {
  buildLimitUpCsv,
  buildMonthCalendar,
  clampMonth,
  defaultLimitUpFilters,
  filterLimitUpRows,
  limitUpEmptyTitle,
  limitUpSealLabel,
  limitUpSectorOptions,
  limitUpStatusLabel,
  paginateRows,
  shiftMonth,
  sortLimitUpRows,
} from './limit-up'

function row(
  overrides: Partial<LimitUpReviewRow> & Pick<LimitUpReviewRow, 'date' | 'symbol'>,
): LimitUpReviewRow {
  return {
    name: overrides.symbol,
    sector: '半导体',
    status: 'limit_up',
    boards: 1,
    boards_as_of_date: overrides.date,
    limit_up_time: '09:35:00',
    limit_up_time_as_of_date: overrides.date,
    broken_kind: null,
    change_pct: '10.00',
    one_word_board: false,
    ...overrides,
  }
}

function reviewDate(day: string, count: number): ReviewDate {
  return {
    date: day,
    limit_up: { status: 'available', row_count: count, completeness: 'presence_only' },
    market_wide: { status: 'available', row_count: 1, completeness: 'presence_only' },
    indices: {
      shanghai: { status: 'available', row_count: 1, completeness: 'presence_only' },
      shenzhen: { status: 'available', row_count: 1, completeness: 'presence_only' },
      csi300: { status: 'available', row_count: 1, completeness: 'presence_only' },
      csi500: { status: 'available', row_count: 1, completeness: 'presence_only' },
    },
  }
}

const rows = [
  row({ date: '2026-09-17', symbol: '000001.SZ', name: '甲', boards: 2 }),
  row({
    date: '2026-09-18',
    symbol: '000001.SZ',
    name: '甲',
    boards: 3,
    one_word_board: true,
  }),
  row({
    date: '2026-09-18',
    symbol: '000002.SZ',
    name: '乙',
    sector: '机器人',
    boards: 1,
  }),
  row({
    date: '2026-09-18',
    symbol: '000003.SZ',
    name: '丙',
    sector: '未知',
    status: 'broken',
    boards: 4,
    broken_kind: 'connection',
    boards_as_of_date: '2026-09-17',
    change_pct: '-4.20',
  }),
  row({
    date: '2026-09-18',
    symbol: '000004.SZ',
    name: '丁',
    sector: '机器人',
    boards: null,
    boards_as_of_date: '2026-09-17',
  }),
]

describe('limit-up presentation model', () => {
  it('distinguishes unknown broken counts from filtered results and confirmed zero', () => {
    const day: LimitUpReviewDay = {
      date: '2026-09-18',
      assessment: 'partial',
      broken_count: null,
      limit_up: { status: 'available', row_count: 3, completeness: 'presence_only' },
    }
    const filters = { ...defaultLimitUpFilters(), status: 'broken' as const }
    expect(limitUpEmptyTitle(day, filters)).toBe('当日断板状态无法确认')
    expect(limitUpEmptyTitle({ ...day, broken_count: 0 }, filters)).toBe('当日没有断板记录')
    expect(limitUpEmptyTitle({ ...day, broken_count: 2 }, { ...filters, query: '无匹配' })).toBe(
      '没有符合筛选条件的断板记录',
    )
    expect(limitUpEmptyTitle({ ...day, broken_count: 0 }, { ...filters, tier: 'high' })).toBe(
      '没有符合筛选条件的断板记录',
    )
  })

  it('shows only the selected day and hides broken rows by default', () => {
    const filters = defaultLimitUpFilters()
    const current = filterLimitUpRows(rows, '2026-09-18', filters)
    expect(current).toHaveLength(3)
    expect(current.every((item) => item.status === 'limit_up')).toBe(true)
    expect(current.every((item) => item.date === '2026-09-18')).toBe(true)
    expect(
      filterLimitUpRows(rows, '2026-09-18', {
        ...filters,
        status: 'broken',
      }).map((item) => item.symbol),
    ).toEqual(['000003.SZ'])
  })

  it('combines tier, status, sector and text filters without inventing board counts', () => {
    const filtered = filterLimitUpRows(rows, '2026-09-18', {
      query: '丙',
      tier: 'high',
      status: 'broken',
      sector: '未知',
    })
    expect(filtered.map((item) => item.symbol)).toEqual(['000003.SZ'])
    expect(
      filterLimitUpRows(rows, '2026-09-18', {
        ...defaultLimitUpFilters(),
        tier: 'connection',
        status: 'all',
      }).map((item) => item.symbol),
    ).toEqual(['000001.SZ', '000003.SZ'])
  })

  it('keeps the unknown sector while limiting the quick filters', () => {
    const options = limitUpSectorOptions(
      [
        ...rows,
        row({
          date: '2026-09-18',
          symbol: '000005.SZ',
          sector: '未知',
        }),
      ],
      '2026-09-18',
      2,
    )
    expect(options).toHaveLength(2)
    expect(options.at(-1)).toBe('未知')
  })

  it('keeps a known seal time when the one-word flag is unknown', () => {
    const unknownFlag = row({
      date: '2026-09-18',
      symbol: '000001.SZ',
      limit_up_time: '10:05:00',
      one_word_board: null,
    })
    expect(limitUpSealLabel(unknownFlag)).toBe('10:05:00 · 一字未知')
  })

  it('sorts nullable values last and breaks date ties by board height', () => {
    const sorted = sortLimitUpRows(rows, { key: 'boards', direction: 'desc' })
    expect(sorted.at(-1)?.symbol).toBe('000004.SZ')
    const dated = sortLimitUpRows(rows, { key: 'date', direction: 'desc' })
    expect(dated[0]?.date).toBe('2026-09-18')
    expect(dated[0]?.boards).toBe(4)
  })

  it('does not call an unknown broken chain a first-board failure', () => {
    const unknownBroken = row({
      date: '2026-09-18',
      symbol: '000005.SZ',
      status: 'broken',
      boards: null,
      broken_kind: null,
      one_word_board: true,
      limit_up_time_as_of_date: '2026-09-17',
    })
    expect(limitUpStatusLabel(unknownBroken)).toBe('断板 · 板数未知')
    expect(limitUpSealLabel(unknownBroken)).toBe('09:35:00 · 前日')
  })

  it('distinguishes missing coverage from a displayed count in the month calendar', () => {
    const dates: ReviewDate[] = [
      {
        date: '2026-09-17',
        limit_up: { status: 'missing', row_count: 0, completeness: 'presence_only' },
        market_wide: { status: 'available', row_count: 1, completeness: 'presence_only' },
        indices: {
          shanghai: { status: 'available', row_count: 1, completeness: 'presence_only' },
          shenzhen: { status: 'available', row_count: 1, completeness: 'presence_only' },
          csi300: { status: 'available', row_count: 1, completeness: 'presence_only' },
          csi500: { status: 'available', row_count: 1, completeness: 'presence_only' },
        },
      },
      {
        date: '2026-09-18',
        limit_up: { status: 'available', row_count: 3, completeness: 'presence_only' },
        market_wide: { status: 'available', row_count: 1, completeness: 'presence_only' },
        indices: {
          shanghai: { status: 'available', row_count: 1, completeness: 'presence_only' },
          shenzhen: { status: 'available', row_count: 1, completeness: 'presence_only' },
          csi300: { status: 'available', row_count: 1, completeness: 'presence_only' },
          csi500: { status: 'available', row_count: 1, completeness: 'presence_only' },
        },
      },
    ]
    const calendar = buildMonthCalendar('2026-09', dates)
    const missing = calendar.cells.find((cell) => cell?.date === '2026-09-17')
    const available = calendar.cells.find((cell) => cell?.date === '2026-09-18')
    expect(missing?.count).toBeNull()
    expect(missing?.available).toBe(false)
    expect(available?.count).toBe(3)
    expect(calendar.tradingDays).toBe(2)
    expect(calendar.knownDays).toBe(1)
    expect(calendar.total).toBe(3)
    expect(calendar.peakDate).toBe('2026-09-18')
    expect(calendar.activityDays).toEqual([{ date: '2026-09-18', count: 3 }])
  })

  it('ranks calendar activity by count and then by most recent date', () => {
    const calendar = buildMonthCalendar('2026-09', [
      reviewDate('2026-09-02', 4),
      reviewDate('2026-09-01', 7),
      reviewDate('2026-09-03', 7),
    ])
    expect(calendar.activityDays).toEqual([
      { date: '2026-09-03', count: 7 },
      { date: '2026-09-01', count: 7 },
      { date: '2026-09-02', count: 4 },
    ])
  })

  it('shifts and clamps months by calendar bounds', () => {
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(clampMonth('2025-12', '2026-01-03', '2026-09-18')).toBe('2026-01')
    expect(clampMonth('2026-10', '2026-01-03', '2026-09-18')).toBe('2026-09')
  })

  it('paginates the filtered result deterministically', () => {
    expect(paginateRows(rows, 2, 2)).toMatchObject({
      total: 5,
      page: 2,
      pageCount: 3,
      start: 3,
      end: 4,
    })
    expect(paginateRows([], 4, 100)).toMatchObject({ page: 1, pageCount: 1, start: 0, end: 0 })
  })

  it('exports the visible data vocabulary without mock seal or turnover columns', () => {
    const csv = buildLimitUpCsv([rows[2]!])
    expect(csv.split('\r\n')[0]).toContain('"板数截至"')
    expect(csv.split('\r\n')[0]).toContain('"封板时间截至"')
    expect(csv).not.toContain('封单')
    expect(csv).not.toContain('换手')
    expect(csv).toContain('"机器人"')
    const brokenCsv = buildLimitUpCsv([rows[3]!])
    expect(brokenCsv).toContain('· 前日')
    expect(brokenCsv).toContain('不适用（断板）')
  })
})
