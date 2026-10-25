<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../AppIcon'
import {
  EARLIER_HISTORY_NOTE,
  EARLIER_HISTORY_SCOPE_NOTE,
  LEGACY_ANCHOR_NOTE,
  NEAREST_PRIOR_FALLBACK_LABEL,
  NO_PRIOR_FIRST_BOARD_NOTE,
  NO_PRIOR_FIRST_BOARD_TEXT,
  RECURSIVE_ANCHOR_FALLBACK_LABEL,
  anchorAbsentExplanation,
  candidateAnchorMark,
  candidateLegacyMark,
  earlierHistoryTitle,
  formatRecursiveBoardCount,
  formatRecursiveLimitRate,
  formatRecursiveNumber,
  formatRecursivePercent,
  formatRecursivePrice,
  formatRecursiveSessionDistance,
  layersDivergeHint,
  recursiveDateMismatchWarning,
  recursiveNodeTone,
  recursiveStageTone,
  splitRecursiveHistory,
  type FirstBoardRecursiveStatus,
  type FirstBoardRecursiveTargetDetail,
} from '../../market/first-board-recursive'

const props = defineProps<{
  detail: FirstBoardRecursiveTargetDetail | null
  status: FirstBoardRecursiveStatus
  failure: string | null
  reviewDate?: string | null
  requestId?: string | null
}>()
const emit = defineEmits<{ retry: [] }>()

const loading = computed(() => props.status === 'idle' || props.status === 'loading')

const model = computed(() => {
  const detail = props.detail
  if (!detail) return null
  const history = splitRecursiveHistory(
    detail.timeline,
    detail.earlier_first_boards,
    detail.recursive_anchor?.date ?? null,
  )
  const nearestStage = detail.nearest_prior?.stage ?? detail.summary.nearest_prior_stage
  const nearestStageLabel =
    detail.nearest_prior?.stage_label ??
    detail.summary.nearest_prior_stage_label ??
    (detail.summary.nearest_prior_date !== null ? '阶段未知' : NO_PRIOR_FIRST_BOARD_TEXT)
  return {
    meta: detail.snapshot,
    summary: detail.summary,
    target: detail.target,
    nearestPrior: detail.nearest_prior,
    nearestStage,
    nearestStageLabel,
    nearestLabel: detail.nearest_prior?.label ?? NEAREST_PRIOR_FALLBACK_LABEL,
    anchor: detail.recursive_anchor,
    anchorLabel: detail.recursive_anchor?.label ?? RECURSIVE_ANCHOR_FALLBACK_LABEL,
    history,
    candidates: detail.candidates,
    audit: detail.audit,
    anchorAbsent: anchorAbsentExplanation(detail.target.stage_description),
    divergeHint: layersDivergeHint(detail.summary.layers_diverge),
    earlierTitle: earlierHistoryTitle(history.earlier.length),
  }
})

/** M2: a review day after the frozen target day must warn prominently, not in tiny print. */
const dateWarning = computed(() => {
  const snapshotDate = model.value?.meta.trade_date ?? null
  return snapshotDate ? recursiveDateMismatchWarning(props.reviewDate ?? null, snapshotDate) : ''
})
</script>

<template>
  <section class="recursive-panel" aria-label="首板递归结构">
    <div v-if="loading" class="recursive-state">正在读取首板递归结构…</div>
    <div
      v-else-if="status === 'failure'"
      class="recursive-state recursive-state--error"
      role="alert"
    >
      <AppIcon name="alert-triangle" :size="18" />
      <b>首板递归结构读取失败</b>
      <span>{{ failure }}</span>
      <small v-if="requestId">请求编号 {{ requestId }}</small>
      <button type="button" @click="emit('retry')">重试首板递归</button>
    </div>
    <div v-else-if="status === 'unavailable'" class="recursive-state" role="status">
      <AppIcon name="alert-triangle" :size="18" />
      <b>尚未导入首板递归冻结快照</b>
      <span>后台还没有导入该冻结研究结果，本次没有可展示的递归结构；不会用其他数据替代。</span>
      <button type="button" @click="emit('retry')">重新检查</button>
    </div>
    <div v-else-if="!model" class="recursive-state" role="status">
      <b>该股票不在已导入的首板递归冻结快照内</b>
      <span>冻结快照只覆盖主板符合条件的目标，这不是读取失败。</span>
    </div>
    <template v-else>
      <div v-if="dateWarning" class="recursive-warning" role="status">
        <AppIcon name="alert-triangle" :size="18" />
        <div>
          <b>复盘日与冻结快照目标日不一致</b>
          <span>{{ dateWarning }}</span>
        </div>
      </div>
      <header class="recursive-head">
        <div class="section-title">
          <div>
            <h3>首板递归</h3>
            <p>
              冻结快照 {{ model.meta.trade_date }} · {{ model.meta.board_scope_label }} ·
              {{ model.meta.status_label }}
            </p>
          </div>
          <span>
            {{ model.meta.counts.targets }} 只目标 · 首板
            {{ model.meta.counts.first_boards_since_2019 }} 次 · 候选链接
            {{ model.meta.counts.candidate_links }} 条
          </span>
        </div>
        <p class="recursive-caveat">
          只展示该冻结快照的既有结论，不随复盘日期重算；冻结快照自身未使用未来数据。
        </p>
      </header>

      <section class="recursive-section">
        <div class="section-title">
          <h3>两层结论</h3>
          <span>最近状态 / 递归结果</span>
        </div>
        <div class="layer-badges">
          <div class="layer-badge">
            <span class="layer-label">最近状态</span>
            <span
              class="tone-badge"
              :class="`tone-badge--${recursiveStageTone(model.nearestStage)}`"
            >
              {{ model.nearestStageLabel }}
            </span>
            <small>{{ model.summary.nearest_prior_date ?? '—' }}</small>
          </div>
          <div class="layer-badge">
            <span class="layer-label">递归结果</span>
            <span
              class="tone-badge"
              :class="`tone-badge--${recursiveStageTone(model.summary.result_stage)}`"
            >
              {{ model.summary.result_stage_label }}
            </span>
            <small>
              {{ model.summary.anchor_date ? `锚点 ${model.summary.anchor_date}` : '无递归锚点' }}
            </small>
          </div>
        </div>
        <p v-if="model.summary.relation_status_label" class="recursive-line">
          递归层关系：{{ model.summary.relation_status_label }}
        </p>
        <div v-if="model.divergeHint" class="recursive-notice">
          <AppIcon name="alert-triangle" :size="15" />
          <span>{{ model.divergeHint }}</span>
        </div>
      </section>

      <section class="recursive-section">
        <div class="section-title">
          <h3>{{ model.target.label }}</h3>
          <span>{{ model.target.date }}</span>
        </div>
        <dl class="facts">
          <div>
            <dt>日期</dt>
            <dd>{{ model.target.date }}</dd>
          </div>
          <div>
            <dt>收盘</dt>
            <dd>{{ formatRecursivePrice(model.target.close) }}</dd>
          </div>
          <div>
            <dt>涨停幅度</dt>
            <dd>{{ formatRecursiveLimitRate(model.target.limit_rate) }}</dd>
          </div>
          <div>
            <dt>板数</dt>
            <dd>{{ formatRecursiveBoardCount(model.target) }}</dd>
          </div>
          <div>
            <dt>题材</dt>
            <dd>{{ model.target.theme ?? '—' }}</dd>
          </div>
          <div>
            <dt>2019 年以来首板次数</dt>
            <dd>{{ formatRecursiveNumber(model.target.first_board_since_2019) }}</dd>
          </div>
          <div>
            <dt>此前首板次数</dt>
            <dd>{{ formatRecursiveNumber(model.target.prior_first_board_count) }}</dd>
          </div>
          <div>
            <dt>合格非 ST 前次首板</dt>
            <dd>{{ formatRecursiveNumber(model.target.prior_eligible_non_st_count) }}</dd>
          </div>
        </dl>
        <p class="recursive-line">{{ model.target.explanation }}</p>
        <p class="recursive-line">{{ model.target.stage_description }}</p>
      </section>

      <section class="recursive-section">
        <div class="section-title">
          <h3>{{ model.nearestLabel }}</h3>
          <span>两层中的最近层</span>
        </div>
        <template v-if="model.nearestPrior">
          <dl class="facts">
            <div>
              <dt>日期</dt>
              <dd>{{ model.nearestPrior.date }}</dd>
            </div>
            <div>
              <dt>距目标</dt>
              <dd>{{ formatRecursiveSessionDistance(model.nearestPrior.distance_sessions) }}</dd>
            </div>
            <div>
              <dt>阶段</dt>
              <dd>{{ model.nearestPrior.stage_label ?? '—' }}</dd>
            </div>
            <div>
              <dt>是否递归锚点</dt>
              <dd>
                {{
                  model.nearestPrior.is_recursive_anchor ? `是，同时作为${model.anchorLabel}` : '否'
                }}
              </dd>
            </div>
          </dl>
          <p class="recursive-line">{{ model.nearestPrior.explanation }}</p>
        </template>
        <template v-else>
          <p class="recursive-empty">{{ NO_PRIOR_FIRST_BOARD_TEXT }}</p>
          <p class="recursive-line">{{ NO_PRIOR_FIRST_BOARD_NOTE }}</p>
        </template>
      </section>

      <section class="recursive-section">
        <div class="section-title">
          <h3>{{ model.anchorLabel }}</h3>
          <span>本轮递归窗口起点</span>
        </div>
        <template v-if="model.anchor">
          <dl class="facts">
            <div>
              <dt>锚点日期</dt>
              <dd>{{ model.anchor.date }}</dd>
            </div>
            <div>
              <dt>距目标</dt>
              <dd>{{ formatRecursiveSessionDistance(model.anchor.distance_sessions) }}</dd>
            </div>
            <div>
              <dt>阶段</dt>
              <dd>{{ model.anchor.stage_label }}</dd>
            </div>
            <div>
              <dt>参考高点 P</dt>
              <dd>
                {{ formatRecursivePrice(model.anchor.reference_peak) }}
                <small v-if="model.anchor.reference_peak_date">
                  {{ model.anchor.reference_peak_date }}
                </small>
              </dd>
            </div>
            <div>
              <dt>回调低点 L</dt>
              <dd>
                {{ formatRecursivePrice(model.anchor.pullback_low) }}
                <small v-if="model.anchor.pullback_low_date">
                  {{ model.anchor.pullback_low_date }}
                </small>
              </dd>
            </div>
            <div>
              <dt>回调幅度</dt>
              <dd>{{ formatRecursivePercent(model.anchor.pullback_pct) }}</dd>
            </div>
            <div>
              <dt>首次收盘突破</dt>
              <dd>{{ model.anchor.first_close_break_date ?? '—' }}</dd>
            </div>
            <div>
              <dt>目标收盘相对 P</dt>
              <dd>{{ formatRecursivePercent(model.anchor.target_close_vs_reference_pct) }}</dd>
            </div>
            <div>
              <dt>选中原因</dt>
              <dd>{{ model.anchor.selection_reason_label }}</dd>
            </div>
          </dl>
          <p class="recursive-line">{{ model.anchor.explanation }}</p>
        </template>
        <template v-else>
          <p class="recursive-empty">{{ model.anchorAbsent }}</p>
          <p class="recursive-line">递归结果：{{ model.summary.result_stage_label }}</p>
        </template>
      </section>

      <section class="recursive-section">
        <div class="section-title">
          <h3>递归窗口时间线</h3>
          <span>{{ model.history.window.length }} 个节点 · 锚点至目标</span>
        </div>
        <ol v-if="model.history.window.length" class="timeline" role="list">
          <li
            v-for="item in model.history.window"
            :key="`${item.order}-${item.date}-${item.role}`"
            class="timeline-node"
            :class="`timeline-node--${recursiveNodeTone(item.role)}`"
          >
            <header>
              <time>{{ item.date }}</time>
              <span class="node-role">{{ item.label }}</span>
              <span v-if="item.stage_label" class="node-stage">{{ item.stage_label }}</span>
            </header>
            <div class="node-facts">
              <span v-if="item.limit_rate !== null">
                涨停幅度 {{ formatRecursiveLimitRate(item.limit_rate) }}
              </span>
              <span v-if="item.reference_peak !== null">
                P {{ formatRecursivePrice(item.reference_peak) }}
              </span>
              <span v-if="item.pullback_low !== null">
                L {{ formatRecursivePrice(item.pullback_low) }}
              </span>
              <span v-if="item.first_close_break_date !== null">
                首破 {{ item.first_close_break_date }}
              </span>
              <span v-if="item.target_close_vs_reference_pct !== null">
                相对 P {{ formatRecursivePercent(item.target_close_vs_reference_pct) }}
              </span>
            </div>
            <p v-if="item.note" class="node-note">{{ item.note }}</p>
          </li>
        </ol>
        <p v-else class="recursive-empty">递归窗口内没有可展示的节点。</p>
      </section>

      <details v-if="model.history.earlier.length" class="recursive-fold">
        <summary>{{ model.earlierTitle }}</summary>
        <div class="fold-body">
          <p class="fold-note">{{ EARLIER_HISTORY_NOTE }}</p>
          <p class="fold-note">{{ EARLIER_HISTORY_SCOPE_NOTE }}</p>
          <ul class="earlier-list">
            <li v-for="item in model.history.earlier" :key="item.date">
              <time>{{ item.date }}</time>
              <span>{{ item.stage_label }}</span>
            </li>
          </ul>
        </div>
      </details>

      <details class="recursive-fold">
        <summary>
          合格候选（{{ model.candidates.length }} 条；历史首板
          {{ formatRecursiveNumber(model.target.first_board_since_2019) }} 次，快照候选链接
          {{ model.meta.counts.candidate_links }} 条）
        </summary>
        <div class="fold-body">
          <div v-if="model.candidates.length" class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>候选日期</th>
                  <th>阶段</th>
                  <th>距目标间隔</th>
                  <th>参考高点 P</th>
                  <th>回调低点 L</th>
                  <th>回调幅度</th>
                  <th>首次收盘突破</th>
                  <th>目标收盘相对 P</th>
                  <th>选中原因</th>
                  <th>审计标记</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in model.candidates"
                  :key="item.candidate_date"
                  :class="{ 'row--legacy': item.is_legacy_anchor }"
                >
                  <td>
                    <time>{{ item.candidate_date }}</time>
                  </td>
                  <td>{{ item.stage_label }}</td>
                  <td>{{ formatRecursiveSessionDistance(item.anchor_session_distance) }}</td>
                  <td>{{ formatRecursivePrice(item.reference_peak) }}</td>
                  <td>{{ formatRecursivePrice(item.pullback_low) }}</td>
                  <td>{{ formatRecursivePercent(item.pullback_pct) }}</td>
                  <td>{{ item.first_close_break_date ?? '—' }}</td>
                  <td>{{ formatRecursivePercent(item.target_close_vs_reference_pct) }}</td>
                  <td>{{ item.selection_reason_label ?? '—' }}</td>
                  <td>
                    <span
                      v-if="candidateAnchorMark(item.is_selected_anchor)"
                      class="mark mark--anchor"
                    >
                      {{ candidateAnchorMark(item.is_selected_anchor) }}
                    </span>
                    <span
                      v-if="candidateLegacyMark(item.is_legacy_anchor)"
                      class="mark mark--legacy"
                    >
                      {{ candidateLegacyMark(item.is_legacy_anchor) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="recursive-empty">没有合格候选。</p>
          <p class="fold-note">{{ LEGACY_ANCHOR_NOTE }}</p>
        </div>
      </details>

      <details class="recursive-fold">
        <summary>技术审计（代码修正 / 旧规则锚点 / 诊断码）</summary>
        <div class="fold-body">
          <dl class="facts facts--audit">
            <div>
              <dt>代码修正</dt>
              <dd>
                {{
                  model.audit.code_correction_from && model.audit.code_correction_to
                    ? `${model.audit.code_correction_from} → ${model.audit.code_correction_to}`
                    : '—'
                }}
              </dd>
            </div>
            <div>
              <dt>旧规则锚点</dt>
              <dd>{{ model.audit.legacy_anchor_date ?? '—' }}</dd>
            </div>
            <div>
              <dt>旧规则阶段</dt>
              <dd>{{ model.audit.legacy_anchor_stage_label ?? '—' }}</dd>
            </div>
            <div>
              <dt>旧规则选中原因</dt>
              <dd>{{ model.audit.legacy_selection_reason_label ?? '—' }}</dd>
            </div>
            <div>
              <dt>关系状态</dt>
              <dd>{{ model.audit.relation_status_label ?? '—' }}</dd>
            </div>
            <div>
              <dt>诊断码</dt>
              <dd>
                {{
                  model.audit.diagnostic_codes.length
                    ? model.audit.diagnostic_codes.join('、')
                    : '—'
                }}
              </dd>
            </div>
          </dl>
          <p v-if="model.audit.diagnostic_detail" class="fold-note">
            {{ model.audit.diagnostic_detail }}
          </p>
          <p class="fold-note">{{ LEGACY_ANCHOR_NOTE }}</p>
          <dl class="facts facts--audit">
            <div>
              <dt>冻结来源</dt>
              <dd>{{ model.meta.source.source_kind }}</dd>
            </div>
            <div>
              <dt>校验状态</dt>
              <dd>{{ model.meta.source.verification_status_label }}</dd>
            </div>
            <div>
              <dt>来源 SHA256</dt>
              <dd class="mono">{{ model.meta.source.source_sha256 }}</dd>
            </div>
            <div>
              <dt>产物 SHA256</dt>
              <dd class="mono">{{ model.meta.source.artifact_sha256 }}</dd>
            </div>
          </dl>
        </div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.recursive-panel {
  min-width: 0;
  display: grid;
  gap: 14px;
}

.recursive-state {
  min-height: 240px;
  padding: 20px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 7px;
  font-size: 12.5px;
  line-height: 1.55;
  text-align: center;
}

.recursive-state b {
  color: var(--fg2);
  font-size: 14px;
}

.recursive-state small {
  font-family: var(--mono);
}

.recursive-state--error {
  border-color: color-mix(in oklab, var(--up) 34%, var(--border));
  color: var(--up);
}

.recursive-state button {
  min-height: 32px;
  margin-top: 4px;
  padding: 3px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  font-size: 12px;
  cursor: pointer;
}

.recursive-head {
  min-width: 0;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  display: grid;
  gap: 6px;
}

.recursive-caveat {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.55;
}

.recursive-section {
  min-width: 0;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  display: grid;
  gap: 9px;
}

.section-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.section-title h3 {
  margin: 0;
  color: var(--fg2);
  font-size: 14px;
}

.section-title span {
  color: var(--muted);
  font-size: 11.5px;
  text-align: right;
  line-height: 1.5;
}

.section-title p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.5;
}

.layer-badges {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.layer-badge {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  display: grid;
  justify-items: start;
  gap: 6px;
}

.layer-label {
  color: var(--muted);
  font-size: 11px;
}

.layer-badge small {
  color: var(--muted);
  font: 10.5px var(--mono);
}

.tone-badge {
  max-width: 100%;
  padding: 3px 9px;
  border: 1px solid var(--border2);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.4;
  color: var(--fg2);
  overflow-wrap: anywhere;
}

.tone-badge--rebreak {
  border-color: color-mix(in oklab, var(--up) 42%, var(--border));
  background: color-mix(in oklab, var(--up) 11%, transparent);
  color: var(--up);
}

.tone-badge--direct {
  border-color: color-mix(in oklab, var(--brand) 46%, var(--border));
  background: color-mix(in oklab, var(--brand) 11%, transparent);
  color: var(--brand);
}

.tone-badge--reattack {
  border-color: color-mix(in oklab, var(--warn) 42%, var(--border));
  background: color-mix(in oklab, var(--warn) 11%, transparent);
  color: var(--warn);
}

.tone-badge--rebroken {
  border-color: color-mix(in oklab, var(--accent) 42%, var(--border));
  background: color-mix(in oklab, var(--accent) 11%, transparent);
  color: var(--accent);
}

.tone-badge--no-prior {
  border-color: color-mix(in oklab, var(--vol) 48%, var(--border));
  background: color-mix(in oklab, var(--vol) 12%, transparent);
  color: var(--vol);
}

.tone-badge--insufficient {
  border-color: color-mix(in oklab, var(--flat) 52%, var(--border));
  background: color-mix(in oklab, var(--flat) 12%, transparent);
  color: var(--flat);
}

.tone-badge--unknown {
  color: var(--muted);
}

.recursive-line {
  margin: 0;
  color: var(--fg2);
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.recursive-empty {
  margin: 0;
  padding: 12px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.55;
}

.recursive-notice {
  padding: 6px 9px;
  border: 1px solid color-mix(in oklab, var(--warn) 34%, var(--border));
  border-radius: var(--radius-sm);
  background: color-mix(in oklab, var(--warn) 8%, transparent);
  color: var(--warn);
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 12px;
  line-height: 1.55;
}

.recursive-warning {
  padding: 10px 12px;
  border: 1px solid color-mix(in oklab, var(--warn) 68%, var(--border));
  border-radius: var(--radius-sm);
  background: color-mix(in oklab, var(--warn) 16%, transparent);
  color: var(--warn);
  display: flex;
  align-items: flex-start;
  gap: 9px;
  font-size: 12.5px;
  line-height: 1.6;
}

.recursive-warning b {
  display: block;
  margin-bottom: 2px;
  font-size: 13px;
}

.recursive-warning > div {
  min-width: 0;
}

.recursive-warning span {
  display: block;
  color: var(--fg);
  overflow-wrap: anywhere;
}

.facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 14px;
  margin: 0;
}

.facts > div {
  min-width: 0;
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 3px 7px;
  padding: 5px 0;
}

.facts dt {
  color: var(--muted);
  font-size: 11px;
  flex: none;
}

.facts dd {
  margin: 0;
  min-width: 0;
  color: var(--fg);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.facts small {
  color: var(--muted);
  font-size: 10px;
  font-family: var(--mono);
}

.facts--audit {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.facts dd.mono {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--muted);
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.timeline-node {
  position: relative;
  min-width: 0;
  padding: 8px 10px 8px 22px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.timeline-node::before {
  content: '';
  position: absolute;
  left: 9px;
  top: 14px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--flat);
}

.timeline-node--anchor::before {
  background: var(--accent);
}

.timeline-node--nearest::before {
  background: var(--warn);
}

.timeline-node--break::before {
  background: var(--vol);
}

.timeline-node--target::before {
  background: var(--up);
}

.timeline-node header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.timeline-node time {
  color: var(--accent);
  font: 11px var(--mono);
}

.node-role {
  padding: 1px 7px;
  border: 1px solid var(--border2);
  border-radius: 999px;
  color: var(--fg2);
  font-size: 10.5px;
}

.node-stage {
  color: var(--muted);
  font-size: 11px;
}

.node-facts {
  margin-top: 5px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  color: var(--muted);
  font: 11px var(--mono);
}

.node-note {
  margin: 5px 0 0;
  color: var(--fg2);
  font-size: 11.5px;
  line-height: 1.55;
}

.recursive-fold {
  min-width: 0;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.recursive-fold summary {
  padding: 9px 0;
  color: var(--fg2);
  font-size: 12px;
  line-height: 1.5;
  cursor: pointer;
}

.fold-body {
  padding: 0 0 10px;
  display: grid;
  gap: 8px;
}

.fold-note {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.55;
}

.earlier-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 240px;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  scrollbar-gutter: stable;
  display: grid;
  gap: 4px;
}

.earlier-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  color: var(--fg2);
  font-size: 11.5px;
}

.earlier-list time {
  color: var(--accent);
  font-family: var(--mono);
}

.table-scroll {
  min-width: 0;
  overflow-x: auto;
  scrollbar-gutter: stable;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

th,
td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}

th {
  color: var(--muted);
  font-weight: 600;
}

td time {
  color: var(--accent);
  font-family: var(--mono);
}

tbody tr td {
  color: var(--fg2);
}

tbody tr.row--legacy td {
  color: var(--muted);
}

.mark {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid var(--border2);
  border-radius: 999px;
  font-size: 9.5px;
  white-space: nowrap;
}

.mark--anchor {
  border-color: color-mix(in oklab, var(--accent) 42%, var(--border));
  color: var(--accent);
}

.mark--legacy {
  border-color: color-mix(in oklab, var(--warn) 42%, var(--border));
  color: var(--warn);
}

@media (max-width: 760px) {
  .facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .facts--audit {
    grid-template-columns: 1fr;
  }

  .layer-badges {
    grid-template-columns: 1fr;
  }

  .section-title {
    flex-wrap: wrap;
  }

  .section-title span {
    text-align: left;
  }
}
</style>
