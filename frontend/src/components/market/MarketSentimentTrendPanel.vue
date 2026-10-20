<script setup lang="ts">
import { computed } from 'vue'

import MarketSparkline from './MarketSparkline.vue'
import MarketTrendChart from './MarketTrendChart.vue'
import type { ReviewHistoryRow } from '../../market/review'
import { emotionRating, formatMetric } from '../../market/review'
import { orderedHistory, sentimentSnapshot } from '../../market/sentiment'

const props = defineProps<{
  history: ReviewHistoryRow[]
  selectedDate: string
  windowValue: number
  windowOptions: number[]
  windowRequested: number
  windowActual: number
}>()
const emit = defineEmits<{
  window: [window: number]
  select: [date: string]
}>()

const rows = computed(() => orderedHistory(props.history))
const snapshot = computed(() => sentimentSnapshot(rows.value, props.selectedDate))
const rating = computed(() => emotionRating(snapshot.value.current?.emotion_score))
const peakRating = computed(() => emotionRating(snapshot.value.peak?.emotion_score))
const recentRows = computed(() => rows.value.slice(-10))
const recentScores = computed(() => recentRows.value.map((row) => row.emotion_score))
const recentMaxBoards = computed(() => recentRows.value.map((row) => row.max_board))
const shortestWindow = computed(() => props.windowActual < props.windowRequested)

function comparison(
  current: number | null | undefined,
  previous: number | null | undefined,
  unit = '',
) {
  if (current === null || current === undefined) {
    return { main: '当前值缺失', detail: '缺失不按零值处理', direction: 0 }
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
    main: delta === 0 ? '较前日持平' : `较前日 ${delta > 0 ? '+' : ''}${delta}${unit}`,
    detail: `前日 ${previous}${unit} · ${percentage}`,
    direction,
  }
}

const emotionComparison = computed(() =>
  comparison(snapshot.value.current?.emotion_score, snapshot.value.previous?.emotion_score, ' 分'),
)
const boardComparison = computed(() =>
  comparison(snapshot.value.current?.max_board, snapshot.value.previous?.max_board, ' 板'),
)
const averageText = computed(() =>
  snapshot.value.average === null ? '—' : snapshot.value.average.toFixed(1),
)
const peakDate = computed(() => snapshot.value.peak?.date.slice(5) ?? '没有有效评分')
const focusNames = computed(
  () =>
    snapshot.value.current?.max_board_stocks?.map((stock) => stock.name).join('、') ||
    '最高板股票未知',
)

function comparisonClass(direction: number): string {
  if (direction > 0) return 'up'
  if (direction < 0) return 'down'
  return 'flat'
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <div class="title">
        <h2>情绪周期</h2>
        <span class="sub">
          最近 {{ history.length }} 个交易日 · 截至 {{ selectedDate }}
          <template v-if="shortestWindow"> · 源内仅 {{ windowActual }} 日</template>
        </span>
      </div>
      <span class="grow" />
      <slot name="controls" />
      <div class="window-tabs" role="group" aria-label="情绪周期区间长度">
        <button
          v-for="item in windowOptions"
          :key="item"
          type="button"
          :class="{ active: item === windowValue }"
          :aria-pressed="item === windowValue"
          @click="emit('window', item)"
        >
          {{ item }}日
        </button>
      </div>
    </header>

    <div class="panel-body">
      <div class="stat-strip">
        <article class="stat stat--brand">
          <span class="stat-top">
            <span>当前情绪</span>
            <b class="rating" :class="`rating--${rating.tone}`">{{ rating.label }}</b>
          </span>
          <span class="stat-value">
            {{ formatMetric(snapshot.current?.emotion_score) }}
            <small v-if="snapshot.current?.emotion_score !== null">分</small>
          </span>
          <span class="stat-delta" :class="comparisonClass(emotionComparison.direction)">
            {{ emotionComparison.main }}
          </span>
          <span class="stat-detail">{{ emotionComparison.detail }}</span>
          <div class="spark">
            <MarketSparkline
              :values="recentScores"
              :label="`最近 ${recentScores.length} 个交易日情绪评分`"
              :height="32"
              color="var(--brand)"
            />
          </div>
          <span class="stat-foot">{{ rating.note }}</span>
        </article>

        <article class="stat">
          <span class="stat-top"><span>区间均值</span><b>区间统计</b></span>
          <span class="stat-value">{{ averageText }}</span>
          <span class="stat-delta flat">
            {{ snapshot.knownScores }}/{{ snapshot.totalRows }} 个有效评分
          </span>
          <span class="stat-detail">仅使用非缺失评分计算，不补零</span>
          <div class="spark spark--placeholder" />
          <span class="stat-foot">{{ history.length }} 日均值</span>
        </article>

        <article class="stat">
          <span class="stat-top"><span>区间峰值</span><b>区间统计</b></span>
          <span class="stat-value">{{ formatMetric(snapshot.peak?.emotion_score) }}</span>
          <span class="stat-delta flat">{{ peakRating.label }}</span>
          <span class="stat-detail">{{ peakDate }}</span>
          <div class="spark spark--placeholder" />
          <span class="stat-foot">区间最高情绪评分</span>
        </article>

        <article class="stat stat--accent">
          <span class="stat-top"><span>最高板</span><b>当日高度</b></span>
          <span class="stat-value">
            {{ formatMetric(snapshot.current?.max_board) }}
            <small v-if="snapshot.current?.max_board !== null">板</small>
          </span>
          <span class="stat-delta" :class="comparisonClass(boardComparison.direction)">
            {{ boardComparison.main }}
          </span>
          <span class="stat-detail">{{ focusNames }}</span>
          <div class="spark">
            <MarketSparkline
              :values="recentMaxBoards"
              :label="`最近 ${recentMaxBoards.length} 个交易日最高连板`"
              :height="32"
              color="var(--accent)"
            />
          </div>
          <span class="stat-foot">缺失日期保持断点</span>
        </article>
      </div>

      <div class="chart-heading">
        <div>
          <strong>每日最高连板</strong>
          <span>点表示有涨停记录 · 悬停查看当日最高板个股 · 点击切换观察日</span>
        </div>
        <span class="chart-current">
          当前 {{ snapshot.current?.max_board ?? '—' }} 板 · 区间已知最高
          {{ snapshot.maxBoard ?? '—' }} 板
        </span>
      </div>
      <div v-if="rows.length" class="chart-scroll">
        <MarketTrendChart
          :history="rows"
          :selected-date="selectedDate"
          :chart-height="260"
          @select="emit('select', $event)"
        />
      </div>
      <div v-else class="empty">当前窗口没有可绘制的连板数据。</div>

      <div v-if="snapshot.current" class="focus">
        <span>
          <b>{{ snapshot.current.date }}</b>
          · 最高 {{ snapshot.current.max_board ?? '—' }} 板
        </span>
        <span class="focus-names">{{ focusNames }}</span>
        <RouterLink
          class="detail-link"
          :to="{ path: '/market/limit-up', query: { date: snapshot.current.date } }"
        >
          查看当日涨停列表
        </RouterLink>
      </div>
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

.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.title {
  display: flex;
  align-items: baseline;
  gap: 9px;
  flex-wrap: wrap;
}

.panel-head h2 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 680;
}

.sub,
.stat-detail,
.stat-foot,
.chart-heading span {
  color: var(--muted);
  font-size: 11px;
}

.grow {
  flex: 1 1 auto;
}

.window-tabs {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
}

.window-tabs button {
  min-height: 26px;
  padding: 2px 10px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 10.5px;
  cursor: pointer;
  transition:
    background var(--duration) var(--ease),
    color var(--duration) var(--ease);
}

.window-tabs button:hover {
  color: var(--fg);
}

.window-tabs button.active {
  background: var(--surface);
  color: var(--fg);
  box-shadow: var(--shadow);
}

.panel-body {
  padding: 14px 16px 16px;
}

.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
}

.stat {
  min-width: 0;
  min-height: 124px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
  display: grid;
  align-content: start;
  gap: 2px;
}

.stat--brand {
  border-color: color-mix(in oklab, var(--brand) 20%, var(--border));
}

.stat--accent {
  border-color: color-mix(in oklab, var(--accent) 18%, var(--border));
}

.stat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-size: 10.5px;
}

.stat-top b {
  font-size: 10px;
  font-weight: 500;
}

.rating {
  padding: 0 5px;
  border-radius: 999px;
  border: 1px solid currentColor;
}

.rating--up {
  color: var(--up);
}

.rating--flat {
  color: var(--accent);
}

.rating--down {
  color: var(--down);
}

.stat-value {
  color: var(--fg);
  font-family: var(--mono);
  font-size: 21px;
  font-weight: 700;
  line-height: 1.25;
}

.stat-value small {
  margin-left: 2px;
  color: var(--fg2);
  font-family: var(--font);
  font-size: 10px;
  font-weight: 500;
}

.stat-delta {
  min-height: 17px;
  font-size: 10.5px;
  font-weight: 600;
}

.stat-delta.up {
  color: var(--up);
}

.stat-delta.down {
  color: var(--down);
}

.stat-delta.flat {
  color: var(--accent);
}

.stat-detail,
.stat-foot {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
}

.spark {
  height: 32px;
  margin-top: 2px;
}

.spark--placeholder {
  min-height: 32px;
}

.chart-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px 20px;
  flex-wrap: wrap;
  margin-top: 13px;
}

.chart-heading div {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.chart-heading strong {
  color: var(--fg2);
  font-size: 11px;
  font-weight: 600;
}

.chart-current {
  color: var(--fg2) !important;
  font-family: var(--mono);
  white-space: nowrap;
}

.chart-scroll {
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

.focus {
  display: flex;
  align-items: center;
  gap: 8px 14px;
  flex-wrap: wrap;
  margin-top: 2px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  font-size: 10.5px;
}

.focus b {
  font-family: var(--mono);
  color: var(--fg);
}

.focus-names {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}

.detail-link {
  margin-left: auto;
  color: var(--accent);
  font-size: 10.5px;
}

.empty {
  min-height: 180px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 920px) {
  .stat-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .panel-head,
  .panel-body {
    padding-inline: 14px;
  }

  .title,
  .stat-strip {
    width: 100%;
  }

  .stat-strip {
    grid-template-columns: 1fr;
  }
}
</style>
