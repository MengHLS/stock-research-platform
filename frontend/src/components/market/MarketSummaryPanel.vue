<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../AppIcon'
import MarketSparkline from './MarketSparkline.vue'
import type { ReviewHistoryRow, ReviewOverview } from '../../market/review'
import { emotionRating } from '../../market/review'

const props = defineProps<{
  overview: ReviewOverview
  previous: ReviewHistoryRow | null
}>()

const assessmentLabel = computed(
  () =>
    ({
      available: '统计可评估',
      partial: '部分可评估',
      missing: '记录缺失',
    })[props.overview.summary.assessment],
)

const rating = computed(() => emotionRating(props.overview.summary.emotion_score))
const circumference = 2 * Math.PI * 46
const gaugeOffset = computed(() => {
  const score = props.overview.summary.emotion_score
  const safe = score === null || score === undefined ? 0 : Math.max(0, Math.min(100, score))
  return circumference * (1 - safe / 100)
})
const gaugeColor = computed(() => {
  if (props.overview.summary.emotion_score === null) return 'var(--flat)'
  if (rating.value.tone === 'up') return 'var(--up)'
  if (rating.value.tone === 'down') return 'var(--down)'
  return 'var(--accent)'
})

function comparison(
  current: number | null | undefined,
  previous: number | null | undefined,
  unit: string,
) {
  if (current === null || current === undefined) {
    return { main: '当前值不可评估', detail: '缺失未按零值处理', direction: 0 }
  }
  if (previous === null || previous === undefined) {
    return { main: '无可比日', detail: '前一交易日没有有效基准', direction: 0 }
  }
  const delta = current - previous
  const direction = Math.sign(delta)
  const percentage =
    previous === 0
      ? current === 0
        ? '前日为 0 · 真实持平'
        : '前日为 0'
      : `${delta > 0 ? '+' : ''}${((delta / previous) * 100).toFixed(1)}%`
  return {
    main: delta === 0 ? '较前一交易日持平' : `较前一交易日 ${delta > 0 ? '+' : ''}${delta}${unit}`,
    detail: `前日 ${previous}${unit} · ${percentage}`,
    direction,
  }
}

function seriesFacts(values: Array<number | null | undefined>, dates: string[]) {
  const known = values
    .map((value, index) => ({ value, date: dates[index] ?? '' }))
    .filter((item): item is { value: number; date: string } => Number.isFinite(item.value))
  if (!known.length) {
    return {
      median: null,
      minimum: null,
      maximum: null,
      peak: null,
      peakDate: null,
      samples: 0,
      total: dates.length,
    }
  }
  const sortedValues = known.map((item) => item.value).sort((left, right) => left - right)
  const middle = Math.floor(sortedValues.length / 2)
  const median =
    sortedValues.length % 2 === 1
      ? sortedValues[middle]
      : (sortedValues[middle - 1]! + sortedValues[middle]!) / 2
  const peak = known.reduce((best, item) => (item.value > best.value ? item : best))
  return {
    median,
    minimum: sortedValues[0],
    maximum: sortedValues.at(-1),
    peak: peak.value,
    peakDate: peak.date,
    samples: known.length,
    total: dates.length,
  }
}

function factValue(value: number | null | undefined, unit = '') {
  if (value === null || value === undefined) return '—'
  return `${Number.isInteger(value) ? String(value) : value.toFixed(1)}${unit}`
}

function factRange(
  minimum: number | null | undefined,
  maximum: number | null | undefined,
  unit: string,
) {
  if (minimum === null || minimum === undefined || maximum === null || maximum === undefined) {
    return '—'
  }
  return `${factValue(minimum, unit)}–${factValue(maximum, unit)}`
}

const metrics = computed(() => {
  const summary = props.overview.summary
  const previous = props.previous
  const recent = props.overview.history.slice(-10)
  const dates = recent.map((row) => row.date)
  const limitUpSeries = recent.map((row) => row.total_limit_up)
  const connectionSeries = recent.map((row) => row.connection_board_count)
  const maxBoardSeries = recent.map((row) => row.max_board)
  const brokenSeries = recent.map((row) => row.broken_count)
  return [
    {
      key: 'limit-up',
      label: '涨停家数',
      basis: '绝对家数',
      value: summary.total_limit_up,
      unit: '家',
      compare: comparison(summary.total_limit_up, previous?.total_limit_up, ' 家'),
      baseline: previous?.total_limit_up,
      note: '去重后的当日涨停证券',
      series: limitUpSeries,
      facts: seriesFacts(limitUpSeries, dates),
      tone: 'up',
      risk: false,
    },
    {
      key: 'connection',
      label: '连板家数',
      basis: '≥2板',
      value: summary.connection_board_count,
      unit: '家',
      compare: comparison(summary.connection_board_count, previous?.connection_board_count, ' 家'),
      baseline: previous?.connection_board_count,
      note: '2 板及以上',
      series: connectionSeries,
      facts: seriesFacts(connectionSeries, dates),
      tone: 'brand',
      risk: false,
    },
    {
      key: 'max-board',
      label: '最高板',
      basis: '当日高度',
      value: summary.max_board,
      unit: '板',
      compare: comparison(summary.max_board, previous?.max_board, ' 板'),
      baseline: previous?.max_board,
      note: '当日已确认高度',
      series: maxBoardSeries,
      facts: seriesFacts(maxBoardSeries, dates),
      tone: 'accent',
      risk: false,
    },
    {
      key: 'broken',
      label: '断板家数',
      basis: '风险指标',
      value: summary.broken_count,
      unit: '家',
      compare: comparison(summary.broken_count, previous?.broken_count, ' 家'),
      baseline: previous?.broken_count,
      note:
        summary.broken_connection_count === null
          ? '连板中断数未知'
          : `其中连板中断 ${summary.broken_connection_count} 家`,
      series: brokenSeries,
      facts: seriesFacts(brokenSeries, dates),
      tone: 'warn',
      risk: true,
    },
  ]
})

function comparisonClass(metric: (typeof metrics.value)[number]) {
  if (!metric.risk) {
    if (metric.compare.direction > 0) return 'up'
    if (metric.compare.direction < 0) return 'down'
    return 'flat'
  }
  if (metric.compare.direction > 0) return 'risk-up'
  if (metric.compare.direction < 0) return 'risk-down'
  return 'flat'
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>市场情绪</h2>
      <span class="sub">当日结构、连板高度与断板风险</span>
    </header>
    <div class="hero">
      <div class="summary-context">
        <div class="summary-context-main">
          <span class="context-key">观察日</span>
          <slot name="controls" />
          <span class="context-tag">{{ assessmentLabel }}</span>
          <span v-if="overview.window_actual < overview.window_requested" class="context-tag warn">
            仅 {{ overview.window_actual }} 个交易日
          </span>
          <span class="context-tag context-tag--quiet">完整度未验证</span>
        </div>
        <div class="context-note">
          前一交易日基准
          <b>{{ overview.previous_trading_day ?? '无可比日' }}</b>
        </div>
      </div>

      <div class="hero-top">
        <div class="emotion">
          <div
            class="gauge"
            role="img"
            :aria-label="`情绪评分 ${overview.summary.emotion_score ?? '不可评估'}`"
          >
            <svg viewBox="0 0 108 108" aria-hidden="true">
              <circle cx="54" cy="54" r="46" class="gauge-track" />
              <circle
                cx="54"
                cy="54"
                r="46"
                class="gauge-value"
                :style="{
                  stroke: gaugeColor,
                  strokeDasharray: circumference,
                  strokeDashoffset: gaugeOffset,
                }"
              />
            </svg>
            <div class="gauge-copy">
              <strong :style="{ color: gaugeColor }">
                {{ overview.summary.emotion_score ?? '—' }}
              </strong>
              <span>情绪评分</span>
            </div>
          </div>
          <div class="rating">
            <span class="rating-badge" :class="`rating-badge--${rating.tone}`">
              {{ rating.label }}
            </span>
            <span class="rating-note">{{ rating.note }}</span>
          </div>
        </div>

        <div class="stat-strip">
          <article
            v-for="metric in metrics"
            :key="metric.key"
            class="stat"
            :class="`stat--${metric.tone}`"
          >
            <span class="stat-top">
              <span class="stat-label">{{ metric.label }}</span>
              <span class="stat-basis">{{ metric.basis }}</span>
            </span>
            <span class="stat-value">
              {{ metric.value ?? '缺失'
              }}<small v-if="metric.value !== null">{{ metric.unit }}</small>
            </span>
            <span class="stat-delta" :class="comparisonClass(metric)">
              {{ metric.compare.main }}
            </span>
            <span class="stat-comparison">{{ metric.compare.detail }}</span>
            <div class="stat-facts">
              <span>
                <small>近10日中位</small>
                <b>{{ factValue(metric.facts.median, metric.unit) }}</b>
              </span>
              <span>
                <small>近10日区间</small>
                <b>
                  {{ factRange(metric.facts.minimum, metric.facts.maximum, metric.unit) }}
                </b>
              </span>
              <span>
                <small>区间高峰</small>
                <b>
                  {{ factValue(metric.facts.peak, metric.unit) }}
                  <em v-if="metric.facts.peakDate">· {{ metric.facts.peakDate.slice(5) }}</em>
                </b>
              </span>
              <span>
                <small>昨日基准</small>
                <b>{{ factValue(metric.baseline, metric.unit) }}</b>
              </span>
            </div>
            <div class="stat-spark-head">
              <span> 近10个交易日 · 已知 {{ metric.facts.samples }}/{{ metric.facts.total }} </span>
              <span>{{ metric.compare.main }}</span>
            </div>
            <MarketSparkline
              :values="metric.series"
              :label="`${metric.label}近十个交易日趋势`"
              :height="32"
              :color="`var(--${metric.tone})`"
            />
            <span class="stat-note"><em>口径</em>{{ metric.note }}</span>
          </article>
        </div>
      </div>

      <details v-if="overview.issues.length" class="issues">
        <summary>
          <AppIcon name="alert-triangle" :size="14" />
          {{ overview.issues.length }} 条数据口径与缺失提示
        </summary>
        <ul>
          <li v-for="issue in overview.issues" :key="`${issue.code}-${issue.scope}`">
            {{ issue.message }}
          </li>
        </ul>
      </details>
    </div>
  </section>
</template>

<style scoped>
.panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.hero {
  padding: var(--review-pad, 18px);
  display: grid;
  gap: 14px;
}

.summary-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px 18px;
  flex-wrap: wrap;
  padding: 0 0 12px;
  border-bottom: 1px solid var(--border);
}

.summary-context-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.context-key,
.context-note {
  color: var(--muted);
  font-size: 11px;
}

.context-note b {
  color: var(--fg);
  font-family: var(--mono);
  font-weight: 600;
}

.context-tag {
  padding: 1px 6px;
  border: 1px solid var(--border2);
  border-radius: 5px;
  color: var(--fg2);
  font-size: 10.5px;
}

.context-tag--quiet {
  color: var(--muted);
}

.context-tag.warn {
  color: var(--warn);
  border-color: color-mix(in oklab, var(--warn) 40%, var(--border));
}

.hero-top {
  display: grid;
  grid-template-columns: minmax(270px, 0.78fr) minmax(0, 3fr);
  align-items: stretch;
  gap: 14px;
}

.emotion {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  padding: 14px 16px;
  border-radius: 10px;
  background:
    radial-gradient(
      circle at 18% 24%,
      color-mix(in oklab, var(--brand) 10%, transparent),
      transparent 46%
    ),
    var(--surface2);
}

.gauge {
  position: relative;
  width: 116px;
  height: 116px;
  flex: none;
}

.gauge svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.gauge circle {
  fill: none;
  stroke-width: 8;
}

.gauge-track {
  stroke: var(--surface3);
}

.gauge-value {
  stroke-linecap: round;
  transition:
    stroke-dashoffset var(--duration) var(--ease),
    stroke var(--duration) var(--ease);
}

.gauge-copy {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  text-align: center;
}

.gauge-copy strong {
  font-family: var(--mono);
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
}

.gauge-copy span {
  color: var(--muted);
  font-size: 10.5px;
}

.rating {
  display: grid;
  gap: 7px;
  max-width: 260px;
}

.rating-badge {
  width: fit-content;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 700;
}

.rating-badge--up {
  color: var(--up);
  background: color-mix(in oklab, var(--up) 16%, transparent);
}

.rating-badge--flat {
  color: var(--accent);
  background: color-mix(in oklab, var(--accent) 14%, transparent);
}

.rating-badge--down {
  color: var(--down);
  background: color-mix(in oklab, var(--down) 16%, transparent);
}

.rating-note {
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.45;
}

.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  min-width: 0;
}

.stat {
  --stat-color: var(--fg2);
  min-width: 0;
  min-height: 196px;
  padding: 13px 14px 11px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in oklab, var(--surface2) 88%, var(--surface));
  display: grid;
  gap: 6px;
  align-content: start;
}

.stat--up {
  --stat-color: var(--up);
}

.stat--brand {
  --stat-color: var(--brand);
}

.stat--accent {
  --stat-color: var(--accent);
}

.stat--warn {
  --stat-color: var(--warn);
}

.stat-label,
.stat-comparison,
.stat-note {
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-label {
  font-size: 11.5px;
  font-weight: 620;
}

.stat-top {
  min-width: 0;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.stat-basis {
  flex: none;
  padding: 1px 6px;
  border-radius: 999px;
  background: color-mix(in oklab, var(--fg) 5%, transparent);
  color: var(--muted);
  font-size: 9.5px;
  white-space: nowrap;
}

.stat-value {
  font-family: var(--mono);
  font-size: 27px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.stat-value small {
  margin-left: 3px;
  color: var(--fg2);
  font-size: 12px;
  font-weight: 500;
}

.stat-delta {
  font-size: 11.3px;
  font-weight: 600;
}

.stat-delta.up {
  color: var(--up);
}

.stat-delta.down {
  color: var(--down);
}

.stat-delta.risk-up {
  color: var(--warn);
}

.stat-delta.risk-down {
  color: var(--accent);
}

.stat-delta.flat {
  color: var(--fg2);
}

.stat-comparison,
.stat-note {
  font-size: 10.7px;
  white-space: normal;
  line-height: 1.45;
}

.stat-comparison {
  min-height: 0;
}

.stat-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  padding: 7px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}

.stat-facts span {
  min-width: 0;
  display: grid;
  gap: 2px;
  padding: 6px 7px;
  border-radius: 7px;
  background: color-mix(in oklab, var(--surface) 66%, transparent);
}

.stat-facts small {
  color: var(--muted);
  font-size: 10px;
  white-space: nowrap;
}

.stat-facts b {
  min-width: 0;
  color: var(--fg2);
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
}

.stat-facts em {
  color: var(--muted);
  font-style: normal;
  font-weight: 400;
}

.stat-spark-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-size: 10px;
}

.stat-note em {
  margin-right: 4px;
  color: var(--stat-color);
  font-style: normal;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border);
}

.panel-head h2 {
  margin: 0;
}

.sub {
  color: var(--muted);
}

.issues {
  border-top: 1px solid var(--border);
  padding-top: 9px;
  color: var(--muted);
  font-size: 10.5px;
}

.issues summary {
  width: fit-content;
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}

.issues ul {
  margin: 7px 0 0;
  padding-left: 20px;
  color: var(--fg2);
  line-height: 1.55;
}

@media (max-width: 1220px) {
  .hero-top {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .stat-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-top {
    align-items: flex-start;
  }

  .summary-context {
    align-items: flex-start;
  }

  .context-note {
    flex-basis: 100%;
  }
}

@media (max-width: 540px) {
  .emotion {
    gap: 10px;
  }

  .gauge {
    width: 92px;
    height: 92px;
  }

  .gauge-copy strong {
    font-size: 22px;
  }

  .rating-badge {
    font-size: 12.5px;
  }
}
</style>
