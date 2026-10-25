<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../AppIcon'
import type { MonthCalendarModel } from '../../market/limit-up'

const props = defineProps<{
  model: MonthCalendarModel
  selectedDate: string
  loading: boolean
  failure: string | null
  previousMonth: string | null
  nextMonth: string | null
}>()
const emit = defineEmits<{
  month: [month: string]
  select: [date: string]
}>()

const maxCount = computed(() => Math.max(1, ...props.model.cells.map((cell) => cell?.count ?? 0)))
const hasIncompleteDays = computed(() => props.model.knownDays < props.model.tradingDays)
const hasIncompleteDownDays = computed(() => props.model.downKnownDays < props.model.tradingDays)
const weekdays = ['一', '二', '三', '四', '五', '六', '日']

function heat(cell: NonNullable<MonthCalendarModel['cells'][number]>) {
  if (!cell.available || cell.count === null) return undefined
  const opacity = 0.12 + (cell.count / maxCount.value) * 0.72
  return {
    background: `color-mix(in oklab, var(--up) ${(opacity * 100).toFixed(0)}%, var(--surface2))`,
    color: opacity > 0.58 ? '#fff' : 'var(--fg)',
  }
}

function missingCellTitle(day: number) {
  const date = `${props.model.month}-${String(day).padStart(2, '0')}`
  if (props.loading) return `${date} 的交易日历正在读取`
  if (props.failure) return `${date} 的交易日历读取失败`
  return `${date} 不在交易日历中`
}

function countLabel(cell: NonNullable<MonthCalendarModel['cells'][number]>) {
  const up = cell.count === null ? '涨停计数缺失' : `${cell.count} 家涨停`
  const down = cell.downCount === null ? '跌停计数缺失' : `${cell.downCount} 家跌停`
  return `${cell.date}，${up}，${down}`
}
</script>

<template>
  <section class="panel calendar-panel" :aria-busy="loading">
    <header class="panel-head">
      <div>
        <h2>涨跌停日历</h2>
        <p>每天涨停 / 跌停家数 · 色深表示涨停数量 · 缺失显示斜纹</p>
      </div>
      <div class="head-tools">
        <slot name="date-controls" />
        <div class="month-controls" role="group" aria-label="日历月份">
          <button
            type="button"
            :disabled="loading || !previousMonth"
            aria-label="上一个月"
            @click="previousMonth && emit('month', previousMonth)"
          >
            <AppIcon name="chevron-left" :size="15" />
          </button>
          <b>{{ model.month }}</b>
          <button
            type="button"
            :disabled="loading || !nextMonth"
            aria-label="下一个月"
            @click="nextMonth && emit('month', nextMonth)"
          >
            <AppIcon name="chevron-right" :size="15" />
          </button>
        </div>
      </div>
    </header>

    <div class="panel-body calendar-layout">
      <div class="calendar-wrap">
        <div v-for="weekday in weekdays" :key="weekday" class="weekday">{{ weekday }}</div>
        <template v-for="(cell, index) in model.cells" :key="cell?.date ?? `blank-${index}`">
          <div v-if="!cell" class="calendar-cell calendar-cell--blank" aria-hidden="true" />
          <button
            v-else-if="cell.date"
            type="button"
            class="calendar-cell calendar-cell--trade"
            :class="{
              'calendar-cell--selected': cell.date === selectedDate,
              'calendar-cell--missing': !cell.available,
              'calendar-cell--weekend': cell.weekend,
            }"
            :style="heat(cell)"
            :aria-label="countLabel(cell)"
            :aria-pressed="cell.date === selectedDate"
            @click="emit('select', cell.date)"
          >
            <span class="calendar-day">{{ cell.day }}</span>
            <span class="calendar-counts">
              <span class="count-up">
                <em>涨</em>
                <b>{{ cell.count ?? '—' }}</b>
              </span>
              <span class="count-down">
                <em>跌</em>
                <b>{{ cell.downCount ?? '—' }}</b>
              </span>
            </span>
          </button>
          <div
            v-else
            class="calendar-cell"
            :class="{
              'calendar-cell--weekend': cell.weekend,
              'calendar-cell--pending': loading || failure,
            }"
            :title="missingCellTitle(cell.day)"
          >
            <span class="calendar-day">{{ cell.day }}</span>
          </div>
        </template>
      </div>

      <div class="month-summary">
        <div v-if="failure" class="calendar-state calendar-state--error" role="alert">
          <AppIcon name="alert-triangle" :size="16" />
          <span>{{ failure }}</span>
        </div>
        <div v-else-if="loading && !model.tradingDays" class="calendar-state">
          正在读取 {{ model.month }} 的交易日历…
        </div>
        <template v-else>
          <article>
            <span>{{ hasIncompleteDays ? '本月已知涨停合计' : '本月涨停合计' }}</span>
            <b>{{ hasIncompleteDays ? '≥' : '' }}{{ model.total }}<small>家</small></b>
            <em>{{ model.knownDays }}/{{ model.tradingDays }} 个交易日有记录</em>
          </article>
          <article>
            <span>{{ hasIncompleteDownDays ? '本月已知跌停合计' : '本月跌停合计' }}</span>
            <b v-if="model.downKnownDays">
              {{ hasIncompleteDownDays ? '≥' : '' }}{{ model.downTotal }}<small>家</small>
            </b>
            <b v-else>—</b>
            <em> {{ model.downKnownDays }}/{{ model.tradingDays }} 个交易日有涨跌停计数 </em>
          </article>
          <article>
            <span>有记录日均值</span>
            <b> {{ model.average === null ? '—' : model.average.toFixed(1) }}<small>家</small> </b>
            <em>只按有记录的日期计算</em>
          </article>
          <article>
            <span>{{ hasIncompleteDays ? '已知峰值日' : '峰值日' }}</span>
            <b>{{ model.peak ?? '—' }}<small>家</small></b>
            <em>{{ model.peakDate ? model.peakDate.slice(5) : '本月暂无可用记录' }}</em>
          </article>
          <div class="calendar-legend">
            <span>少</span>
            <i />
            <span>多</span>
            <span class="legend-missing">斜纹 = 记录缺失</span>
          </div>
          <p class="calendar-note">
            涨停、跌停取同一冻结市场状态交易日；0 家是有效计数，缺少对应计数才显示“—”。
          </p>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.panel-head {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 4px 10px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in oklab, var(--surface) 96%, var(--fg) 4%);
}

.panel-head h2 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 680;
  line-height: 1.2;
}

.panel-head p {
  margin: 1px 0 0;
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.2;
}

.head-tools {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px 8px;
  flex-wrap: wrap;
}

.month-controls {
  flex: none;
  height: 30px;
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.month-controls button {
  width: 28px;
  height: 100%;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--fg2);
  cursor: pointer;
}

.month-controls button:hover:not(:disabled) {
  background: var(--surface3);
}

.month-controls button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.month-controls b {
  min-width: 68px;
  padding: 0 6px;
  border-inline: 1px solid var(--border);
  color: var(--fg);
  font-family: var(--mono);
  font-size: 11.5px;
  text-align: center;
}

.calendar-layout {
  padding: 6px 8px;
  display: grid;
  grid-template-columns: minmax(0, 620px) minmax(300px, 1fr);
  gap: 12px;
  align-items: start;
}

.calendar-wrap {
  width: 100%;
  max-width: 760px;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 3px;
}

.weekday {
  padding-bottom: 0;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10.5px;
  text-align: center;
}

.calendar-cell {
  position: relative;
  height: clamp(28px, 2.35vw, 42px);
  padding: 3px 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0;
}

.calendar-cell--blank {
  visibility: hidden;
}

.calendar-cell--trade {
  cursor: pointer;
  transition:
    transform var(--duration) var(--ease),
    border-color var(--duration) var(--ease),
    box-shadow var(--duration) var(--ease);
}

.calendar-cell--trade:hover {
  transform: translateY(-1px);
  border-color: var(--border2);
  box-shadow: var(--shadow);
}

.calendar-cell--selected {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.calendar-cell--missing {
  background:
    repeating-linear-gradient(
      135deg,
      transparent 0 4px,
      color-mix(in oklab, var(--muted) 14%, transparent) 4px 5px
    ),
    var(--surface2);
}

.calendar-cell--weekend {
  opacity: 0.58;
}

.calendar-cell--pending {
  border-style: dashed;
  opacity: 0.72;
}

.calendar-day {
  color: currentColor;
  font-family: var(--mono);
  font-size: 9.5px;
  opacity: 0.68;
}

.calendar-counts {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.calendar-counts > span {
  display: inline-flex;
  align-items: baseline;
  gap: 1px;
}

.calendar-counts em {
  color: currentColor;
  font-size: 8px;
  font-style: normal;
  opacity: 0.7;
}

.calendar-counts b {
  color: inherit;
  font-family: var(--mono);
  font-size: clamp(10px, 0.75vw, 13px);
  line-height: 1;
}

.count-up b {
  color: inherit;
}

.count-down b {
  color: inherit;
}

.month-summary {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.month-summary article {
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
  display: grid;
  gap: 1px;
}

.month-summary article > span,
.month-summary article em {
  color: var(--muted);
  font-size: 10.5px;
  font-style: normal;
  line-height: 1.35;
}

.month-summary article b {
  color: var(--fg);
  font-family: var(--mono);
  font-size: 18px;
  line-height: 1.05;
}

.month-summary article small {
  margin-left: 3px;
  color: var(--fg2);
  font-size: 10.5px;
}

.calendar-legend {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px;
  color: var(--muted);
  font-size: 10.5px;
}

.calendar-legend i {
  width: min(110px, 38%);
  height: 7px;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    color-mix(in oklab, var(--up) 12%, var(--surface2)),
    var(--up)
  );
}

.calendar-legend .legend-missing {
  margin-left: auto;
}

.calendar-note {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
}

.calendar-note code {
  color: var(--fg2);
  font-family: var(--mono);
}

.calendar-state {
  min-height: 110px;
  padding: 16px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 7px;
  font-size: 12.5px;
  text-align: center;
}

.calendar-state--error {
  color: var(--up);
}

@media (max-width: 1080px) {
  .calendar-layout {
    grid-template-columns: 1fr;
  }

  .month-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .calendar-legend,
  .calendar-note {
    grid-column: 1 / -1;
  }
}

@media (max-width: 680px) {
  .panel-head {
    align-items: flex-start;
    flex-direction: column;
    padding: 9px 10px;
  }

  .calendar-layout {
    padding: 9px;
  }

  .head-tools {
    width: 100%;
    justify-content: flex-start;
  }

  .calendar-cell {
    height: 34px;
    padding: 3px;
  }

  .month-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .month-controls {
    height: 40px;
  }

  .month-controls button {
    width: 40px;
  }
}

@media (min-width: 2200px) {
  .calendar-layout {
    grid-template-columns: minmax(620px, 720px) minmax(360px, 1fr);
    gap: 16px;
  }

  .calendar-wrap {
    max-width: none;
  }

  .calendar-cell {
    height: 46px;
  }

  .month-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .calendar-legend,
  .calendar-note {
    grid-column: 1 / -1;
  }
}
</style>
