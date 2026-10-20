import type { components } from '../api/schema'

export type IntradayQuote = components['schemas']['QuoteRead']
export type IntradaySeries = components['schemas']['IntradaySeries']
export type IntradayBar = components['schemas']['BarRead']
export type OpeningAuction = components['schemas']['AuctionRead']
export type MarketSession = components['schemas']['MarketSessionRead']
export type MarketPhase = IntradayQuote['phase']

export const INTRADAY_WATCH_LIMIT = 50
export const INTRADAY_WATCH_STORAGE_PREFIX = 'rp.intraday.watchlist.v1'
export const INTRADAY_CONTINUOUS_SLOTS = 240
export const INTRADAY_TIME_TICKS: readonly { slot: number; label: string }[] = [
  { slot: 0, label: '09:31' },
  { slot: 59, label: '10:30' },
  { slot: 119, label: '11:30' },
  { slot: 149, label: '13:30' },
  { slot: 239, label: '15:00' },
]

const TICKER_PATTERN = /^\d{5,6}$/
const CANONICAL_TICKER_PATTERN = /^(\d{5,6})\.(SH|SZ|BJ)$/i
const PREFIXED_TICKER_PATTERN = /^(SH|SZ|BJ)\.?(\d{5,6})$/i

export interface TickerInputResult {
  valid: string[]
  invalid: string[]
  duplicates: string[]
}

export interface WatchMergeResult {
  codes: string[]
  added: string[]
  duplicates: string[]
  overflow: string[]
}

export interface IntradaySummary {
  barCount: number
  latestBarTime: string | null
  barTradingDay: string | null
  intradayVolumeShares: number | null
  openGapPct: number | null
  drawdownFromHighPct: number | null
  positionPct: number | null
}

export interface IntradayPriceAxis {
  center: number
  top: number
  bottom: number
  boundPct: number
}

export interface IntradayLinePoint {
  slot: number
  value: number
}

export function parseTickerInput(raw: string): TickerInputResult {
  const tokens = raw
    .split(/[\s,，;；]+/)
    .map((token) => token.trim())
    .filter(Boolean)
  const valid: string[] = []
  const invalid: string[] = []
  const duplicates: string[] = []
  const seen = new Set<string>()

  for (const token of tokens) {
    const normalized = normalizeTicker(token)
    if (!normalized) {
      invalid.push(token)
      continue
    }
    if (seen.has(normalized)) {
      duplicates.push(token)
      continue
    }
    seen.add(normalized)
    valid.push(normalized)
  }

  return { valid, invalid, duplicates }
}

export function mergeWatchlist(
  existing: readonly string[],
  additions: readonly string[],
  limit = INTRADAY_WATCH_LIMIT,
): WatchMergeResult {
  const codes = [...existing]
  const seen = new Set(codes)
  const added: string[] = []
  const duplicates: string[] = []
  const overflow: string[] = []

  for (const code of additions) {
    if (seen.has(code)) {
      duplicates.push(code)
      continue
    }
    seen.add(code)
    if (codes.length >= limit) {
      overflow.push(code)
      continue
    }
    codes.push(code)
    added.push(code)
  }

  return { codes, added, duplicates, overflow }
}

export function canonicalWatchCodes(codes: readonly string[]): {
  codes: string[]
  aliases: Map<string, string>
} {
  const result: string[] = []
  const aliases = new Map<string, string>()
  for (const raw of codes) {
    const code = normalizeTicker(raw)
    if (!code) continue
    if (!result.includes(code)) {
      result.push(code)
      aliases.set(raw, code)
      aliases.set(code, code)
    }
  }
  return { codes: result, aliases }
}

export function normalizeTicker(value: unknown): string | null {
  const first = Array.isArray(value) ? value[0] : value
  if (typeof first !== 'string') return null
  const trimmed = first.trim()
  if (TICKER_PATTERN.test(trimmed)) return inferBareTicker(trimmed)
  const canonical = CANONICAL_TICKER_PATTERN.exec(trimmed)
  if (canonical) return `${canonical[1]}.${canonical[2].toUpperCase()}`
  const prefixed = PREFIXED_TICKER_PATTERN.exec(trimmed)
  if (prefixed) return `${prefixed[2]}.${prefixed[1].toUpperCase()}`
  return null
}

function inferBareTicker(code: string): string {
  if (/^(920|4|8)/.test(code)) return `${code}.BJ`
  if (/^(5|6|900)/.test(code)) return `${code}.SH`
  if (/^(0|1|2|3|200)/.test(code)) return `${code}.SZ`
  return code
}

export function readStoredWatchlist(raw: string | null, limit = INTRADAY_WATCH_LIMIT): string[] {
  if (!raw) return []
  try {
    const value: unknown = JSON.parse(raw)
    if (!Array.isArray(value)) return []
    const result: string[] = []
    for (const item of value) {
      const code = normalizeTicker(item)
      if (code && !result.includes(code)) result.push(code)
      if (result.length >= limit) break
    }
    return result
  } catch {
    return []
  }
}

export function watchlistStorageKey(userId: number | null | undefined): string {
  return `${INTRADAY_WATCH_STORAGE_PREFIX}:${userId ?? 'anonymous'}`
}

export function exchangeLabel(symbol: string | null | undefined): string {
  if (!symbol) return '交易所未知'
  if (/\.SH$/i.test(symbol)) return '上交所'
  if (/\.SZ$/i.test(symbol)) return '深交所'
  if (/\.BJ$/i.test(symbol)) return '北交所'
  return '交易所未知'
}

export function marketPhaseLabel(phase: MarketPhase | null | undefined): string {
  switch (phase) {
    case 'opening_auction':
      return '集合竞价'
    case 'pre_open':
      return '竞价结束'
    case 'continuous':
      return '连续交易'
    case 'lunch_break':
      return '午间休市'
    case 'closed':
      return '已收盘'
    default:
      return '时段未知'
  }
}

export function phaseTone(phase: MarketPhase | null | undefined): 'live' | 'muted' | 'warn' {
  if (phase === 'continuous' || phase === 'opening_auction') return 'live'
  if (phase === 'pre_open' || phase === 'lunch_break') return 'warn'
  return 'muted'
}

export function formatShanghaiTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(parsed)
}

export function formatShanghaiDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(parsed)
}

export function formatAmount(value: string | number | null | undefined): string {
  const amount = numeric(value)
  if (amount === null) return '—'
  if (Math.abs(amount) >= 100_000_000) return `${(amount / 100_000_000).toFixed(2)} 亿`
  if (Math.abs(amount) >= 10_000) return `${(amount / 10_000).toFixed(2)} 万`
  return `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(amount)} 元`
}

export function formatShares(value: string | number | null | undefined): string {
  const shares = numeric(value)
  if (shares === null) return '—'
  if (Math.abs(shares) >= 100_000_000) return `${(shares / 100_000_000).toFixed(2)} 亿股`
  if (Math.abs(shares) >= 10_000) return `${(shares / 10_000).toFixed(2)} 万股`
  return `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(shares)} 股`
}

export function percentDistance(
  current: string | number | null | undefined,
  reference: string | number | null | undefined,
): number | null {
  const currentValue = numeric(current)
  const referenceValue = numeric(reference)
  if (currentValue === null || referenceValue === null || referenceValue === 0) return null
  return (currentValue / referenceValue - 1) * 100
}

export function intradaySlotIndex(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return null
  const exchangeLocal = new Date(parsed.getTime() + 8 * 60 * 60 * 1000)
  const clock = exchangeLocal.getUTCHours() * 60 + exchangeLocal.getUTCMinutes()
  if (clock >= 9 * 60 + 31 && clock <= 11 * 60 + 30) {
    return clock - (9 * 60 + 31)
  }
  if (clock >= 13 * 60 + 1 && clock <= 15 * 60) {
    return 120 + clock - (13 * 60 + 1)
  }
  // 09:30 only contains the opening auction and is outside the 240 continuous minutes.
  return null
}

export function positivePrice(value: string | number | null | undefined): number | null {
  const price = numeric(value)
  return price !== null && price > 0 ? price : null
}

export function continuousIntradaySegments(bars: readonly IntradayBar[]): IntradayLinePoint[][] {
  const segments: IntradayLinePoint[][] = []
  let current: IntradayLinePoint[] = []
  const flush = () => {
    if (current.length) segments.push(current)
    current = []
  }

  for (const bar of bars) {
    const slot = intradaySlotIndex(bar.start)
    const value = positivePrice(bar.close)
    if (slot === null || value === null) {
      flush()
      continue
    }
    const previousSlot = current.at(-1)?.slot
    if (previousSlot !== undefined && slot !== previousSlot + 1) flush()
    current.push({ slot, value })
  }
  flush()
  return segments
}

export function symmetricIntradayRange(
  previousClose: string | number | null | undefined,
  values: readonly (string | number | null | undefined)[],
): IntradayPriceAxis | null {
  const center = positivePrice(previousClose)
  if (center === null) return null
  let maximumDeviation = 0
  for (const raw of values) {
    const value = positivePrice(raw)
    if (value === null) continue
    maximumDeviation = Math.max(maximumDeviation, Math.abs(value / center - 1))
  }
  const boundPct = Math.max(0.005, maximumDeviation * 1.08)
  return {
    center,
    top: center * (1 + boundPct),
    bottom: center * (1 - boundPct),
    boundPct,
  }
}

export function latestTradingDayBars(bars: readonly IntradayBar[]): IntradayBar[] {
  if (!bars.length) return []
  const latest = bars.reduce((winner, bar) =>
    bar.start.localeCompare(winner.start) > 0 ? bar : winner,
  )
  return bars
    .filter((bar) => bar.trading_day === latest.trading_day)
    .sort((left, right) => left.start.localeCompare(right.start))
}

export function intradaySummary(
  quote: IntradayQuote,
  bars: readonly IntradayBar[],
): IntradaySummary {
  const volumes = bars
    .map((bar) => numeric(bar.volume_shares))
    .filter((value): value is number => value !== null)
  const latest = bars.at(-1)
  const high = numeric(quote.high)
  const low = numeric(quote.low)
  const price = numeric(quote.price)
  const opening = numeric(quote.open)
  const previousClose = numeric(quote.previous_close)
  const positionPct =
    price !== null && high !== null && low !== null && high > low
      ? clamp(((price - low) / (high - low)) * 100, 0, 100)
      : null

  return {
    barCount: bars.length,
    latestBarTime: latest?.start ?? null,
    barTradingDay: latest?.trading_day ?? null,
    intradayVolumeShares: volumes.length
      ? volumes.reduce((total, value) => total + value, 0)
      : null,
    openGapPct:
      opening !== null && previousClose !== null && previousClose !== 0
        ? (opening / previousClose - 1) * 100
        : null,
    drawdownFromHighPct:
      price !== null && high !== null && high !== 0 ? (price / high - 1) * 100 : null,
    positionPct,
  }
}

function numeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value))
}
