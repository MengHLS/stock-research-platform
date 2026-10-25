import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import FirstBoardRecursivePanel from '../components/market/FirstBoardRecursivePanel.vue'
import LimitUpDetail from '../components/market/LimitUpDetail.vue'
import type { ApiFailure } from '../api/errors'
import type { LimitUpReviewRow } from './review'
import {
  EARLIER_HISTORY_SCOPE_NOTE,
  LAYERS_DIVERGE_TEXT,
  LEGACY_ANCHOR_MARK,
  NO_PRIOR_FIRST_BOARD_TEXT,
  RECURSIVE_RESULT_STAGES,
  RECURSIVE_SNAPSHOT_NOT_FOUND,
  RECURSIVE_TARGET_NOT_FOUND,
  SELECTED_ANCHOR_MARK,
  anchorAbsentExplanation,
  candidateAnchorMark,
  candidateLegacyMark,
  classifyRecursiveFailure,
  earlierHistoryTitle,
  effectiveRecursiveView,
  firstBoardRecursiveFailureText,
  formatRecursiveBoardCount,
  formatRecursiveLimitRate,
  formatRecursiveNumber,
  formatRecursivePercent,
  formatRecursivePrice,
  formatRecursiveSessionDistance,
  layersDivergeHint,
  recursiveDateMismatchWarning,
  recursiveDateRelation,
  recursiveNodeTone,
  recursiveStageTone,
  recursiveTabVisible,
  shouldResetRecursiveView,
  splitRecursiveHistory,
  type FirstBoardRecursiveCandidate,
  type FirstBoardRecursiveEarlierBoard,
  type FirstBoardRecursiveSnapshotMeta,
  type FirstBoardRecursiveSummary,
  type FirstBoardRecursiveTarget,
  type FirstBoardRecursiveTargetDetail,
  type FirstBoardRecursiveTimelineNode,
} from './first-board-recursive'

function node(
  partial: Pick<FirstBoardRecursiveTimelineNode, 'order' | 'date' | 'role'> &
    Partial<FirstBoardRecursiveTimelineNode>,
): FirstBoardRecursiveTimelineNode {
  return {
    order: partial.order,
    date: partial.date,
    kind: partial.kind ?? 'FIRST_BOARD',
    role: partial.role,
    label: partial.label ?? '节点',
    stage: partial.stage ?? null,
    stage_label: partial.stage_label ?? null,
    is_selected_anchor: partial.is_selected_anchor ?? false,
    is_skipped: partial.is_skipped ?? false,
    is_nearest_prior: partial.is_nearest_prior ?? false,
    is_before_anchor: partial.is_before_anchor ?? false,
    limit_rate: partial.limit_rate ?? null,
    reference_peak: partial.reference_peak ?? null,
    pullback_low: partial.pullback_low ?? null,
    first_close_break_date: partial.first_close_break_date ?? null,
    target_close_vs_reference_pct: partial.target_close_vs_reference_pct ?? null,
    note: partial.note ?? null,
  }
}

function earlierBoard(date: string, rank: number): FirstBoardRecursiveEarlierBoard {
  return {
    date,
    rank_oldest: rank,
    rank_nearest: 27 - rank,
    stage: 'EPISODE_NO_PULLBACK_YET',
    stage_label: '前次首板后尚未形成有效洗盘',
    is_before_anchor: true,
    is_skipped: false,
  }
}

function earlierBoards(count = 26): FirstBoardRecursiveEarlierBoard[] {
  const boards = [earlierBoard('2019-06-19', 1)]
  for (let index = 0; index < count - 1; index += 1) {
    const month = String((index % 12) + 1).padStart(2, '0')
    const day = String(Math.floor(index / 12) + 2).padStart(2, '0')
    boards.push(earlierBoard(`2020-${month}-${day}`, index + 2))
  }
  return boards
}

const anchor = node({
  order: 1,
  date: '2026-07-29',
  role: 'ANCHOR',
  label: '递归锚点首板',
  stage_label: '目标前已经越过前高',
  is_selected_anchor: true,
  limit_rate: '0.1',
  reference_peak: '15.39',
  pullback_low: '13.52',
  first_close_break_date: '2026-09-01',
  target_close_vs_reference_pct: '12.150747238466542',
  note: '该首板作为递归锚点。',
})
const skipped = node({
  order: 2,
  date: '2026-09-01',
  role: 'SKIPPED',
  label: '被跳过的首板',
  is_skipped: true,
  note: '该首板未形成有效结构，被递归跳过。',
})
const firstBreak = node({
  order: 3,
  date: '2026-09-01',
  role: 'FIRST_CLOSE_BREAK',
  kind: 'FIRST_CLOSE_BREAK',
  label: '首次收盘突破',
  first_close_break_date: '2026-09-01',
  note: '锚点后首次以收盘价越过参考高点。',
})
const nearestPrior = node({
  order: 4,
  date: '2026-10-15',
  role: 'NEAREST_PRIOR',
  label: '最近前次首板',
  is_nearest_prior: true,
  stage_label: '前次首板后尚未形成有效洗盘',
  note: '最近前次首板未形成有效结构，递归继续向更早的首板回溯。',
})
const target = node({
  order: 5,
  date: '2026-10-23',
  role: 'TARGET',
  kind: 'TARGET',
  label: '目标首板',
  stage_label: '目标前已经越过前高',
  note: '目标日首板。',
})
const legacyAnchorFromTimeline = node({
  order: 0,
  date: '2019-06-19',
  role: 'SKIPPED',
  label: '被跳过的首板',
  is_before_anchor: true,
})
const beforeAnchorByDate = node({
  order: 0,
  date: '2026-05-01',
  role: 'SKIPPED',
  label: '被跳过的首板',
})

function failure(overrides: Partial<ApiFailure>): ApiFailure {
  return {
    kind: 'business',
    code: null,
    message: '请求失败',
    status: 500,
    requestId: null,
    retryable: false,
    fields: [],
    ...overrides,
  }
}

describe('first-board recursive formatting', () => {
  it('keeps a missing price distinct from a real price', () => {
    expect(formatRecursivePrice(null)).toBe('—')
    expect(formatRecursivePrice('15.39')).toBe('15.39')
    expect(formatRecursivePrice('12.150747238467')).toBe('12.15')
    expect(formatRecursivePrice('0')).toBe('0.00')
  })

  it('shows limit_rate as a percent ratio and other percent fields as-is', () => {
    expect(formatRecursiveLimitRate('0.1')).toBe('10%')
    expect(formatRecursiveLimitRate('0.2')).toBe('20%')
    expect(formatRecursiveLimitRate('0')).toBe('0%')
    expect(formatRecursiveLimitRate(null)).toBe('—')
    expect(formatRecursivePercent('12.150747238466542')).toBe('12.15%')
    expect(formatRecursivePercent('0')).toBe('0.00%')
    expect(formatRecursivePercent(null)).toBe('—')
  })

  it('formats session distance and counts without turning 0 into a gap', () => {
    expect(formatRecursiveSessionDistance(null)).toBe('—')
    expect(formatRecursiveSessionDistance(0)).toBe('0 个交易日')
    expect(formatRecursiveSessionDistance(9)).toBe('9 个交易日')
    expect(formatRecursiveNumber(null)).toBe('—')
    expect(formatRecursiveNumber(0)).toBe('0')
    expect(formatRecursiveNumber(29)).toBe('29')
  })

  it('falls back from board_count_text to board_count and then to a gap', () => {
    expect(formatRecursiveBoardCount({ board_count_text: '一字板', board_count: null })).toBe(
      '一字板',
    )
    expect(formatRecursiveBoardCount({ board_count_text: null, board_count: 3 })).toBe('3')
    expect(formatRecursiveBoardCount({ board_count_text: null, board_count: 0 })).toBe('0')
    expect(formatRecursiveBoardCount({ board_count_text: null, board_count: null })).toBe('—')
  })
})

describe('first-board recursive result tones', () => {
  it('gives each of the six result classes its own tone', () => {
    const tones = RECURSIVE_RESULT_STAGES.map(recursiveStageTone)
    expect(new Set(tones).size).toBe(6)
    expect(tones).not.toContain('unknown')
  })

  it('leaves candidate-only stages neutral instead of borrowing a result color', () => {
    expect(recursiveStageTone('EPISODE_NO_PULLBACK_YET')).toBe('unknown')
    expect(recursiveStageTone('EPISODE_WEAK_OR_NO_RECOVERY')).toBe('unknown')
    expect(recursiveStageTone(null)).toBe('unknown')
  })

  it('keeps five timeline roles visually distinct', () => {
    const tones = ['ANCHOR', 'SKIPPED', 'NEAREST_PRIOR', 'FIRST_CLOSE_BREAK', 'TARGET'].map(
      recursiveNodeTone,
    )
    expect(new Set(tones).size).toBe(5)
    expect(recursiveNodeTone('UNKNOWN_ROLE')).toBe('skipped')
  })
})

describe('first-board recursive timeline split', () => {
  it('keeps only the recursive window in the main timeline', () => {
    const { window } = splitRecursiveHistory(
      [legacyAnchorFromTimeline, anchor, skipped, firstBreak, nearestPrior, target],
      earlierBoards(),
      '2026-07-29',
    )

    expect(window.map((item) => item.date)).toEqual([
      '2026-07-29',
      '2026-09-01',
      '2026-09-01',
      '2026-10-15',
      '2026-10-23',
    ])
    expect(window.at(-1)?.role).toBe('TARGET')
    expect(window.some((item) => item.date === '2019-06-19')).toBe(false)
  })

  it('folds pre-anchor history, never duplicating a date', () => {
    const { earlier } = splitRecursiveHistory(
      [legacyAnchorFromTimeline, anchor, skipped, firstBreak, nearestPrior, target],
      earlierBoards(),
      '2026-07-29',
    )

    expect(earlier).toHaveLength(26)
    expect(earlier.filter((item) => item.date === '2019-06-19')).toHaveLength(1)
    expect(earlier[0].date).toBe('2019-06-19')
  })

  it('uses the anchor date as a fallback when a node carries no before-anchor flag', () => {
    const { window, earlier } = splitRecursiveHistory(
      [beforeAnchorByDate, anchor, target],
      earlierBoards(),
      '2026-07-29',
    )

    expect(window.map((item) => item.date)).toEqual(['2026-07-29', '2026-10-23'])
    expect(earlier.some((item) => item.date === '2026-05-01')).toBe(true)
    expect(earlier).toHaveLength(27)
  })

  it('keeps the target alone when the snapshot concluded there is no anchor', () => {
    const { window, earlier } = splitRecursiveHistory([target], [], null)

    expect(window).toHaveLength(1)
    expect(window[0].role).toBe('TARGET')
    expect(earlier).toEqual([])
  })
})

describe('first-board recursive copy and empty states', () => {
  it('writes the exact fold title with the eligible row count', () => {
    expect(earlierHistoryTitle(26)).toBe(
      '更早的合格前次首板（26 条，默认折叠，早于递归锚点，不在本轮递归窗口内）',
    )
  })

  it('states that the fold excludes ST and ineligible prior first boards', () => {
    expect(EARLIER_HISTORY_SCOPE_NOTE).toContain('ST')
    expect(EARLIER_HISTORY_SCOPE_NOTE).toContain('未列入')
  })

  it('explains a missing anchor as a conclusion and never as a missing field', () => {
    const fromApi = anchorAbsentExplanation('2019 年以来没有可作为锚点的前次首板，无从递归。')
    const fallback = anchorAbsentExplanation(null)

    expect(fromApi).toBe('2019 年以来没有可作为锚点的前次首板，无从递归。')
    expect(fallback).not.toContain('缺失')
    expect(fallback.length).toBeGreaterThan(0)
    expect(fromApi).not.toContain('缺失')
  })

  it('keeps the no-prior-first-board wording explicit', () => {
    expect(NO_PRIOR_FIRST_BOARD_TEXT).toBe('2019 年以来无前次首板')
  })

  it('explains diverging layers only when the flag is set', () => {
    expect(layersDivergeHint(false)).toBe('')
    expect(layersDivergeHint(true)).toBe(LAYERS_DIVERGE_TEXT)
    // The anchor itself may be classified "information insufficient", so the sentence must
    // not call it "valid/有效" (that would contradict the information-gap conclusion).
    expect(LAYERS_DIVERGE_TEXT).not.toContain('有效')
    expect(LAYERS_DIVERGE_TEXT).toContain('递归锚点')
  })

  it('marks legacy and selected candidates without confusing them', () => {
    expect(candidateLegacyMark(true)).toBe(LEGACY_ANCHOR_MARK)
    expect(candidateLegacyMark(false)).toBe('')
    expect(candidateAnchorMark(true)).toBe(SELECTED_ANCHOR_MARK)
    expect(candidateAnchorMark(false)).toBe('')
  })
})

describe('first-board recursive date gate', () => {
  it('compares the review day against the frozen target day', () => {
    expect(recursiveDateRelation('2026-10-21', '2026-10-23')).toBe('before')
    expect(recursiveDateRelation('2026-10-23', '2026-10-23')).toBe('same')
    expect(recursiveDateRelation('2026-10-26', '2026-10-23')).toBe('after')
    expect(recursiveDateRelation(null, '2026-10-23')).toBe('unknown')
    expect(recursiveDateRelation('2026-10-23', null)).toBe('unknown')
    expect(recursiveDateRelation('', '')).toBe('unknown')
  })

  it('never shows the tab for a review day before the frozen target day', () => {
    expect(recursiveTabVisible('ready', '2026-10-21', '2026-10-23')).toBe(false)
    expect(recursiveTabVisible('ready', '2026-10-23', '2026-10-23')).toBe(true)
    expect(recursiveTabVisible('ready', '2026-10-26', '2026-10-23')).toBe(true)
    expect(recursiveTabVisible('missing', '2026-10-23', '2026-10-23')).toBe(false)
    expect(recursiveTabVisible('loading', '2026-10-21', '2026-10-23')).toBe(false)
    expect(recursiveTabVisible('idle')).toBe(false)
    expect(recursiveTabVisible('unavailable', '2026-10-21', null)).toBe(true)
    expect(recursiveTabVisible('failure', '2026-10-21', null)).toBe(true)
  })

  it('warns with both dates only when the review day is after the snapshot day', () => {
    const warning = recursiveDateMismatchWarning('2026-10-26', '2026-10-23')

    expect(warning).toContain('2026-10-26')
    expect(warning).toContain('2026-10-23')
    expect(warning).toContain('不是当前复盘日的结论')
    expect(recursiveDateMismatchWarning('2026-10-23', '2026-10-23')).toBe('')
    expect(recursiveDateMismatchWarning('2026-10-21', '2026-10-23')).toBe('')
    expect(recursiveDateMismatchWarning(null, '2026-10-23')).toBe('')
  })

  it('renders the effective view and resets only on a settled empty state', () => {
    expect(effectiveRecursiveView(true, 'recursive')).toBe('recursive')
    expect(effectiveRecursiveView(true, 'events')).toBe('events')
    expect(effectiveRecursiveView(false, 'recursive')).toBe('events')

    expect(shouldResetRecursiveView('loading')).toBe(false)
    expect(shouldResetRecursiveView('loading', null, null)).toBe(false)
    expect(shouldResetRecursiveView('ready', '2026-10-23', '2026-10-23')).toBe(false)
    expect(shouldResetRecursiveView('failure')).toBe(false)
    expect(shouldResetRecursiveView('idle')).toBe(true)
    expect(shouldResetRecursiveView('missing', '2026-10-23', '2026-10-23')).toBe(true)
    expect(shouldResetRecursiveView('ready', '2026-10-21', '2026-10-23')).toBe(true)
  })
})

describe('first-board recursive failure handling', () => {
  it('treats a target 404 as frozen scope, not as a failure', () => {
    expect(
      classifyRecursiveFailure(failure({ code: RECURSIVE_TARGET_NOT_FOUND, status: 404 })),
    ).toBe('missing')
    expect(
      classifyRecursiveFailure(failure({ code: RECURSIVE_SNAPSHOT_NOT_FOUND, status: 404 })),
    ).toBe('unavailable')
    expect(classifyRecursiveFailure(failure({ kind: 'network', code: null, status: null }))).toBe(
      'failure',
    )
    expect(classifyRecursiveFailure(failure({ kind: 'aborted', code: null, status: null }))).toBe(
      'aborted',
    )
  })

  it('keeps failure copy safe and specific', () => {
    expect(
      firstBoardRecursiveFailureText(
        failure({ code: 'AUTH_NOT_CONFIGURED', status: 503, message: 'x' }),
      ),
    ).toBe('登录服务尚未启用，无法读取首板递归结构。')
    expect(
      firstBoardRecursiveFailureText(failure({ kind: 'network', code: null, status: null })),
    ).toContain('无法连接后台服务')
    expect(
      firstBoardRecursiveFailureText(
        failure({ kind: 'business', code: null, status: 409, message: '业务侧已审核文案' }),
      ),
    ).toBe('业务侧已审核文案')
  })
})

const snapshotMeta: FirstBoardRecursiveSnapshotMeta = {
  snapshot_id: 'fbr-2026-10-23',
  trade_date: '2026-10-23',
  board_scope: 'MAINBOARD_ONLY',
  board_scope_label: '主板',
  status: 'PASS',
  status_label: '冻结研究结果，校验通过',
  computed_at: '2026-11-01T08:00:00+00:00',
  counts: { targets: 53, first_boards_since_2019: 1710, candidate_links: 1802 },
  stage_counts: { ALREADY_REBROKEN_BEFORE_TARGET: 12 },
  stage_labels: { ALREADY_REBROKEN_BEFORE_TARGET: '目标前已经越过前高' },
  selection_reason_counts: { RECURSIVE_ACTIVE_EPISODE: 8 },
  selection_reason_labels: { RECURSIVE_ACTIVE_EPISODE: '回溯到更早的有效结构' },
  source: {
    source_kind: 'FROZEN_RESEARCH',
    source_sha256: 'a'.repeat(64),
    artifact_sha256: 'b'.repeat(64),
    verification_status: 'PASS',
    verification_status_label: '校验通过',
    uses_forward_data: false,
  },
}

const targetSummary: FirstBoardRecursiveSummary = {
  stock_code: '002945.SZ',
  stock_name: '华林证券',
  theme: '证券',
  target_order: 1,
  target_date: '2026-10-23',
  target_close: '15.39',
  limit_rate: '0.1',
  board_count: 1,
  board_count_text: null,
  result_stage: 'ALREADY_REBROKEN_BEFORE_TARGET',
  result_stage_label: '目标前已经越过前高',
  selection_reason: 'RECURSIVE_ACTIVE_EPISODE',
  selection_reason_label: '回溯到更早的有效结构',
  nearest_prior_date: '2026-10-15',
  nearest_prior_stage: 'EPISODE_NO_PULLBACK_YET',
  nearest_prior_stage_label: '前次首板后尚未形成有效洗盘',
  anchor_date: '2026-07-29',
  anchor_distance_sessions: 60,
  layers_diverge: true,
  relation_status: 'ALREADY_CLOSED_ABOVE_REFERENCE_BEFORE_TARGET',
  relation_status_label: '目标前已收盘越过前高',
}

const targetCard: FirstBoardRecursiveTarget = {
  label: '目标首板',
  date: '2026-10-23',
  close: '15.39',
  limit_rate: '0.1',
  theme: '证券',
  board_count: 1,
  board_count_text: null,
  first_board_since_2019: 27,
  prior_first_board_count: 26,
  prior_eligible_non_st_count: 26,
  stage_description: '目标日之前已出现收盘越过参考前高的突破。',
  explanation: '目标首板 2026-10-23；收盘 15.39；涨停幅度比率 0.1；题材 证券；板数 1。',
}

const nearestCard: NonNullable<FirstBoardRecursiveTargetDetail['nearest_prior']> = {
  date: '2026-10-15',
  distance_sessions: 6,
  stage: 'EPISODE_NO_PULLBACK_YET',
  stage_label: '前次首板后尚未形成有效洗盘',
  label: '最近前次首板',
  explanation:
    '最近前次首板 2026-10-15，距目标 6 个交易日，状态为“前次首板后尚未形成有效洗盘”；该首板未形成有效结构，递归继续向更早的首板回溯。',
  is_recursive_anchor: false,
}

const anchorCard: NonNullable<FirstBoardRecursiveTargetDetail['recursive_anchor']> = {
  date: '2026-07-29',
  distance_sessions: 60,
  stage: 'ALREADY_REBROKEN_BEFORE_TARGET',
  stage_label: '目标前已经越过前高',
  reference_peak_date: '2026-08-05',
  reference_peak: '15.39',
  pullback_low_date: '2026-08-20',
  pullback_low: '13.52',
  pullback_pct: '12.150747238466542',
  first_close_break_date: '2026-09-01',
  target_close_vs_reference_pct: '12.15',
  selection_reason: 'RECURSIVE_ACTIVE_EPISODE',
  selection_reason_label: '回溯到更早的有效结构',
  label: '递归锚点',
  explanation:
    '递归锚点 2026-07-29；距目标 60 个交易日；参考高点 P=15.39（2026-08-05）；回调低点 L=13.52（2026-08-20），回调 12.15%；首次收盘突破 2026-09-01；结果为“目标前已经越过前高”。',
}

const legacyCandidate: FirstBoardRecursiveCandidate = {
  candidate_date: '2019-06-19',
  rank_oldest: 1,
  rank_nearest: 29,
  stage: 'EPISODE_NO_PULLBACK_YET',
  stage_label: '前次首板后尚未形成有效洗盘',
  limit_rate: '0.1',
  anchor_session_distance: 900,
  reference_peak_date: null,
  reference_peak: null,
  pullback_low_date: null,
  pullback_low: null,
  pullback_pct: null,
  first_close_break_date: null,
  target_close_vs_reference_pct: null,
  is_selected_anchor: false,
  is_legacy_anchor: true,
  selection_reason: 'EARLIEST_ACTIVE_EPISODE',
  selection_reason_label: '旧规则：最早有效结构（仅审计）',
  relation_status: null,
  relation_status_label: null,
  price_reasons: [],
  price_diagnostic: null,
}

const selectedCandidate: FirstBoardRecursiveCandidate = {
  ...legacyCandidate,
  candidate_date: '2026-07-29',
  rank_oldest: 4,
  rank_nearest: 2,
  reference_peak_date: '2026-08-05',
  reference_peak: '15.39',
  pullback_low_date: '2026-08-20',
  pullback_low: '13.52',
  pullback_pct: '12.150747238466542',
  first_close_break_date: '2026-09-01',
  target_close_vs_reference_pct: '12.15',
  is_selected_anchor: true,
  is_legacy_anchor: false,
  selection_reason: 'RECURSIVE_ACTIVE_EPISODE',
  selection_reason_label: '回溯到更早的有效结构',
  relation_status: 'ALREADY_CLOSED_ABOVE_REFERENCE_BEFORE_TARGET',
  relation_status_label: '目标前已收盘越过前高',
}

const auditCard: FirstBoardRecursiveTargetDetail['audit'] = {
  code_correction_from: null,
  code_correction_to: null,
  legacy_anchor_date: '2019-06-19',
  legacy_anchor_stage: 'EPISODE_REATTACK_BELOW_REFERENCE',
  legacy_anchor_stage_label: '洗盘后回攻但未越过前高',
  legacy_selection_reason: 'EARLIEST_ACTIVE_EPISODE',
  legacy_selection_reason_label: '旧规则：最早有效结构（仅审计）',
  relation_status: 'ALREADY_CLOSED_ABOVE_REFERENCE_BEFORE_TARGET',
  relation_status_label: '目标前已收盘越过前高',
  diagnostic_codes: ['LEGACY_ANCHOR_CORRECTED'],
  diagnostic_detail: null,
}

function detailFixture(): FirstBoardRecursiveTargetDetail {
  return {
    snapshot: snapshotMeta,
    summary: targetSummary,
    target: targetCard,
    nearest_prior: nearestCard,
    recursive_anchor: anchorCard,
    timeline: [anchor, skipped, firstBreak, nearestPrior, target],
    earlier_first_boards: earlierBoards(),
    candidates: [legacyCandidate, selectedCandidate],
    audit: auditCard,
    uses_forward_data: false,
  }
}

function noAnchorDetail(): FirstBoardRecursiveTargetDetail {
  return {
    ...detailFixture(),
    summary: {
      ...targetSummary,
      nearest_prior_date: null,
      nearest_prior_stage: null,
      nearest_prior_stage_label: null,
      anchor_date: null,
      anchor_distance_sessions: null,
      result_stage: 'NO_ACTIVE_PRIOR_EPISODE',
      result_stage_label: '无有效前次首板事件链',
      selection_reason: 'NO_PRIOR_ANCHOR',
      selection_reason_label: '无更早首板可作锚点',
      layers_diverge: false,
      relation_status: null,
      relation_status_label: null,
    },
    target: {
      ...targetCard,
      first_board_since_2019: 1,
      prior_first_board_count: 0,
      prior_eligible_non_st_count: 0,
      stage_description: '2019 年以来没有可作为锚点的前次首板，无从递归。',
      explanation: '目标首板 2026-10-23；收盘 3.68；板数 1。',
    },
    nearest_prior: null,
    recursive_anchor: null,
    timeline: [target],
    earlier_first_boards: [],
    candidates: [],
    audit: {
      ...auditCard,
      legacy_anchor_date: null,
      legacy_anchor_stage: null,
      legacy_anchor_stage_label: null,
      legacy_selection_reason: null,
      legacy_selection_reason_label: null,
      diagnostic_codes: [],
    },
  }
}

function renderPanel(props: Record<string, unknown>) {
  return renderToString(createSSRApp(FirstBoardRecursivePanel, props))
}

describe('first-board recursive panel rendering', () => {
  it('keeps 2019 legacy history out of the recursive window', async () => {
    const html = await renderPanel({ detail: detailFixture(), status: 'ready', failure: null })
    const timeline = html.match(/<ol[^>]*>([\s\S]*?)<\/ol>/)

    expect(timeline).not.toBeNull()
    expect(timeline?.[1]).not.toContain('2019-06-19')
    expect(html).toContain('2019-06-19')
    expect(html).toContain(
      '更早的合格前次首板（26 条，默认折叠，早于递归锚点，不在本轮递归窗口内）',
    )
    expect(html).toContain(EARLIER_HISTORY_SCOPE_NOTE)
    expect(html).toContain(LEGACY_ANCHOR_MARK)
    expect(html).toContain(LAYERS_DIVERGE_TEXT)
    expect(html).not.toMatch(/<details[^>]*\sopen/)
  })

  it('shows a prominent date-mismatch warning only after the frozen target day', async () => {
    const after = await renderPanel({
      detail: detailFixture(),
      status: 'ready',
      failure: null,
      reviewDate: '2026-10-26',
    })
    const same = await renderPanel({
      detail: detailFixture(),
      status: 'ready',
      failure: null,
      reviewDate: '2026-10-23',
    })

    expect(after).toContain('role="status"')
    expect(after).toContain('复盘日与冻结快照目标日不一致')
    expect(after).toContain('当前复盘日 2026-10-26 晚于冻结快照目标日 2026-10-23')
    expect(same).not.toContain('复盘日与冻结快照目标日不一致')
    expect(same).not.toContain('role="status"')
  })

  it('renders no-anchor and no-prior copy without a missing-field wording', async () => {
    const html = await renderPanel({ detail: noAnchorDetail(), status: 'ready', failure: null })

    expect(html).toContain(NO_PRIOR_FIRST_BOARD_TEXT)
    expect(html).toContain('2019 年以来没有可作为锚点的前次首板，无从递归。')
    expect(html).not.toContain('缺失')
    expect(html).not.toContain('更早的合格前次首板')
    expect(html).not.toContain(LAYERS_DIVERGE_TEXT)
  })

  it('keeps loading, not-imported, failure and out-of-snapshot states distinct', async () => {
    const loading = await renderPanel({ detail: null, status: 'loading', failure: null })
    const unavailable = await renderPanel({ detail: null, status: 'unavailable', failure: null })
    const failed = await renderPanel({
      detail: null,
      status: 'failure',
      failure: '后台暂不可用',
      requestId: 'req-7',
    })
    const missing = await renderPanel({ detail: null, status: 'missing', failure: null })

    expect(loading).toContain('正在读取首板递归结构')
    expect(unavailable).toContain('尚未导入首板递归冻结快照')
    expect(failed).toContain('后台暂不可用')
    expect(failed).toContain('请求编号 req-7')
    expect(missing).toContain('该股票不在已导入的首板递归冻结快照内')
  })
})

const reviewRow: LimitUpReviewRow = {
  date: '2026-10-23',
  symbol: '002945.SZ',
  name: '华林证券',
  board_category: 'main',
  sector: '证券',
  status: 'limit_up',
  boards: 1,
  boards_as_of_date: '2026-10-23',
  limit_up_time: '09:35:00',
  limit_up_time_as_of_date: '2026-10-23',
  broken_kind: null,
  change_pct: '10.00',
  one_word_board: false,
}

function renderDetail(overrides: Record<string, unknown> = {}) {
  return renderToString(
    createSSRApp(LimitUpDetail, {
      row: reviewRow,
      note: '',
      stockSeries: null,
      stockLoading: false,
      stockFailure: null,
      facts: null,
      factsLoading: false,
      factsFailure: null,
      intradayBars: [],
      intradayTradingDay: null,
      intradayLoading: false,
      intradayFailure: null,
      firstBoardEvents: null,
      firstBoardLoading: false,
      firstBoardFailure: null,
      ...overrides,
    }),
  )
}

describe('first-board recursive tab assembly', () => {
  it('renders the view switch for a covered stock on the frozen target day', async () => {
    const html = await renderDetail({ recursiveStatus: 'ready', recursiveDetail: detailFixture() })

    expect(html).toContain('行情与事件')
    expect(html).toContain('首板递归')
    expect(html).toContain('个股走势')
  })

  it('hides the switch for a review day before the frozen target day', async () => {
    const html = await renderDetail({
      row: { ...reviewRow, date: '2026-10-21' },
      recursiveStatus: 'ready',
      recursiveDetail: detailFixture(),
    })

    expect(html).not.toContain('首板递归')
    expect(html).toContain('个股走势')
  })

  it('keeps the switch for a review day after the frozen target day', async () => {
    const html = await renderDetail({
      row: { ...reviewRow, date: '2026-10-26' },
      recursiveStatus: 'ready',
      recursiveDetail: detailFixture(),
    })

    expect(html).toContain('首板递归')
  })

  it('hides the switch while loading, when idle and when the stock is out of snapshot', async () => {
    const loading = await renderDetail({ recursiveStatus: 'loading' })
    const missing = await renderDetail({ recursiveStatus: 'missing' })
    const idle = await renderDetail()

    for (const html of [loading, missing, idle]) {
      expect(html).not.toContain('首板递归')
      expect(html).toContain('个股走势')
    }
  })

  it('mounts the panel with the date warning so dropping :review-date cannot pass', async () => {
    const after = await renderDetail({
      row: { ...reviewRow, date: '2026-10-26' },
      recursiveStatus: 'ready',
      recursiveDetail: detailFixture(),
      initialView: 'recursive',
    })

    expect(after).toContain('role="status"')
    expect(after).toContain('复盘日与冻结快照目标日不一致')
    expect(after).toContain('当前复盘日 2026-10-26 晚于冻结快照目标日 2026-10-23')
    expect(after).not.toContain('个股走势')
  })

  it('mounts the panel on the frozen target day without a date warning', async () => {
    const same = await renderDetail({
      row: { ...reviewRow, date: '2026-10-23' },
      recursiveStatus: 'ready',
      recursiveDetail: detailFixture(),
      initialView: 'recursive',
    })

    expect(same).toContain('首板递归')
    expect(same).not.toContain('复盘日与冻结快照目标日不一致')
    expect(same).not.toContain('role="status"')
    expect(same).not.toContain('个股走势')
  })
})
