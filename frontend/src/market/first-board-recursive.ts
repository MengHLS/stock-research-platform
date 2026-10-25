/**
 * Display model for the imported first-board recursive snapshot.
 *
 * The backend (`modules/first_board_recursive/labels.py`) owns every Chinese label and
 * sentence: stage / selection-reason / relation-status wording is read from the API
 * fields and is never re-mapped here. This module only derives layout decisions and
 * safe formatting from the contract, so one wording change cannot leave two copies out
 * of sync.
 *
 * Units follow the API contract: `limit_rate` is a ratio (0.1 = 10%), while fields
 * ending in `_pct` are already percent values (12.15 = 12.15%). Decimal fields are
 * decimal strings; `null` always means "unknown", which stays distinct from 0.
 */

import type { components } from '../api/schema'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'

export type FirstBoardRecursiveSnapshot = components['schemas']['SnapshotRead']
export type FirstBoardRecursiveSnapshotMeta = components['schemas']['SnapshotMetaRead']
export type FirstBoardRecursiveTargetDetail = components['schemas']['TargetDetailRead']
export type FirstBoardRecursiveSummary = components['schemas']['TargetSummaryRead']
export type FirstBoardRecursiveTarget = components['schemas']['TargetRead']
export type FirstBoardRecursiveNearestPrior = components['schemas']['NearestPriorRead']
export type FirstBoardRecursiveAnchor = components['schemas']['RecursiveAnchorRead']
export type FirstBoardRecursiveTimelineNode = components['schemas']['TimelineNodeRead']
export type FirstBoardRecursiveEarlierBoard = components['schemas']['EarlierFirstBoardRead']
export type FirstBoardRecursiveCandidate = components['schemas']['CandidateRead']
export type FirstBoardRecursiveAudit = components['schemas']['AuditRead']

/** Loading / empty / failure states of one stock's recursive detail. */
export type FirstBoardRecursiveStatus =
  'idle' | 'loading' | 'ready' | 'missing' | 'unavailable' | 'failure'

/** 404 on the target route: the stock is simply outside the frozen snapshot. */
export const RECURSIVE_TARGET_NOT_FOUND = 'FIRST_BOARD_RECURSIVE_TARGET_NOT_FOUND'
/** 404 on the snapshot route: nothing was imported yet (an operational state). */
export const RECURSIVE_SNAPSHOT_NOT_FOUND = 'FIRST_BOARD_RECURSIVE_SNAPSHOT_NOT_FOUND'

/** A fixed front-end label for a state the contract carries no sentence for. */
export const NO_PRIOR_FIRST_BOARD_TEXT = '2019 年以来无前次首板'
export const NO_PRIOR_FIRST_BOARD_NOTE =
  '当前冻结窗口内没有更早的合格首板，两层结构都没有前次首板可比较，递归结果只保留目标日首板。'

/** Missing anchor wording never claims a data gap: the snapshot concluded no anchor exists. */
export const ANCHOR_ABSENT_FALLBACK = '本轮递归没有可用的前次首板锚点，只展示目标日首板。'

/** The contract has no divergence sentence, so the UI explains the flag itself. */
export const LAYERS_DIVERGE_TEXT =
  '两层结论不在同一层：最近前次首板只描述最近一次事件，递归结果已回溯到更早的递归锚点，结论以递归结果为准。'

export const LEGACY_ANCHOR_MARK = '旧规则锚点（仅审计）'
export const LEGACY_ANCHOR_NOTE =
  '旧规则锚点只用于核对历史口径，不是本轮递归锚点，也不进入递归窗口。'
export const SELECTED_ANCHOR_MARK = '本轮递归锚点'
export const EARLIER_HISTORY_NOTE =
  '这些首板早于递归锚点，只作为历史背景，不参与本轮递归窗口，也不改变结论。'
/** `earlier_first_boards` only carries eligible non-ST prior first boards. */
export const EARLIER_HISTORY_SCOPE_NOTE =
  '该列表只含合格的非 ST 前次首板；历史首板中被标记 ST 或不合格的前次首板未列入本轮候选。'

/** Fallbacks for a record the contract has no label for (no prior board / no anchor). */
export const NEAREST_PRIOR_FALLBACK_LABEL = '最近前次首板'
export const RECURSIVE_ANCHOR_FALLBACK_LABEL = '递归锚点'

/** Six recursive result classes; each keeps its own tone so two badges never look alike. */
export const RECURSIVE_RESULT_STAGES = [
  'EPISODE_FIRST_CLOSE_REBREAK',
  'EPISODE_TARGET_DAY_DIRECT_BREAK',
  'EPISODE_REATTACK_BELOW_REFERENCE',
  'ALREADY_REBROKEN_BEFORE_TARGET',
  'NO_ACTIVE_PRIOR_EPISODE',
  'CHAIN_INFORMATION_INSUFFICIENT',
] as const

export type RecursiveResultTone =
  'rebreak' | 'direct' | 'reattack' | 'rebroken' | 'no-prior' | 'insufficient' | 'unknown'

const RESULT_STAGE_TONES: Readonly<Record<string, RecursiveResultTone>> = {
  EPISODE_FIRST_CLOSE_REBREAK: 'rebreak',
  EPISODE_TARGET_DAY_DIRECT_BREAK: 'direct',
  EPISODE_REATTACK_BELOW_REFERENCE: 'reattack',
  ALREADY_REBROKEN_BEFORE_TARGET: 'rebroken',
  NO_ACTIVE_PRIOR_EPISODE: 'no-prior',
  CHAIN_INFORMATION_INSUFFICIENT: 'insufficient',
}

/**
 * Candidate-only stages (`EPISODE_NO_PULLBACK_YET`, `EPISODE_WEAK_OR_NO_RECOVERY`) are not
 * result classes, so they stay neutral instead of borrowing a result color.
 */
export function recursiveStageTone(stage: string | null | undefined): RecursiveResultTone {
  if (!stage) return 'unknown'
  return RESULT_STAGE_TONES[stage] ?? 'unknown'
}

export type RecursiveNodeTone = 'anchor' | 'skipped' | 'nearest' | 'break' | 'target'

const NODE_TONES: Readonly<Record<string, RecursiveNodeTone>> = {
  ANCHOR: 'anchor',
  SKIPPED: 'skipped',
  NEAREST_PRIOR: 'nearest',
  FIRST_CLOSE_BREAK: 'break',
  TARGET: 'target',
}

export function recursiveNodeTone(role: string | null | undefined): RecursiveNodeTone {
  if (!role) return 'skipped'
  return NODE_TONES[role] ?? 'skipped'
}

/** 404 statuses become empty states; everything else stays a visible failure with retry. */
export type RecursiveFailureState = 'missing' | 'unavailable' | 'failure' | 'aborted'

export type RecursiveDateRelation = 'before' | 'same' | 'after' | 'unknown'

/**
 * Compare the review day against the frozen snapshot's own target day.
 *
 * `trade_date` is the day the frozen snapshot describes, so a review day before it must
 * never show this tab (that would leak future data), while a later review day may show it
 * only behind an explicit warning. ISO `YYYY-MM-DD` strings compare chronologically.
 */
export function recursiveDateRelation(
  reviewDate: string | null | undefined,
  snapshotDate: string | null | undefined,
): RecursiveDateRelation {
  if (!reviewDate || !snapshotDate) return 'unknown'
  if (reviewDate < snapshotDate) return 'before'
  if (reviewDate > snapshotDate) return 'after'
  return 'same'
}

/**
 * The tab exists only once a record is known or the feature itself needs attention:
 * a 404 target (`missing`) or an unfinished load stays out of the tab strip, while an
 * un-imported snapshot and a request failure stay visible with their own retry.
 * A review day before the frozen target day always hides the tab, and that date gate
 * survives `loading`: the gate only closes once the settled snapshot date proves it.
 */
export function recursiveTabVisible(
  status: FirstBoardRecursiveStatus,
  reviewDate?: string | null,
  snapshotDate?: string | null,
): boolean {
  if (status !== 'ready' && status !== 'unavailable' && status !== 'failure') return false
  return recursiveDateRelation(reviewDate, snapshotDate) !== 'before'
}

/**
 * Warning for a review day after the frozen target day; empty when both agree, when the
 * review day is before (the tab is hidden) or when a date is unknown.
 */
export function recursiveDateMismatchWarning(
  reviewDate: string | null | undefined,
  snapshotDate: string | null | undefined,
): string {
  if (recursiveDateRelation(reviewDate, snapshotDate) !== 'after') return ''
  return `当前复盘日 ${reviewDate} 晚于冻结快照目标日 ${snapshotDate}：本 Tab 展示 ${snapshotDate} 的冻结结论，不是当前复盘日的结论，可能不包含之后发生的结构变化。`
}

/** Render decision: a hidden tab always falls back to the quote/events view. */
export function effectiveRecursiveView(
  tabVisible: boolean,
  activeView: 'events' | 'recursive',
): 'events' | 'recursive' {
  return tabVisible ? activeView : 'events'
}

/**
 * Reset only when data is definitively absent or the date gate is closed. Transient
 * `loading` keeps the chosen view so switching between two covered stocks does not kick
 * the user back to the chart.
 */
export function shouldResetRecursiveView(
  status: FirstBoardRecursiveStatus,
  reviewDate?: string | null,
  snapshotDate?: string | null,
): boolean {
  if (recursiveDateRelation(reviewDate, snapshotDate) === 'before') return true
  return status === 'missing' || status === 'idle'
}

export function classifyRecursiveFailure(failure: ApiFailure): RecursiveFailureState {
  if (failure.kind === 'aborted') return 'aborted'
  if (failure.kind === 'business' && failure.code === RECURSIVE_TARGET_NOT_FOUND) return 'missing'
  if (failure.kind === 'business' && failure.code === RECURSIVE_SNAPSHOT_NOT_FOUND) {
    return 'unavailable'
  }
  return 'failure'
}

/** Safe copy for the failure branch; the raw message of a business failure is already reviewed. */
export function firstBoardRecursiveFailureText(failure: ApiFailure): string {
  if (isAuthNotConfigured(failure)) return '登录服务尚未启用，无法读取首板递归结构。'
  if (failure.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
  if (failure.kind === 'timeout') return '请求超时，首板递归结构暂未返回，请稍后重试。'
  if (failure.kind === 'business' && failure.code === 'FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE') {
    return '首板递归数据库暂不可用，未用其他数据替代。'
  }
  return failure.message
}

function parseDecimal(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const text = value.trim()
  if (!text) return null
  const number = Number(text)
  return Number.isFinite(number) ? number : null
}

function trimTrailingZeros(text: string): string {
  if (!text.includes('.')) return text
  return text.replace(/0+$/, '').replace(/\.$/, '') || '0'
}

/** Display-only: A-share prices keep two decimals; the API still returns full precision. */
export function formatRecursivePrice(value: string | null | undefined): string {
  const number = parseDecimal(value)
  return number === null ? '—' : number.toFixed(2)
}

/** `*_pct` values are already percent units (12.15 means 12.15%). */
export function formatRecursivePercent(value: string | null | undefined): string {
  const number = parseDecimal(value)
  return number === null ? '—' : `${number.toFixed(2)}%`
}

/** `limit_rate` is a ratio (0.1 = 10%); 0 stays a real value, `null` stays unknown. */
export function formatRecursiveLimitRate(value: string | null | undefined): string {
  const number = parseDecimal(value)
  if (number === null) return '—'
  return `${trimTrailingZeros((number * 100).toFixed(2))}%`
}

export function formatRecursiveSessionDistance(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${value} 个交易日`
}

/** 0 is displayed as 0; only `null` becomes `—`. */
export function formatRecursiveNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return String(value)
}

/** `board_count_text` wins, then the numeric board count, then an explicit gap. */
export function formatRecursiveBoardCount(
  card: Pick<FirstBoardRecursiveTarget, 'board_count' | 'board_count_text'>,
): string {
  if (card.board_count_text !== null && card.board_count_text !== undefined) {
    return card.board_count_text
  }
  if (card.board_count !== null && card.board_count !== undefined) {
    return String(card.board_count)
  }
  return '—'
}

export interface RecursiveEarlierRow {
  date: string
  stage_label: string
}

export interface RecursiveHistorySplit {
  /** The recursive window only: anchor and later, target last. */
  window: FirstBoardRecursiveTimelineNode[]
  /** Folded history before the anchor, in ascending date order, deduplicated by date. */
  earlier: RecursiveEarlierRow[]
}

/**
 * Split the served history into the recursive window and the folded earlier history.
 *
 * `is_before_anchor` wins; the anchor date is the fallback for rows that carry no flag.
 * A pre-anchor node accidentally placed in `timeline` can therefore never reach the main
 * timeline (for example a 2019 legacy anchor).
 */
export function splitRecursiveHistory(
  timeline: readonly FirstBoardRecursiveTimelineNode[],
  earlierFirstBoards: readonly FirstBoardRecursiveEarlierBoard[],
  anchorDate: string | null,
): RecursiveHistorySplit {
  const window: FirstBoardRecursiveTimelineNode[] = []
  const earlier: RecursiveEarlierRow[] = earlierFirstBoards.map((item) => ({
    date: item.date,
    stage_label: item.stage_label,
  }))
  for (const node of timeline) {
    const beforeAnchor = node.is_before_anchor || (anchorDate !== null && node.date < anchorDate)
    if (beforeAnchor) {
      earlier.push({ date: node.date, stage_label: node.stage_label ?? node.label })
    } else {
      window.push(node)
    }
  }
  window.sort((left, right) => left.date.localeCompare(right.date) || left.order - right.order)
  earlier.sort((left, right) => left.date.localeCompare(right.date))
  const seen = new Set<string>()
  return {
    window,
    earlier: earlier.filter((row) => {
      if (seen.has(row.date)) return false
      seen.add(row.date)
      return true
    }),
  }
}

/** Fold title: strictly the eligible non-ST prior first boards before the anchor. */
export function earlierHistoryTitle(count: number): string {
  return `更早的合格前次首板（${count} 条，默认折叠，早于递归锚点，不在本轮递归窗口内）`
}

/** No anchor is a conclusion of the snapshot, never a missing field: reuse its explanation. */
export function anchorAbsentExplanation(stageDescription: string | null | undefined): string {
  const text = stageDescription?.trim()
  return text ? text : ANCHOR_ABSENT_FALLBACK
}

export function layersDivergeHint(layersDiverge: boolean): string {
  return layersDiverge ? LAYERS_DIVERGE_TEXT : ''
}

export function candidateLegacyMark(isLegacyAnchor: boolean): string {
  return isLegacyAnchor ? LEGACY_ANCHOR_MARK : ''
}

export function candidateAnchorMark(isSelectedAnchor: boolean): string {
  return isSelectedAnchor ? SELECTED_ANCHOR_MARK : ''
}
