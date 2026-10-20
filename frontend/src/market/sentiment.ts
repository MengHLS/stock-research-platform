import type { LadderRead, LadderRow, ReviewHistoryRow } from './review'

export const SENTIMENT_WINDOWS = [20, 40, 60, 120] as const

export interface SentimentSnapshot {
  current: ReviewHistoryRow | null
  previous: ReviewHistoryRow | null
  average: number | null
  peak: ReviewHistoryRow | null
  knownScores: number
  totalRows: number
  maxBoard: number | null
}

export function parseSentimentWindow(value: unknown, maximum = 120): number {
  const safeMaximum = Math.max(1, Math.floor(maximum))
  const supported = SENTIMENT_WINDOWS.filter((window) => window <= safeMaximum)
  const fallback = supported.includes(40) ? 40 : (supported.at(-1) ?? safeMaximum)
  const parsed = Number(value)
  if (
    Number.isInteger(parsed) &&
    parsed > 0 &&
    parsed <= safeMaximum &&
    (supported.includes(parsed as (typeof SENTIMENT_WINDOWS)[number]) || parsed === safeMaximum)
  ) {
    return parsed
  }
  return fallback
}

export function orderedHistory(history: ReviewHistoryRow[]): ReviewHistoryRow[] {
  return [...history].sort((left, right) => left.date.localeCompare(right.date))
}

export function sentimentSnapshot(
  history: ReviewHistoryRow[],
  selectedDate?: string,
): SentimentSnapshot {
  const rows = orderedHistory(history)
  const selectedIndex = selectedDate
    ? rows.findIndex((row) => row.date === selectedDate)
    : rows.length - 1
  const currentIndex = selectedIndex >= 0 ? selectedIndex : rows.length - 1
  const current = rows[currentIndex] ?? null
  const previous = currentIndex > 0 ? (rows[currentIndex - 1] ?? null) : null
  const scores = rows
    .map((row) => row.emotion_score)
    .filter((score): score is number => score !== null && score !== undefined)
  const boards = rows
    .map((row) => row.max_board)
    .filter((value): value is number => value !== null && value !== undefined)
  const peak = rows.reduce<ReviewHistoryRow | null>((best, row) => {
    if (row.emotion_score === null || row.emotion_score === undefined) return best
    if (!best || best.emotion_score === null || best.emotion_score === undefined) return row
    return row.emotion_score > best.emotion_score ? row : best
  }, null)
  return {
    current,
    previous,
    average: scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : null,
    peak,
    knownScores: scores.length,
    totalRows: rows.length,
    maxBoard: boards.length ? Math.max(...boards) : null,
  }
}

export function sentimentTimeline(history: ReviewHistoryRow[], days = 14): ReviewHistoryRow[] {
  const limit = Math.max(0, Math.floor(days))
  if (!limit) return []
  return orderedHistory(history).slice(-limit).reverse()
}

export function sentimentLeaders(ladder: LadderRead, limit = 8): LadderRow[] {
  const rows = [...ladder.connection, ...ladder.first, ...ladder.unknown].filter(
    (row) => !row.broken_kind,
  )
  return rows
    .sort(
      (left, right) =>
        (right.boards ?? -1) - (left.boards ?? -1) ||
        left.limit_up_time.localeCompare(right.limit_up_time) ||
        left.symbol.localeCompare(right.symbol),
    )
    .slice(0, Math.max(0, Math.floor(limit)))
}
