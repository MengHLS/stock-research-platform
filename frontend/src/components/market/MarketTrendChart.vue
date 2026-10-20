<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'

import type { ReviewHistoryRow } from '../../market/review'
import { trendPeakIndexes } from '../../market/review'
import { useChartViewport } from '../../market/useChartViewport'
import {
  areaPath,
  linePath,
  sparseAxisIndexes,
  splitLineSegments,
  type ChartPoint,
} from '../../market/chart'

const props = defineProps<{
  history: ReviewHistoryRow[]
  selectedDate: string
  chartHeight?: number
}>()
const emit = defineEmits<{ select: [date: string] }>()

const { chartHost, width, revealX, tooltipPosition } = useChartViewport(480, 760)
const height = props.chartHeight ?? 360
const plotLeft = 46
const plotRight = 20
const plotTop = 38
const plotBottom = 38
const plotWidth = computed(() => width.value - plotLeft - plotRight)
const plotHeight = height - plotTop - plotBottom
const gradientId = `trend-fill-${useId().replaceAll(':', '')}`
const hoverIndex = ref<number | null>(null)
watch(
  () => props.history,
  () => {
    hoverIndex.value = null
  },
)

const values = computed(() => props.history.map((row) => row.max_board ?? null))
const knownValues = computed(() => values.value.filter((value): value is number => value !== null))
const hasValues = computed(() => knownValues.value.length > 0)
const maximum = computed(() => {
  const highest = knownValues.value.length ? Math.max(...knownValues.value) : 1
  return Math.max(1, Math.ceil(highest * 1.18))
})
const tickValues = computed(() => {
  const top = maximum.value
  const step = Math.max(1, Math.ceil(top / 4))
  return Array.from({ length: Math.floor(top / step) + 1 }, (_, index) => index * step)
})
const selectedIndex = computed(() =>
  props.history.findIndex((row) => row.date === props.selectedDate),
)
const axisIndexes = computed(() =>
  sparseAxisIndexes(props.history.length, Math.max(6, Math.min(12, Math.floor(width.value / 180)))),
)

function xFor(index: number) {
  return plotLeft + ((index + 0.5) / Math.max(1, props.history.length)) * plotWidth.value
}

function yFor(value: number) {
  return plotTop + plotHeight - (value / maximum.value) * plotHeight
}

const segments = computed(() => splitLineSegments(values.value, xFor, yFor))
const points = computed<ChartPoint[]>(() =>
  segments.value.flatMap((segment) =>
    props.history.length <= 40 || segment.length === 1 ? segment : [],
  ),
)
const peaks = computed(() => {
  const candidates = trendPeakIndexes(props.history).sort(
    (left, right) => (values.value[right] ?? 0) - (values.value[left] ?? 0),
  )
  const chosen: number[] = []
  for (const index of candidates) {
    if (chosen.length === 4) break
    if (
      chosen.every(
        (other) => Math.abs(xFor(other) - xFor(index)) >= Math.min(168, plotWidth.value * 0.2),
      )
    )
      chosen.push(index)
  }
  return chosen.map((index) => {
    const row = props.history[index]
    return {
      index,
      x: xFor(index),
      y: yFor(row.max_board ?? 0),
      label:
        row.max_board_stocks
          ?.slice(0, 1)
          .map((stock) => stock.name)
          .join('、') || `${row.max_board ?? '—'} 板`,
      anchor: xFor(index) > width.value - 100 ? 'end' : xFor(index) < 100 ? 'start' : 'middle',
    }
  })
})

const activeIndex = computed(() => hoverIndex.value ?? selectedIndex.value)
const activeValue = computed(() =>
  activeIndex.value >= 0 ? (values.value[activeIndex.value] ?? null) : null,
)
const tooltipRow = computed(() =>
  hoverIndex.value !== null ? (props.history[hoverIndex.value] ?? null) : null,
)
const tooltipStyle = computed(() => {
  if (hoverIndex.value === null || !props.history.length) return { display: 'none' }
  return tooltipPosition(xFor(hoverIndex.value), 200)
})

function setHoverFromPointer(event: PointerEvent) {
  if (!props.history.length) return
  const bounds = (event.currentTarget as SVGElement).getBoundingClientRect()
  const chartX = ((event.clientX - bounds.left) / bounds.width) * width.value
  const index = Math.floor(((chartX - plotLeft) / plotWidth.value) * props.history.length)
  hoverIndex.value = Math.max(0, Math.min(props.history.length - 1, index))
}

function moveCursor(step: number) {
  if (!props.history.length) return
  const current = hoverIndex.value ?? selectedIndex.value
  hoverIndex.value = Math.max(0, Math.min(props.history.length - 1, current + step))
  revealX(xFor(hoverIndex.value))
}

function selectActive(index = activeIndex.value) {
  const row = props.history[index]
  if (row) emit('select', row.date)
}
</script>

<template>
  <div ref="chartHost" class="chart-wrap">
    <svg
      class="trend-chart"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      aria-label="每日最高连板趋势；方向键可逐日查看，回车在图表内查看当天"
      tabindex="0"
      @pointermove="setHoverFromPointer"
      @pointerleave="hoverIndex = null"
      @keydown.left.prevent="moveCursor(-1)"
      @keydown.right.prevent="moveCursor(1)"
      @keydown.enter.prevent="selectActive()"
      @keydown.esc="hoverIndex = null"
      @blur="hoverIndex = null"
    >
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--brand)" stop-opacity="0.15" />
          <stop offset="1" stop-color="var(--brand)" stop-opacity="0" />
        </linearGradient>
      </defs>

      <rect
        v-if="selectedIndex >= 0"
        class="selected-band"
        :x="xFor(selectedIndex) - plotWidth / Math.max(1, history.length) / 2"
        :y="plotTop"
        :width="plotWidth / Math.max(1, history.length)"
        :height="plotHeight"
      />

      <template v-if="hasValues">
        <g v-for="tick in tickValues" :key="tick">
          <line
            class="grid-line"
            :x1="plotLeft"
            :x2="width - plotRight"
            :y1="yFor(tick)"
            :y2="yFor(tick)"
          />
          <text class="axis-value" :x="plotLeft - 8" :y="yFor(tick) + 3" text-anchor="end">
            {{ tick }}
          </text>
        </g>
      </template>

      <path
        v-for="(segment, index) in segments"
        :key="`area-${index}`"
        :d="areaPath(segment, plotTop + plotHeight)"
        class="trend-area"
        :fill="`url(#${gradientId})`"
      />
      <path
        v-for="(segment, index) in segments"
        :key="`line-${index}`"
        :d="linePath(segment)"
        class="trend-line"
      />

      <text
        v-if="!hasValues"
        class="no-data"
        :x="plotLeft + plotWidth / 2"
        :y="plotTop + plotHeight / 2"
        text-anchor="middle"
      >
        该窗口最高板数据缺失，不按零绘制
      </text>

      <circle
        v-for="(point, index) in points"
        :key="`point-${index}`"
        class="trend-dot"
        :cx="point.x"
        :cy="point.y"
        r="2"
      />

      <g v-for="peak in peaks" :key="`peak-${peak.index}`" class="peak">
        <circle :cx="peak.x" :cy="peak.y" r="4.2" />
        <line :x1="peak.x" :x2="peak.x" :y1="peak.y - 7" :y2="peak.y - 15" />
        <text :x="peak.x" :y="peak.y - 19" :text-anchor="peak.anchor" class="peak-label">
          {{ peak.label }}
        </text>
      </g>

      <line
        v-if="activeIndex >= 0"
        class="hover-line"
        :x1="xFor(activeIndex)"
        :x2="xFor(activeIndex)"
        :y1="plotTop"
        :y2="plotTop + plotHeight"
      />
      <circle
        v-if="activeIndex >= 0 && activeValue !== null"
        class="active-point"
        :cx="xFor(activeIndex)"
        :cy="yFor(activeValue)"
        r="4"
      />

      <text
        v-for="index in axisIndexes"
        :key="`date-${index}`"
        class="date-label"
        :x="xFor(index)"
        :y="height - 10"
        text-anchor="middle"
      >
        {{ history[index]?.date.slice(5) }}
      </text>

      <rect
        v-for="(_, index) in history"
        :key="`hit-${index}`"
        class="hit-zone"
        :x="plotLeft + (index / Math.max(1, history.length)) * plotWidth"
        :y="plotTop"
        :width="plotWidth / Math.max(1, history.length)"
        :height="plotHeight"
        @pointerenter="hoverIndex = index"
        @click="selectActive(index)"
      />
    </svg>

    <div v-if="tooltipRow" class="chart-tooltip" :style="tooltipStyle">
      <b>{{ tooltipRow.date }}</b>
      <span>
        <span>最高板</span>
        <strong>{{ tooltipRow.max_board ?? '—' }} 板</strong>
      </span>
      <span>
        <span>涨停</span>
        <strong>{{ tooltipRow.total_limit_up ?? '—' }} 家</strong>
      </span>
      <span class="names">
        {{ tooltipRow.max_board_stocks?.map((stock) => stock.name).join('、') || '最高板股票未知' }}
      </span>
      <span v-if="tooltipRow.high_board_stocks?.length" class="names">
        六板及以上：{{
          tooltipRow.high_board_stocks
            .map((stock) => `${stock.name}（${stock.boards}板）`)
            .join('、')
        }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  min-width: 480px;
}

.trend-chart {
  display: block;
  width: 100%;
  height: 360px;
  outline: none;
}

.trend-chart:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: var(--radius-sm);
}

.selected-band {
  fill: color-mix(in oklab, var(--accent) 6%, transparent);
}

.grid-line {
  stroke: var(--grid);
  stroke-width: 1;
  stroke-dasharray: 2 4;
}

.axis-value,
.date-label {
  fill: var(--muted);
  font-family: var(--mono);
  font-size: 11px;
}

.no-data {
  fill: var(--muted);
  font-size: 10px;
}

.trend-area {
  pointer-events: none;
}

.trend-line {
  fill: none;
  stroke: var(--brand);
  stroke-width: 2.1;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.trend-dot {
  fill: var(--brand);
  stroke: var(--surface);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.peak circle {
  fill: var(--brand);
  stroke: var(--surface);
  stroke-width: 1.4;
  vector-effect: non-scaling-stroke;
}

.peak line {
  stroke: color-mix(in oklab, var(--brand) 54%, transparent);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.peak-label {
  fill: var(--fg2);
  font-size: 11px;
  paint-order: stroke;
  stroke: var(--surface);
  stroke-width: 3px;
  stroke-linejoin: round;
}

.hover-line {
  stroke: var(--accent);
  stroke-width: 1;
  opacity: 0.5;
  vector-effect: non-scaling-stroke;
}

.active-point {
  fill: var(--accent);
  stroke: var(--surface);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.hit-zone {
  fill: transparent;
  cursor: crosshair;
}

.chart-tooltip {
  position: absolute;
  top: 6px;
  z-index: 2;
  width: 200px;
  display: grid;
  gap: 3px;
  padding: 8px 10px;
  border: 1px solid var(--border2);
  border-radius: 7px;
  background: color-mix(in oklab, var(--surface3) 96%, transparent);
  box-shadow: var(--shadow);
  color: var(--fg2);
  font-size: 11px;
  pointer-events: none;
  transform: translateX(-50%);
}

.chart-tooltip b {
  color: var(--fg);
  font-family: var(--mono);
  font-size: 10.5px;
}

.chart-tooltip span {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.chart-tooltip strong {
  color: var(--fg);
  font-family: var(--mono);
  font-weight: 600;
}

.chart-tooltip .names {
  display: block;
  color: var(--muted);
  overflow-wrap: anywhere;
  white-space: normal;
}
</style>
