import type { LimitUpReviewDay, LimitUpReviewRow, ReviewDate } from './review'

export type LimitUpTier = 'all' | 'first' | 'connection' | 'high'
export type LimitUpStatusFilter = 'limit_up' | 'broken' | 'all'
export type LimitUpSortKey =
  'date' | 'symbol' | 'name' | 'sector' | 'boards' | 'limit_up_time' | 'change_pct' | 'status'

export interface LimitUpFilters {
  query: string
  tier: LimitUpTier
  status: LimitUpStatusFilter
  sector: string | null
}

export interface LimitUpSort {
  key: LimitUpSortKey
  direction: 'asc' | 'desc'
}

export interface CalendarCell {
  day: number
  date: string | null
  count: number | null
  downCount: number | null
  available: boolean
  weekend: boolean
}

export interface MonthCalendarModel {
  month: string
  cells: Array<CalendarCell | null>
  tradingDays: number
  knownDays: number
  total: number
  downKnownDays: number
  downTotal: number
  average: number | null
  peakDate: string | null
  peak: number | null
  activityDays: CalendarActivityDay[]
}

export interface CalendarActivityDay {
  date: string
  count: number
}

export interface PageSlice<T> {
  items: T[]
  total: number
  page: number
  pageCount: number
  start: number
  end: number
}

const EMPTY_FILTERS: LimitUpFilters = {
  query: '',
  tier: 'all',
  status: 'limit_up',
  sector: null,
}

export function defaultLimitUpFilters(): LimitUpFilters {
  return { ...EMPTY_FILTERS }
}

export function limitUpEmptyTitle(day: LimitUpReviewDay | null, filters: LimitUpFilters): string {
  if (day?.assessment === 'missing') return '该日涨停记录缺失'
  if (filters.status !== 'broken') return '没有符合条件的记录'
  if (!day || day.broken_count === null || day.broken_count === undefined) {
    return '当日断板状态无法确认'
  }
  if (filters.query.trim() || filters.tier !== 'all' || filters.sector !== null) {
    return '没有符合筛选条件的断板记录'
  }
  return day.broken_count === 0 ? '当日没有断板记录' : '没有符合筛选条件的断板记录'
}

export function filterLimitUpRows(
  rows: LimitUpReviewRow[],
  selectedDate: string,
  filters: LimitUpFilters,
): LimitUpReviewRow[] {
  const query = filters.query.trim().toLowerCase()
  return rows.filter((row) => {
    if (row.date !== selectedDate) return false
    if (filters.status !== 'all' && row.status !== filters.status) return false
    if (filters.sector && row.sector !== filters.sector) return false
    if (filters.tier === 'first' && row.boards !== 1) return false
    if (filters.tier === 'connection' && (row.boards === null || row.boards < 2)) return false
    if (filters.tier === 'high' && (row.boards === null || row.boards < 4)) return false
    if (!query) return true
    return `${row.symbol} ${row.name} ${row.sector}`.toLowerCase().includes(query)
  })
}

export function limitUpSectorOptions(
  rows: LimitUpReviewRow[],
  selectedDate: string,
  limit = 8,
): string[] {
  const inScope = rows.filter((row) => row.date === selectedDate)
  const counts = new Map<string, number>()
  const latestCounts = new Map<string, number>()
  for (const row of inScope) {
    counts.set(row.sector, (counts.get(row.sector) ?? 0) + 1)
    latestCounts.set(row.sector, (latestCounts.get(row.sector) ?? 0) + 1)
  }
  const ranked = [...counts.keys()].sort((left, right) => {
    if (left === '未知') return 1
    if (right === '未知') return -1
    return (
      (latestCounts.get(right) ?? 0) - (latestCounts.get(left) ?? 0) ||
      (counts.get(right) ?? 0) - (counts.get(left) ?? 0) ||
      left.localeCompare(right, 'zh-CN')
    )
  })
  const hasUnknown = ranked.includes('未知')
  const knownLimit = Math.max(0, limit - (hasUnknown ? 1 : 0))
  return [
    ...ranked.filter((sector) => sector !== '未知').slice(0, knownLimit),
    ...(hasUnknown && limit > 0 ? ['未知'] : []),
  ]
}

export function sortLimitUpRows(rows: LimitUpReviewRow[], sort: LimitUpSort): LimitUpReviewRow[] {
  return [...rows].sort((left, right) => {
    const leftValue = sortValue(left, sort.key)
    const rightValue = sortValue(right, sort.key)
    if (leftValue === null || rightValue === null) {
      if (leftValue === rightValue) return tieBreak(left, right, sort.key)
      return leftValue === null ? 1 : -1
    }
    const compared =
      typeof leftValue === 'number' && typeof rightValue === 'number'
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue), 'zh-CN')
    if (compared !== 0) return compared * (sort.direction === 'asc' ? 1 : -1)
    return tieBreak(left, right, sort.key)
  })
}

function sortValue(row: LimitUpReviewRow, key: LimitUpSortKey): string | number | null {
  if (key === 'boards') return row.boards
  if (key === 'change_pct') return numberOrNull(row.change_pct)
  if (key === 'limit_up_time') return row.limit_up_time || null
  if (key === 'date') return row.date
  if (key === 'status') return row.status
  return row[key]
}

function tieBreak(left: LimitUpReviewRow, right: LimitUpReviewRow, key: LimitUpSortKey): number {
  if (key !== 'date' && left.date !== right.date) {
    return right.date.localeCompare(left.date)
  }
  if (key !== 'boards' && left.boards !== right.boards) {
    if (left.boards === null) return 1
    if (right.boards === null) return -1
    return right.boards - left.boards
  }
  return left.symbol.localeCompare(right.symbol)
}

function numberOrNull(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function buildMonthCalendar(month: string, dates: ReviewDate[]): MonthCalendarModel {
  const [year, monthNumber] = month.split('-').map(Number)
  if (!year || !monthNumber) {
    return {
      month,
      cells: [],
      tradingDays: 0,
      knownDays: 0,
      total: 0,
      downKnownDays: 0,
      downTotal: 0,
      average: null,
      peakDate: null,
      peak: null,
      activityDays: [],
    }
  }
  const daysInMonth = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate()
  const firstWeekday = (new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay() + 6) % 7
  const byDate = new Map(
    dates.filter((item) => item.date.startsWith(`${month}-`)).map((item) => [item.date, item]),
  )
  const cells: Array<CalendarCell | null> = Array.from({ length: firstWeekday }, () => null)
  const monthDates = [...byDate.values()].sort((left, right) => left.date.localeCompare(right.date))
  const upCounts = monthDates.map(displayedLimitUpCount)
  const downCounts = monthDates.map(displayedLimitDownCount)
  const counts = upCounts.filter((count): count is number => count !== null)
  const knownDown = downCounts.filter((count): count is number => count !== null)
  const total = counts.reduce((sum, count) => sum + count, 0)
  const downTotal = knownDown.reduce((sum, count) => sum + count, 0)
  const peak = counts.length ? Math.max(...counts) : null
  const peakDate =
    peak === null ? null : (monthDates.find((_, index) => upCounts[index] === peak)?.date ?? null)
  const activityDays = monthDates
    .map((item, index) => ({ date: item.date, count: upCounts[index] }))
    .filter(
      (item): item is { date: string; count: number } => item.count !== null && item.count > 0,
    )
    .sort((left, right) => right.count - left.count || right.date.localeCompare(left.date))

  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = `${month}-${String(day).padStart(2, '0')}`
    const source = byDate.get(date)
    const weekday = (new Date(Date.UTC(year, monthNumber - 1, day)).getUTCDay() + 6) % 7
    const count = source ? displayedLimitUpCount(source) : null
    const downCount = source ? displayedLimitDownCount(source) : null
    cells.push({
      day,
      date: source?.date ?? null,
      count,
      downCount,
      available: count !== null,
      weekend: weekday >= 5,
    })
  }
  return {
    month,
    cells,
    tradingDays: monthDates.length,
    knownDays: counts.length,
    total,
    downKnownDays: knownDown.length,
    downTotal,
    average: counts.length ? total / counts.length : null,
    peakDate,
    peak,
    activityDays,
  }
}

function displayedLimitUpCount(item: ReviewDate): number | null {
  return item.market_state_counts?.status === 'available'
    ? (item.limit_up_close_count ?? null)
    : null
}

function displayedLimitDownCount(item: ReviewDate): number | null {
  return item.market_state_counts?.status === 'available'
    ? (item.limit_down_close_count ?? null)
    : null
}

export function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split('-').map(Number)
  const shifted = new Date(Date.UTC(year, monthNumber - 1 + delta, 1))
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}`
}

export function clampMonth(month: string, minimum: string, maximum: string): string {
  if (month < minimum.slice(0, 7)) return minimum.slice(0, 7)
  if (month > maximum.slice(0, 7)) return maximum.slice(0, 7)
  return month
}

export function paginateRows<T>(rows: T[], page: number, pageSize = 100): PageSlice<T> {
  const safePageSize = Math.max(1, Math.floor(pageSize))
  const pageCount = Math.max(1, Math.ceil(rows.length / safePageSize))
  const safePage = Math.min(Math.max(1, Math.floor(page)), pageCount)
  const offset = (safePage - 1) * safePageSize
  return {
    items: rows.slice(offset, offset + safePageSize),
    total: rows.length,
    page: safePage,
    pageCount,
    start: rows.length ? offset + 1 : 0,
    end: Math.min(rows.length, offset + safePageSize),
  }
}

export function limitUpBoardLabel(row: LimitUpReviewRow): string {
  if (row.boards === null) return '板数未知'
  return `${row.boards} 板`
}

export function limitUpSealLabel(row: LimitUpReviewRow): string {
  if (row.status === 'limit_up') {
    if (row.one_word_board === true) return '09:30 一字'
    if (row.one_word_board === null) {
      return row.limit_up_time ? `${row.limit_up_time} · 一字未知` : '封板时间未知 · 一字未知'
    }
    return row.limit_up_time || '封板时间未知'
  }
  return row.limit_up_time ? `${row.limit_up_time} · 前日` : '前日封板时间未知'
}

export function limitUpStatusLabel(row: LimitUpReviewRow): string {
  if (row.status === 'limit_up') return '涨停'
  if (row.broken_kind === 'connection') return '连板中断'
  if (row.broken_kind === 'first') return '首板未续'
  return '断板 · 板数未知'
}

export function buildLimitUpCsv(rows: LimitUpReviewRow[]): string {
  const header = [
    '日期',
    '代码',
    '名称',
    '题材',
    '状态',
    '板数',
    '板数截至',
    '首封/一字',
    '封板时间截至',
    '涨跌幅',
    '一字板',
  ]
  const body = rows.map((row) => [
    row.date,
    row.symbol,
    row.name,
    row.sector,
    limitUpStatusLabel(row),
    row.boards === null ? '未知' : String(row.boards),
    row.boards_as_of_date,
    limitUpSealLabel(row),
    row.limit_up_time_as_of_date,
    row.change_pct ?? '',
    row.status === 'broken'
      ? '不适用（断板）'
      : row.one_word_board === null
        ? '未知'
        : row.one_word_board
          ? '是'
          : '否',
  ])
  return [header, ...body].map((line) => line.map(csvCell).join(',')).join('\r\n')
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`
}
