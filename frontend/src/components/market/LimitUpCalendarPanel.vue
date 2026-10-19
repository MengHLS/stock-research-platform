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
const activityDays = computed(() => props.model.activityDays.slice(0, 6))
const maxActivityCount = computed(() =>
  Math.max(1, ...activityDays.value.map((item) => item.count)),
)
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
  return `${date} 不在源交易日历中`
}
</script>

<template>
  <section class="panel calendar-panel" :aria-busy="loading">
    <header class="panel-head">
      <div>
        <h2>涨停日历</h2>
        <p>每天涨停家数 · 色深表示数量 · 缺失显示斜纹</p>
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
            :aria-label="`${cell.date}，${cell.available ? `${cell.count} 家涨停` : '涨停记录缺失'}`"
            :aria-pressed="cell.date === selectedDate"
            @click="emit('select', cell.date)"
          >
            <span class="calendar-day">{{ cell.day }}</span>
            <b>{{ cell.available ? cell.count : '—' }}</b>
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
            <span>有记录日均值</span>
            <b> {{ model.average === null ? '—' : model.average.toFixed(1) }}<small>家</small> </b>
            <em>只按源中存在记录的日期计算</em>
          </article>
          <article>
            <span>{{ hasIncompleteDays ? '已知峰值日' : '峰值日' }}</span>
            <b>{{ model.peak ?? '—' }}<small>家</small></b>
            <em>{{ model.peakDate ? model.peakDate.slice(5) : '本月暂无可用记录' }}</em>
          </article>
          <div v-if="activityDays.length" class="activity-card">
            <div class="activity-head">
              <span>本月活跃日</span>
              <em>按涨停家数排序</em>
            </div>
            <div class="activity-list">
              <button
                v-for="item in activityDays"
                :key="item.date"
                type="button"
                :class="{ selected: item.date === selectedDate }"
                :aria-label="`${item.date}，${item.count} 家涨停`"
                @click="emit('select', item.date)"
              >
                <span class="mono">{{ item.date.slice(5) }}</span>
                <i>
                  <span :style="{ width: `${(item.count / maxActivityCount) * 100}%` }" />
                </i>
                <b>{{ item.count }}</b>
              </button>
            </div>
          </div>
          <div class="calendar-legend">
            <span>少</span>
            <i />
            <span>多</span>
            <span class="legend-missing">斜纹 = 记录缺失</span>
          </div>
          <p class="calendar-note">
            日历按旧库 <code>index_daily</code> 的交易日列出；没有涨停行的交易日不会显示成 0。
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
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in oklab, var(--surface) 96%, var(--fg) 4%);
}

.panel-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 680;
}

.panel-head p {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 12.5px;
}

.head-tools {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px 10px;
  flex-wrap: wrap;
}

.month-controls {
  flex: none;
  height: 34px;
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.month-controls button {
  width: 32px;
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
  min-width: 76px;
  padding: 0 8px;
  border-inline: 1px solid var(--border);
  color: var(--fg);
  font-family: var(--mono);
  font-size: 12px;
  text-align: center;
}

.calendar-layout {
  padding: 16px;
  display: grid;
  grid-template-columns: minmax(0, 980px) minmax(300px, 1fr);
  gap: 18px;
  align-items: start;
}

.calendar-wrap {
  width: 100%;
  max-width: 980px;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
}

.weekday {
  padding-bottom: 2px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 11.5px;
  text-align: center;
}

.calendar-cell {
  position: relative;
  aspect-ratio: 1.35;
  min-height: clamp(42px, 4vw, 78px);
  padding: 5px 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 1px;
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
  font-size: 10.5px;
  opacity: 0.68;
}

.calendar-cell b {
  font-family: var(--mono);
  font-size: clamp(13px, 1vw, 18px);
  line-height: 1;
}

.month-summary {
  min-width: 0;
  display: grid;
  gap: 8px;
}

.month-summary article {
  min-width: 0;
  padding: 11px 13px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
  display: grid;
  gap: 2px;
}

.month-summary article > span,
.month-summary article em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
}

.month-summary article b {
  color: var(--fg);
  font-family: var(--mono);
  font-size: 26px;
  line-height: 1.2;
}

.month-summary article small {
  margin-left: 3px;
  color: var(--fg2);
  font-size: 12px;
}

.activity-card {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface2);
}

.activity-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.activity-head span {
  color: var(--fg2);
  font-size: 12px;
  font-weight: 620;
}

.activity-head em {
  color: var(--muted);
  font-size: 11px;
  font-style: normal;
}

.activity-list {
  display: grid;
  gap: 4px;
}

.activity-list button {
  min-width: 0;
  min-height: 24px;
  padding: 2px 5px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--fg2);
  display: grid;
  grid-template-columns: 42px minmax(30px, 1fr) 24px;
  align-items: center;
  gap: 7px;
  font-size: 11.5px;
  text-align: left;
  cursor: pointer;
}

.activity-list button:hover {
  border-color: var(--border);
  background: var(--surface3);
}

.activity-list button.selected {
  border-color: color-mix(in oklab, var(--accent) 44%, var(--border));
  background: color-mix(in oklab, var(--accent) 8%, transparent);
}

.activity-list i {
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface3);
}

.activity-list i span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: color-mix(in oklab, var(--up) 80%, var(--brand));
}

.activity-list b {
  color: var(--fg);
  font-family: var(--mono);
  font-size: 11.5px;
  text-align: right;
}

.mono {
  font-family: var(--mono);
}

.calendar-legend {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 1px;
  color: var(--muted);
  font-size: 11.5px;
}

.calendar-legend i {
  width: min(130px, 42%);
  height: 9px;
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
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}

.calendar-note code {
  color: var(--fg2);
  font-family: var(--mono);
}

.calendar-state {
  min-height: 150px;
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
    grid-template-columns: repeat(3, minmax(0, 1fr));
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
  }

  .calendar-layout {
    padding: 12px;
  }

  .head-tools {
    width: 100%;
    justify-content: flex-start;
  }

  .calendar-cell {
    aspect-ratio: auto;
    min-height: 40px;
    padding: 3px;
  }

  .month-summary {
    grid-template-columns: 1fr;
  }

  .activity-list button {
    min-height: 40px;
  }

  .month-controls {
    height: 44px;
  }

  .month-controls button {
    width: 44px;
  }
}

@media (min-width: 2200px) {
  .calendar-layout {
    grid-template-columns: minmax(760px, 1.15fr) minmax(520px, 0.85fr);
    gap: 24px;
  }

  .calendar-wrap {
    max-width: none;
  }

  .calendar-cell {
    aspect-ratio: auto;
    min-height: 82px;
  }

  .month-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .activity-card,
  .calendar-legend,
  .calendar-note {
    grid-column: 1 / -1;
  }

  .activity-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
