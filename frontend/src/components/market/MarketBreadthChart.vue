<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'

import type { ReviewHistoryRow } from '../../market/review'
import { chartNumber } from '../../market/review'
import { areaPath, linePath, sparseAxisIndexes, splitLineSegments } from '../../market/chart'
import { useChartViewport } from '../../market/useChartViewport'

const props = defineProps<{
  rows: ReviewHistoryRow[]
  selectedDate: string
}>()

const { chartHost, width, revealX, tooltipPosition } = useChartViewport(640, 760)
const height = 456
const plotLeft = 54
const plotRight = 70
const plotWidth = computed(() => width.value - plotLeft - plotRight)
const gradientId = `breadth-fill-${useId().replaceAll(':', '')}`
const hoverIndex = ref<number | null>(null)
watch(
  () => props.rows,
  () => {
    hoverIndex.value = null
  },
)

const selectedIndex = computed(() => props.rows.findIndex((row) => row.date === props.selectedDate))
const axisIndexes = computed(() =>
  sparseAxisIndexes(props.rows.length, Math.max(6, Math.min(12, Math.floor(width.value / 180)))),
)
const xFor = (index: number) =>
  plotLeft + ((index + 0.5) / Math.max(1, props.rows.length)) * plotWidth.value

interface BandDefinition {
  key: 'limit' | 'turnover' | 'margin'
  label: string
  unit: string
  top: number
  height: number
  color: string
  bar: boolean
}

const definitions: BandDefinition[] = [
  {
    key: 'limit',
    label: '涨停家数',
    unit: '家',
    top: 18,
    height: 114,
    color: 'var(--up)',
    bar: true,
  },
  {
    key: 'turnover',
    label: '成交额',
    unit: '亿',
    top: 164,
    height: 114,
    color: 'var(--vol)',
    bar: false,
  },
  {
    key: 'margin',
    label: '两融余额',
    unit: '亿',
    top: 310,
    height: 114,
    color: 'var(--margin)',
    bar: false,
  },
]

function valueFor(row: ReviewHistoryRow | undefined, key: BandDefinition['key']) {
  if (!row) return null
  if (key === 'limit') return row.total_limit_up ?? null
  if (key === 'turnover') return chartNumber(row.turnover_100m_cny)
  return chartNumber(row.margin_balance_100m_cny)
}

const bands = computed(() =>
  definitions.map((definition) => {
    const values = props.rows.map((row) => valueFor(row, definition.key))
    const known = values.filter((value): value is number => value !== null)
    const rawMinimum = known.length ? Math.min(...known) : 0
    const rawMaximum = known.length ? Math.max(...known) : 1
    const minimum =
      definition.key === 'limit' ? 0 : rawMaximum === rawMinimum ? rawMinimum * 0.98 : rawMinimum
    const maximum =
      rawMaximum === minimum ? minimum + Math.max(1, Math.abs(minimum) * 0.02) : rawMaximum
    const yFor = (value: number) =>
      definition.top +
      definition.height -
      ((value - minimum) / (maximum - minimum)) * definition.height
    const segments = splitLineSegments(values, xFor, yFor)
    const areaSegments = segments
      .map((points) => areaPath(points, definition.top + definition.height))
      .filter(Boolean)
    const bars = values.map((value, index) =>
      value === null
        ? null
        : {
            index,
            value,
            x: xFor(index),
            y: yFor(value),
            base: definition.top + definition.height,
          },
    )
    const lastPoint = segments
      .filter((points) => points.length)
      .at(-1)
      ?.at(-1)
    return {
      ...definition,
      hasData: known.length > 0,
      minimum,
      maximum,
      segments,
      areaSegments,
      bars,
      lastPoint,
      yMaximum: yFor(maximum),
      yMinimum: yFor(minimum),
      currentValue: valueFor(props.rows[selectedIndex.value], definition.key),
      isolatedPoints: segments.filter((points) => points.length === 1).flat(),
    }
  }),
)

const activeIndex = computed(() => hoverIndex.value ?? selectedIndex.value)
const tooltipRow = computed(() =>
  hoverIndex.value !== null ? (props.rows[hoverIndex.value] ?? null) : null,
)
const tooltipStyle = computed(() => {
  if (hoverIndex.value === null || !props.rows.length) return { display: 'none' }
  return tooltipPosition(xFor(hoverIndex.value), 200)
})

function updateHover(event: PointerEvent) {
  if (!props.rows.length) return
  const bounds = (event.currentTarget as SVGElement).getBoundingClientRect()
  const chartX = ((event.clientX - bounds.left) / bounds.width) * width.value
  const index = Math.floor(((chartX - plotLeft) / plotWidth.value) * props.rows.length)
  hoverIndex.value = Math.max(0, Math.min(props.rows.length - 1, index))
}

function moveCursor(step: number) {
  if (!props.rows.length) return
  hoverIndex.value = Math.max(
    0,
    Math.min(props.rows.length - 1, (hoverIndex.value ?? selectedIndex.value) + step),
  )
  revealX(xFor(hoverIndex.value))
}

function formatValue(value: number | null): string {
  if (value === null) return '—'
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: value < 100 ? 1 : 0,
  }).format(value)
}

function formatAxis(value: number): string {
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(1)}万`
  return formatValue(value)
}
</script>

<template>
  <div ref="chartHost" class="chart-wrap">
    <svg
      class="breadth-chart"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      aria-label="涨停家数、成交额和两融余额历史图；方向键逐日查看"
      tabindex="0"
      @pointermove="updateHover"
      @pointerleave="hoverIndex = null"
      @keydown.left.prevent="moveCursor(-1)"
      @keydown.right.prevent="moveCursor(1)"
      @keydown.esc="hoverIndex = null"
      @blur="hoverIndex = null"
    >
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--vol)" stop-opacity="0.1" />
          <stop offset="1" stop-color="var(--vol)" stop-opacity="0" />
        </linearGradient>
      </defs>

      <rect
        v-if="selectedIndex >= 0"
        class="selected-band"
        :x="xFor(selectedIndex) - plotWidth / Math.max(1, rows.length) / 2"
        y="13"
        :width="plotWidth / Math.max(1, rows.length)"
        :height="
          bands.at(-1)?.top ? (bands.at(-1)?.top ?? 0) + (bands.at(-1)?.height ?? 0) - 13 : 280
        "
      />

      <g v-for="band in bands" :key="band.key">
        <text class="band-title" x="0" :y="band.top - 8">
          {{ band.label }}
          <tspan>({{ band.unit }})</tspan>
        </text>
        <line
          v-if="band.hasData"
          class="grid-line"
          :x1="plotLeft"
          :x2="width - plotRight"
          :y1="band.yMaximum"
          :y2="band.yMaximum"
        />
        <line
          v-if="band.hasData"
          class="grid-line"
          :x1="plotLeft"
          :x2="width - plotRight"
          :y1="band.yMinimum"
          :y2="band.yMinimum"
        />
        <text
          v-if="band.hasData"
          class="axis-value"
          :x="plotLeft - 8"
          :y="band.yMaximum + 3"
          text-anchor="end"
        >
          {{ formatAxis(band.maximum) }}
        </text>
        <text
          v-if="band.hasData"
          class="axis-value"
          :x="plotLeft - 8"
          :y="band.yMinimum + 3"
          text-anchor="end"
        >
          {{ formatAxis(band.minimum) }}
        </text>
        <text class="axis-value" :x="width - plotRight + 10" :y="band.top + 4">当前</text>
        <text
          class="current-value"
          :fill="band.color"
          :x="width - plotRight + 10"
          :y="band.top + 22"
        >
          {{ formatValue(band.currentValue) }}
        </text>

        <template v-if="band.bar && band.hasData">
          <template v-for="bar in band.bars" :key="`${band.key}-${bar?.index}`">
            <rect
              v-if="bar"
              class="bar"
              :x="
                bar.x - Math.max(2, Math.min(18, (plotWidth / Math.max(1, rows.length)) * 0.54)) / 2
              "
              :y="bar.y"
              :width="Math.max(2, Math.min(18, (plotWidth / Math.max(1, rows.length)) * 0.54))"
              :height="Math.max(1, bar.base - bar.y)"
              rx="1"
            />
          </template>
        </template>
        <template v-else-if="!band.bar && band.hasData">
          <path
            v-for="(area, index) in band.areaSegments"
            :key="`${band.key}-area-${index}`"
            :d="area"
            :fill="
              band.key === 'turnover'
                ? `url(#${gradientId})`
                : 'color-mix(in oklab, var(--margin) 11%, transparent)'
            "
          />
          <path
            v-for="(segment, index) in band.segments"
            :key="`${band.key}-line-${index}`"
            :d="linePath(segment)"
            class="series-line"
            :class="`series-line--${band.key}`"
          />
          <circle
            v-if="band.lastPoint"
            :cx="band.lastPoint.x"
            :cy="band.lastPoint.y"
            r="2.6"
            class="last-point"
            :class="`last-point--${band.key}`"
          />
          <circle
            v-for="(point, index) in band.isolatedPoints"
            :key="`${band.key}-isolated-${index}`"
            :cx="point.x"
            :cy="point.y"
            r="2.6"
            :fill="band.color"
          />
        </template>
        <text
          v-else
          class="band-empty"
          :x="plotLeft + plotWidth / 2"
          :y="band.top + band.height / 2"
          text-anchor="middle"
        >
          该序列缺失，不按零绘制
        </text>
      </g>

      <line
        v-if="activeIndex >= 0"
        class="hover-line"
        :x1="xFor(activeIndex)"
        :x2="xFor(activeIndex)"
        y1="18"
        :y2="bands.at(-1)?.top ? (bands.at(-1)?.top ?? 0) + (bands.at(-1)?.height ?? 0) : 284"
      />

      <text
        v-for="index in axisIndexes"
        :key="`axis-${index}`"
        class="date-label"
        :x="xFor(index)"
        :y="height - 8"
        text-anchor="middle"
      >
        {{ rows[index]?.date.slice(5) }}
      </text>

      <rect
        v-for="(_, index) in rows"
        :key="`hit-${index}`"
        class="hit-zone"
        :x="plotLeft + (index / Math.max(1, rows.length)) * plotWidth"
        y="12"
        :width="plotWidth / Math.max(1, rows.length)"
        :height="height - 28"
        @pointerenter="hoverIndex = index"
      />
    </svg>

    <div v-if="tooltipRow" class="chart-tooltip" :style="tooltipStyle">
      <b>{{ tooltipRow.date }}</b>
      <span>
        <em class="tooltip-dot tooltip-dot--up" />
        <span>涨停</span>
        <strong>{{ formatValue(valueFor(tooltipRow, 'limit')) }} 家</strong>
      </span>
      <span>
        <em class="tooltip-dot tooltip-dot--vol" />
        <span>成交额</span>
        <strong>{{ formatValue(valueFor(tooltipRow, 'turnover')) }} 亿</strong>
      </span>
      <span>
        <em class="tooltip-dot tooltip-dot--margin" />
        <span>两融</span>
        <strong>{{ formatValue(valueFor(tooltipRow, 'margin')) }} 亿</strong>
      </span>
    </div>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  min-width: 640px;
}

.breadth-chart {
  display: block;
  width: 100%;
  height: 456px;
  overflow: visible;
}

.breadth-chart:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
  border-radius: var(--radius-sm);
}

.selected-band {
  fill: color-mix(in oklab, var(--accent) 7%, transparent);
}

.band-title {
  fill: var(--muted);
  font-size: 11px;
  font-weight: 600;
}

.band-title tspan {
  font-weight: 400;
}

.grid-line {
  stroke: var(--grid);
  stroke-width: 1;
}

.axis-value,
.date-label {
  fill: var(--muted);
  font-family: var(--mono);
  font-size: 10.5px;
}

.band-empty {
  fill: var(--muted);
  font-size: 10px;
}

.current-value {
  font-family: var(--mono);
  font-size: 11.5px;
  font-weight: 650;
}

.bar {
  fill: color-mix(in oklab, var(--up) 76%, transparent);
}

.series-line {
  fill: none;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.series-line--turnover {
  stroke: var(--vol);
}

.series-line--margin {
  stroke: var(--margin);
}

.last-point {
  stroke: var(--surface);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.last-point--turnover {
  fill: var(--vol);
}

.last-point--margin {
  fill: var(--margin);
}

.hover-line {
  stroke: var(--accent);
  stroke-width: 1;
  opacity: 0.55;
  vector-effect: non-scaling-stroke;
}

.hit-zone {
  fill: transparent;
  cursor: crosshair;
}

.chart-tooltip {
  position: absolute;
  top: 8px;
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
  margin-bottom: 2px;
  color: var(--fg);
  font-family: var(--mono);
  font-size: 10.5px;
}

.chart-tooltip span {
  display: flex;
  align-items: center;
  gap: 5px;
}

.chart-tooltip strong {
  margin-left: auto;
  color: var(--fg);
  font-family: var(--mono);
  font-weight: 600;
}

.tooltip-dot {
  width: 7px;
  height: 7px;
  border-radius: 2px;
}

.tooltip-dot--up {
  background: var(--up);
}

.tooltip-dot--vol {
  background: var(--vol);
}

.tooltip-dot--margin {
  background: var(--margin);
}

@media (max-width: 760px) {
  .chart-wrap {
    min-width: 640px;
  }
}
</style>
