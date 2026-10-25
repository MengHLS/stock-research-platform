"""Chinese presentation vocabulary and explanation templates for the taxonomy.

The database stores raw enum keys only. This module owns the static vocabulary
(stage/reason/relation labels, stage descriptions, timeline role labels) and the
two explanation templates below; the service passes stored values in and
assembles the dynamic target-card sentence itself, so wording changes cannot
leave the stored snapshot and the served text out of sync.

The stage wordings intentionally match the frozen delivery's own
``selectedStageZh`` / ``nearestStageZh`` columns instead of inventing a second
vocabulary; the real-delivery API test compares every delivered row so a drift
fails the suite. Percentages in sentences are rendered with at most two decimals
(``percent_text``) while the JSON facts keep the unrounded decimal strings.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# Result stage of the selected (recursive) layer: one value per target.
EPISODE_REATTACK_BELOW_REFERENCE = "EPISODE_REATTACK_BELOW_REFERENCE"
ALREADY_REBROKEN_BEFORE_TARGET = "ALREADY_REBROKEN_BEFORE_TARGET"
CHAIN_INFORMATION_INSUFFICIENT = "CHAIN_INFORMATION_INSUFFICIENT"
EPISODE_FIRST_CLOSE_REBREAK = "EPISODE_FIRST_CLOSE_REBREAK"
EPISODE_TARGET_DAY_DIRECT_BREAK = "EPISODE_TARGET_DAY_DIRECT_BREAK"
NO_ACTIVE_PRIOR_EPISODE = "NO_ACTIVE_PRIOR_EPISODE"

# Candidate-only stages: a prior first board may stop before a full structure forms.
EPISODE_NO_PULLBACK_YET = "EPISODE_NO_PULLBACK_YET"
EPISODE_WEAK_OR_NO_RECOVERY = "EPISODE_WEAK_OR_NO_RECOVERY"

RESULT_STAGES: tuple[str, ...] = (
    EPISODE_REATTACK_BELOW_REFERENCE,
    ALREADY_REBROKEN_BEFORE_TARGET,
    CHAIN_INFORMATION_INSUFFICIENT,
    EPISODE_FIRST_CLOSE_REBREAK,
    EPISODE_TARGET_DAY_DIRECT_BREAK,
    NO_ACTIVE_PRIOR_EPISODE,
)
CANDIDATE_STAGES: tuple[str, ...] = RESULT_STAGES + (
    EPISODE_NO_PULLBACK_YET,
    EPISODE_WEAK_OR_NO_RECOVERY,
)

# Why the recursive layer stopped where it did: one value per target.
NEAREST_ACTIVE_EPISODE = "NEAREST_ACTIVE_EPISODE"
RECURSIVE_ACTIVE_EPISODE = "RECURSIVE_ACTIVE_EPISODE"
STRUCTURE_BREAK_STOP = "STRUCTURE_BREAK_STOP"
INFORMATION_GAP_STOP = "INFORMATION_GAP_STOP"
NO_PRIOR_ANCHOR = "NO_PRIOR_ANCHOR"

SELECTION_REASONS: tuple[str, ...] = (
    NEAREST_ACTIVE_EPISODE,
    RECURSIVE_ACTIVE_EPISODE,
    STRUCTURE_BREAK_STOP,
    INFORMATION_GAP_STOP,
    NO_PRIOR_ANCHOR,
)
# Old-rule audit key, never a current selection reason.
EARLIEST_ACTIVE_EPISODE = "EARLIEST_ACTIVE_EPISODE"

STAGE_LABELS: dict[str, str] = {
    EPISODE_REATTACK_BELOW_REFERENCE: "洗盘后回攻但未越过前高",
    ALREADY_REBROKEN_BEFORE_TARGET: "目标前已经越过前高",
    CHAIN_INFORMATION_INSUFFICIENT: "事件链信息不足",
    EPISODE_FIRST_CLOSE_REBREAK: "试盘洗盘后首次收盘突破",
    EPISODE_TARGET_DAY_DIRECT_BREAK: "目标日直接首次收盘突破（前一日尚未回升）",
    NO_ACTIVE_PRIOR_EPISODE: "无有效前次首板事件链",
    EPISODE_NO_PULLBACK_YET: "前次首板后尚未形成有效洗盘",
    EPISODE_WEAK_OR_NO_RECOVERY: "洗盘后未出现有效回攻",
}

STAGE_DESCRIPTIONS: dict[str, str] = {
    EPISODE_REATTACK_BELOW_REFERENCE: "洗盘后出现回攻，但截至目标日收盘仍未越过前高。",
    ALREADY_REBROKEN_BEFORE_TARGET: "目标日之前已出现收盘越过参考前高的突破。",
    CHAIN_INFORMATION_INSUFFICIENT: "事件链路径缺少收盘价或前收盘，无法判定结构是否成立。",
    EPISODE_FIRST_CLOSE_REBREAK: "试盘、洗盘之后首次以收盘价突破参考前高。",
    EPISODE_TARGET_DAY_DIRECT_BREAK: "目标日当天才首次收盘突破，前一日尚未回升。",
    NO_ACTIVE_PRIOR_EPISODE: "2019 年以来没有可作为锚点的前次首板，无从递归。",
    EPISODE_NO_PULLBACK_YET: "最近首板之后尚未形成有效洗盘（未出现参考高点后的回调低点）。",
    EPISODE_WEAK_OR_NO_RECOVERY: "出现回调低点后未出现有效回攻。",
}

SELECTION_REASON_LABELS: dict[str, str] = {
    NEAREST_ACTIVE_EPISODE: "最近前次首板即有效结构",
    RECURSIVE_ACTIVE_EPISODE: "回溯到更早的有效结构",
    STRUCTURE_BREAK_STOP: "向前回溯遇到结构破坏而停止",
    INFORMATION_GAP_STOP: "路径信息缺口导致停止",
    NO_PRIOR_ANCHOR: "无更早首板可作锚点",
    EARLIEST_ACTIVE_EPISODE: "旧规则：最早有效结构（仅审计）",
}

RELATION_STATUS_LABELS: dict[str, str] = {
    "ALREADY_CLOSED_ABOVE_REFERENCE_BEFORE_TARGET": "目标前已收盘越过前高",
    "VALID_FIRST_CLOSE_REBREAK": "首次收盘突破有效",
    "TARGET_CLOSE_NOT_ABOVE_REFERENCE": "洗盘后回攻但目标收盘未越过前高",
    "NO_RECOVERY_BEFORE_TARGET": "洗盘后未出现有效回攻",
    "PATH_INCOMPLETE_OR_INVALID": "事件链路径不完整或价格数据无效",
    "NO_POST_SEED_HIGH": "首板后尚未出现新的参考高点",
    "NO_FIRST_DECLINE_BEFORE_TARGET": "目标前尚未出现首次回落",
    "NO_SESSION_AFTER_REFERENCE_PEAK": "参考高点后没有可用的后续交易日",
}

BOARD_SCOPE_LABELS: dict[str, str] = {"MAINBOARD_ONLY": "主板"}

SNAPSHOT_STATUS_LABELS: dict[str, str] = {
    "PASS": "冻结研究结果，校验通过",
    "FAIL": "冻结研究结果，校验未通过",
}

TIMELINE_NODE_ROLES: tuple[str, ...] = (
    "ANCHOR",
    "SKIPPED",
    "NEAREST_PRIOR",
    "FIRST_CLOSE_BREAK",
    "TARGET",
)

TIMELINE_ROLE_LABELS: dict[str, str] = {
    "ANCHOR": "递归锚点首板",
    "SKIPPED": "被跳过的首板",
    "NEAREST_PRIOR": "最近前次首板",
    "FIRST_CLOSE_BREAK": "首次收盘突破",
    "TARGET": "目标首板",
}


def stage_label(code: str | None) -> str | None:
    """Return the verified Chinese wording, or ``None`` for an absent key."""
    if code is None:
        return None
    return STAGE_LABELS.get(code, code)


def stage_description(code: str | None) -> str | None:
    if code is None:
        return None
    return STAGE_DESCRIPTIONS.get(code, code)


def selection_reason_label(code: str | None) -> str | None:
    if code is None:
        return None
    return SELECTION_REASON_LABELS.get(code, code)


def relation_status_label(code: str | None) -> str | None:
    if code is None:
        return None
    return RELATION_STATUS_LABELS.get(code, code)


def board_scope_label(code: str) -> str:
    return BOARD_SCOPE_LABELS.get(code, code)


def snapshot_status_label(code: str) -> str:
    return SNAPSHOT_STATUS_LABELS.get(code, code)


def timeline_role_label(role: str) -> str:
    return TIMELINE_ROLE_LABELS.get(role, role)


def verification_status_label(code: str) -> str:
    return "校验通过" if code == "PASS" else code


def decimal_text(value: Decimal | None) -> str:
    """Plain decimal text without exponent or trailing zeros; missing values say so."""
    if value is None:
        return "未知"
    text = format(value.normalize(), "f")
    return text


def percent_text(value: Decimal | None) -> str:
    """Render an already-percent number with at most two decimals (12.1507 -> ``12.15%``).

    The frozen columns ``*PullbackPct`` / ``*VsReferencePct`` are stored as percent
    points, not ratios, so they must not be multiplied again.
    """
    if value is None:
        return "未知"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text or '0'}%"


def ratio_percent_text(value: Decimal | None) -> str:
    """Render a 0..1 ratio such as ``limit_rate`` as a percentage (0.1 -> ``10%``)."""
    if value is None:
        return "未知"
    return percent_text(value * 100)


def nearest_prior_explanation(
    *,
    prior_date: date,
    distance_sessions: int | None,
    stage: str | None,
    selection_reason: str | None,
    is_recursive_anchor: bool,
) -> str:
    distance = "间隔未知" if distance_sessions is None else f"距目标 {distance_sessions} 个交易日"
    status = "状态未知" if stage is None else f"状态为“{stage_label(stage)}”"
    # The recursion can stop at a gap found on an *earlier* candidate than this one,
    # so the "stopped here" wording only applies when this board is the anchor.
    information_gap = is_recursive_anchor and (
        selection_reason == INFORMATION_GAP_STOP or stage == CHAIN_INFORMATION_INSUFFICIENT
    )
    if information_gap:
        tail = "该首板候选的价格信息不足，结构是否成立无法认证；递归因信息缺口停在最近候选。"
    elif is_recursive_anchor:
        tail = "该首板本身形成有效结构，直接作为递归锚点。"
    elif selection_reason == INFORMATION_GAP_STOP or stage == CHAIN_INFORMATION_INSUFFICIENT:
        tail = "该首板价格信息不足，未作为本轮递归锚点；递归继续向更早的首板回溯。"
    else:
        tail = "该首板未形成有效结构，递归继续向更早的首板回溯。"
    return f"最近前次首板 {prior_date.isoformat()}，{distance}，{status}；{tail}"


def recursive_anchor_explanation(
    *,
    anchor_date: date,
    distance_sessions: int | None,
    stage: str,
    reference_peak_date: date | None,
    reference_peak: Decimal | None,
    pullback_low_date: date | None,
    pullback_low: Decimal | None,
    pullback_pct: Decimal | None,
    first_close_break_date: date | None,
    target_close_vs_reference_pct: Decimal | None,
    selection_reason: str,
) -> str:
    parts = [f"递归锚点 {anchor_date.isoformat()}"]
    if distance_sessions is not None:
        parts.append(f"距目标 {distance_sessions} 个交易日")
    peak = "参考高点未知"
    if reference_peak is not None:
        peak = f"参考高点 P={decimal_text(reference_peak)}"
        if reference_peak_date is not None:
            peak += f"（{reference_peak_date.isoformat()}）"
    low = "回调低点未知"
    if pullback_low is not None:
        low = f"回调低点 L={decimal_text(pullback_low)}"
        if pullback_low_date is not None:
            low += f"（{pullback_low_date.isoformat()}）"
        if pullback_pct is not None:
            low += f"，回调 {percent_text(pullback_pct)}"
    break_text = (
        f"首次收盘突破 {first_close_break_date.isoformat()}"
        if first_close_break_date is not None
        else "尚未出现首次收盘突破"
    )
    versus = (
        "目标收盘相对 P 未知"
        if target_close_vs_reference_pct is None
        else f"目标收盘相对 P {percent_text(target_close_vs_reference_pct)}"
    )
    parts.append(peak)
    parts.append(low)
    parts.append(break_text)
    parts.append(versus)
    parts.append(f"结果为“{stage_label(stage)}”")
    parts.append(f"选中原因：{selection_reason_label(selection_reason)}")
    return "；".join(parts) + "。"
