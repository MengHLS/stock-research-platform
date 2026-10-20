<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import MarketTrendChart from './MarketTrendChart.vue'
import type { ReviewHistoryRow, ReviewWindow } from '../../market/review'
import { REVIEW_WINDOWS } from '../../market/review'

const props = defineProps<{
  history: ReviewHistoryRow[]
  selectedDate: string
}>()
const emit = defineEmits<{
  openDay: [date: string]
}>()

const focusDate = ref(props.selectedDate)
const localWindow = ref<ReviewWindow>(120)

watch(
  () => props.selectedDate,
  (date) => {
    focusDate.value = date
  },
  { immediate: true },
)

const rows = computed(() =>
  [...props.history].sort((left, right) => left.date.localeCompare(right.date)),
)
const windows = computed(() => {
  const values: number[] = REVIEW_WINDOWS.filter((item) => item <= rows.value.length)
  if (rows.value.length && !values.includes(rows.value.length)) values.push(rows.value.length)
  return Array.from(new Set(values)).sort((left, right) => left - right)
})
const visibleRows = computed(() => rows.value.slice(-localWindow.value))
const focus = computed(
  () =>
    visibleRows.value.find((row) => row.date === focusDate.value) ??
    visibleRows.value.at(-1) ??
    null,
)
const knownMaximum = computed(() => {
  const values = visibleRows.value
    .map((row) => row.max_board)
    .filter((value): value is number => value !== null && value !== undefined)
  return values.length ? Math.max(...values) : null
})

watch(
  () => props.history,
  () => {
    if (!rows.value.length) return
    if (!rows.value.some((row) => row.date === focusDate.value)) {
      focusDate.value = rows.value.at(-1)?.date ?? props.selectedDate
    }
  },
  { immediate: true },
)

function selectDate(date: string) {
  focusDate.value = date
}

function selectWindow(window: ReviewWindow) {
  localWindow.value = window
  if (!visibleRows.value.some((row) => row.date === focusDate.value)) {
    focusDate.value = visibleRows.value.at(-1)?.date ?? focusDate.value
  }
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>每日最高连板</h2>
      <span class="sub">
        {{ `近 ${visibleRows.length} 个交易日` }}
        <template v-if="rows.length > 0 && rows.length < 120"> · 历史不足120日</template>
      </span>
      <span class="grow" />
      <div class="windows" role="group" aria-label="图表区间">
        <button
          v-for="item in windows"
          :key="item"
          type="button"
          :class="{ active: item === Math.min(localWindow, rows.length) }"
          :aria-pressed="item === Math.min(localWindow, rows.length)"
          @click="selectWindow(item)"
        >
          {{ item }}日
        </button>
      </div>
    </header>
    <div class="panel-body">
      <div v-if="visibleRows.length" class="chart-summary">
        <span>
          <b>{{ focus?.max_board ?? '—' }}<small> 板</small></b>
          当前高度
        </span>
        <span>
          <b>{{ knownMaximum ?? '—' }}<small> 板</small></b>
          区间已知最高
        </span>
      </div>
      <div v-if="visibleRows.length" class="chart-scroll">
        <MarketTrendChart :history="visibleRows" :selected-date="focusDate" @select="selectDate" />
      </div>
      <div v-else class="empty">该窗口没有可绘制的最高板数据。</div>

      <div v-if="focus" class="focus">
        <span>
          <b>{{ focus.date }}</b>
          · 最高 {{ focus.max_board ?? '—' }} 板
        </span>
        <span class="names">
          <template v-if="focus.high_board_stocks?.length">
            六板及以上：{{
              focus.high_board_stocks
                .map((stock) => `${stock.name}（${stock.boards}板）`)
                .join('、')
            }}
          </template>
          <template v-else>
            {{ focus.max_board_stocks?.map((stock) => stock.name).join('、') || '最高板股票未知' }}
            <template
              v-if="(focus.max_board_stock_total ?? 0) > (focus.max_board_stocks?.length ?? 0)"
            >
              等 {{ focus.max_board_stock_total }} 只
            </template>
          </template>
        </span>
        <button type="button" class="open" @click="emit('openDay', focus.date)">
          查看当日涨停列表 ›
        </button>
      </div>
      <details v-if="visibleRows.length" class="daily-names">
        <summary>逐日六板及以上股票 · 完整名单</summary>
        <div v-for="row in visibleRows" :key="row.date" class="daily-row">
          <button type="button" @click="selectDate(row.date)">{{ row.date }}</button>
          <span v-if="row.high_board_stocks?.length" class="names">
            {{
              row.high_board_stocks.map((stock) => `${stock.name}（${stock.boards}板）`).join('、')
            }}
          </span>
          <span v-else>{{
            row.assessment === 'available' ? '无六板及以上股票' : '暂无已知六板及以上股票'
          }}</span>
          <button type="button" class="open" @click="emit('openDay', row.date)">查看当日 ›</button>
        </div>
      </details>
      <p class="note">
        <span class="peak-dot" />
        圆点标注为区间内局部高峰；缺失日期保持断点，不补值。
      </p>
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
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.panel-head h2 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 650;
}

.sub {
  color: var(--muted);
  font-size: 11.5px;
}

.grow {
  flex: 1 1 auto;
}

.panel-body {
  padding: 12px 16px 16px;
}

.chart-scroll {
  overflow-x: auto;
}

.chart-summary {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 22px;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 11px;
}

.chart-summary b {
  margin-right: 5px;
  font-family: var(--mono);
  font-size: 18px;
  color: var(--fg);
}

.chart-summary small {
  font-size: 11px;
  font-weight: 500;
}

.windows {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
}

.windows button {
  border: 0;
  border-radius: 999px;
  padding: 4px 11px;
  background: transparent;
  color: var(--muted);
  font-size: 10.5px;
  cursor: pointer;
  transition:
    background var(--duration) var(--ease),
    color var(--duration) var(--ease);
}

.windows button:hover {
  color: var(--fg);
}

.windows button.active {
  background: var(--surface);
  color: var(--fg);
  box-shadow: var(--shadow);
}

.focus {
  display: flex;
  align-items: center;
  gap: 8px 14px;
  flex-wrap: wrap;
  margin-top: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  font-size: 11px;
}

.names {
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: normal;
}

.daily-names {
  margin-top: 12px;
  color: var(--fg2);
  font-size: 11px;
}

.daily-names summary {
  padding: 8px 0;
  cursor: pointer;
}

.daily-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 8px 0;
  border-top: 1px solid var(--border);
}

.daily-row > button:first-child {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--accent);
  font: inherit;
  cursor: pointer;
}

.daily-row .names {
  flex: 1 1 240px;
  line-height: 1.7;
}

.open {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
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

.note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 10.5px;
}

.peak-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
  flex: none;
}

@media (max-width: 540px) {
  .open {
    margin-left: 0;
  }
}
</style>
