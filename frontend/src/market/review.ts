import type { components } from '../api/schema'

export type ReviewOverview = components['schemas']['ReviewOverviewRead']
export type ReviewIndices = components['schemas']['ReviewIndicesRead']
export type ReviewContext = components['schemas']['ReviewContextRead']
export type ReviewHistoryRow = components['schemas']['MarketHistoryRowRead']
export type LadderRow = components['schemas']['LadderRowRead']
export type LadderRead = components['schemas']['LadderRead']
export type IndexSeries = components['schemas']['ReviewIndexSeriesRead']

export const REVIEW_WINDOWS = [20, 40, 60, 120] as const
export type ReviewWindow = number

export interface HeatmapCell {
  date: string
  theme: string
  count: number | null
}

export interface HeatmapModel {
  dates: string[]
  themes: string[]
  cells: Map<string, HeatmapCell>
  totals: Map<string, number>
  hasMissingDays: boolean
  max: number
}

export interface LadderGroup {
  key: string
  label: string
  rows: LadderRow[]
}

export interface EmotionRating {
  label: string
  tone: 'up' | 'flat' | 'down'
  note: string
}

export interface PriceExtreme {
  index: number
  date: string
  value: number
  kind: 'high' | 'low'
}

export function parseReviewWindow(value: unknown, maximum = 120): ReviewWindow {
  const parsed = Number(value)
  const supported = REVIEW_WINDOWS.some((window) => parsed === window) || parsed === maximum
  return Math.min(supported ? parsed : 60, maximum)
}

export function routeDate(value: unknown): string | null {
  const first = Array.isArray(value) ? value[0] : value
  if (typeof first !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(first)) return null
  const calendarDate = new Date(`${first}T00:00:00Z`)
  if (
    Number.isNaN(calendarDate.getTime()) ||
    calendarDate.toISOString().slice(0, 10) !== first ||
    first.startsWith('0000')
  )
    return null
  return first
}

export function chartNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function compareClass(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'flat'
  const number = Number(value)
  if (!Number.isFinite(number) || number === 0) return 'flat'
  return number > 0 ? 'up' : 'down'
}

export function formatNumber(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(number)
}

export function formatSignedPercent(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}%`
}

export function formatMetric(value: number | null | undefined, suffix = ''): string {
  return value === null || value === undefined ? '—' : `${value}${suffix}`
}

export function emotionRating(score: number | null | undefined): EmotionRating {
  if (score === null || score === undefined) {
    return { label: '不可评估', tone: 'flat', note: '评分所需记录不完整，页面保留未知。' }
  }
  if (score >= 86) {
    return { label: '亢奋', tone: 'up', note: '赚钱效应极强，警惕一致后分歧' }
  }
  if (score >= 71) {
    return { label: '活跃', tone: 'up', note: '情绪偏强，连板梯队健康' }
  }
  if (score >= 51) {
    return { label: '正常', tone: 'flat', note: '多空均衡，关注低位首板' }
  }
  if (score >= 31) {
    return { label: '低迷', tone: 'down', note: '缩量退潮，控制仓位' }
  }
  return { label: '冰点', tone: 'down', note: '情绪冰点，等待修复信号' }
}

export function buildCandleData(
  bars: IndexSeries['bars'],
): Array<[number, number, number, number] | null> {
  return bars.map((bar) => {
    if (bar.open === null || bar.close === null || bar.low === null || bar.high === null) {
      return null
    }
    return [Number(bar.open), Number(bar.close), Number(bar.low), Number(bar.high)]
  })
}

export function findPriceExtremes(bars: IndexSeries['bars']): PriceExtreme[] {
  let highIndex = -1
  let lowIndex = -1
  let highValue: number | null = null
  let lowValue: number | null = null
  buildCandleData(bars).forEach((values, index) => {
    if (!values) return
    const nextLow = values[2]
    const nextHigh = values[3]
    if (nextHigh !== null && (highValue === null || nextHigh > highValue)) {
      highIndex = index
      highValue = nextHigh
    }
    if (nextLow !== null && (lowValue === null || nextLow < lowValue)) {
      lowIndex = index
      lowValue = nextLow
    }
  })
  const extremes: PriceExtreme[] = []
  if (highIndex >= 0 && highValue !== null) {
    extremes.push({
      index: highIndex,
      date: bars[highIndex]!.date,
      value: highValue,
      kind: 'high',
    })
  }
  if (lowIndex >= 0 && lowValue !== null) {
    extremes.push({
      index: lowIndex,
      date: bars[lowIndex]!.date,
      value: lowValue,
      kind: 'low',
    })
  }
  return extremes
}

export function previousHistory(
  currentDate: string,
  history: ReviewHistoryRow[],
): ReviewHistoryRow | null {
  const ordered = [...history].sort((left, right) => left.date.localeCompare(right.date))
  const position = ordered.findIndex((row) => row.date === currentDate)
  return position > 0 ? ordered[position - 1] : null
}

export function buildLadderGroups(ladder: LadderRead): LadderGroup[] {
  const byHeight = new Map<number, LadderRow[]>()
  for (const row of [...ladder.connection, ...ladder.first, ...ladder.broken]) {
    if (row.boards === null) continue
    const rows = byHeight.get(row.boards) ?? []
    rows.push(row)
    byHeight.set(row.boards, rows)
  }
  const groups = Array.from(byHeight.entries())
    .sort(([left], [right]) => right - left)
    .map(([height, rows]) => ({
      key: `height-${height}`,
      label: height === 1 ? '首板' : `${height} 板`,
      rows,
    }))
  const unknown = [...ladder.unknown, ...ladder.broken.filter((row) => row.boards === null)]
  if (unknown.length) {
    groups.push({
      key: 'unknown',
      label: '板数未知',
      rows: unknown,
    })
  }
  return groups
}

export function trendPeakIndexes(history: ReviewHistoryRow[], limit = 8): number[] {
  const candidates: number[] = []
  history.forEach((row, index) => {
    const value = row.max_board
    if (value === null || value === undefined || value <= 0) return
    const previous = history[index - 1]?.max_board ?? null
    const next = history[index + 1]?.max_board ?? null
    if ((previous === null || value >= previous) && (next === null || value >= next)) {
      candidates.push(index)
    }
  })
  candidates.sort(
    (left, right) =>
      (history[right]?.max_board ?? 0) - (history[left]?.max_board ?? 0) || left - right,
  )
  const minimumGap = Math.max(3, Math.round(history.length / 10))
  const selected: number[] = []
  for (const index of candidates) {
    if (selected.length >= limit) break
    if (selected.every((existing) => Math.abs(existing - index) >= minimumGap)) {
      selected.push(index)
    }
  }
  return selected.sort((left, right) => left - right)
}

export function buildHeatmap(
  history: ReviewHistoryRow[],
  days = 14,
  maxThemes = Number.POSITIVE_INFINITY,
): HeatmapModel {
  const recent = [...history]
    .sort((left, right) => left.date.localeCompare(right.date))
    .slice(-days)
  const latest = recent.at(-1)
  const totalByTheme = new Map<string, number>()
  const latestByTheme = new Map<string, number>()
  for (const row of recent) {
    for (const theme of row.themes ?? []) {
      totalByTheme.set(theme.theme, (totalByTheme.get(theme.theme) ?? 0) + theme.count)
    }
  }
  for (const theme of latest?.themes ?? []) {
    latestByTheme.set(theme.theme, theme.count)
  }
  const rankedThemes = Array.from(totalByTheme.keys()).sort((left, right) => {
    if (left === '未知') return 1
    if (right === '未知') return -1
    return (
      (latestByTheme.get(right) ?? 0) - (latestByTheme.get(left) ?? 0) ||
      (totalByTheme.get(right) ?? 0) - (totalByTheme.get(left) ?? 0) ||
      left.localeCompare(right, 'zh-CN')
    )
  })
  const themeLimit = Math.max(0, Math.floor(maxThemes))
  const rankedKnown = rankedThemes.filter((theme) => theme !== '未知')
  const hasUnknownTheme = rankedThemes.includes('未知')
  const themes = Number.isFinite(themeLimit)
    ? [
        ...rankedKnown.slice(0, Math.max(0, themeLimit - (hasUnknownTheme ? 1 : 0))),
        ...(hasUnknownTheme && themeLimit > 0 ? ['未知'] : []),
      ]
    : rankedThemes
  const chosen = new Set(themes)
  const cells = new Map<string, HeatmapCell>()
  let max = 1
  let hasMissingDays = false
  for (const row of recent) {
    if (row.assessment === 'missing') hasMissingDays = true
    const counts = new Map((row.themes ?? []).map((theme) => [theme.theme, theme.count]))
    for (const theme of themes) {
      const count = row.assessment === 'missing' ? null : (counts.get(theme) ?? 0)
      cells.set(`${row.date}|${theme}`, { date: row.date, theme, count })
      if (count !== null) max = Math.max(max, count)
    }
  }
  const totals = new Map<string, number>()
  for (const theme of chosen) totals.set(theme, totalByTheme.get(theme) ?? 0)
  return {
    dates: recent.map((row) => row.date),
    themes,
    cells,
    totals,
    hasMissingDays,
    max,
  }
}

export function heatCellKey(date: string, theme: string): string {
  return `${date}|${theme}`
}

export function heatmapDatesNewestFirst(model: HeatmapModel): string[] {
  return [...model.dates].sort((left, right) => right.localeCompare(left))
}

export function mergeLadderRows(ladder: LadderRead): LadderRow[] {
  return [...ladder.connection, ...ladder.first, ...ladder.broken, ...ladder.unknown]
}
