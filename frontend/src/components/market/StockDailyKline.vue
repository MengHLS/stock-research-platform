<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { ReviewStockSeries } from '../../market/review'
import {
  buildCandleData,
  chartNumber,
  findPriceExtremes,
  formatNumber,
  formatSignedPercent,
} from '../../market/review'
import { linePath, sparseAxisIndexes, splitLineSegments } from '../../market/chart'
import { useChartViewport } from '../../market/useChartViewport'

const props = defineProps<{
  series: ReviewStockSeries
  selectedDate: string
}>()

const { chartHost, width, revealX, tooltipPosition } = useChartViewport(440, 760)
const height = 340
const plotLeft = 12
const plotRight = 58
const plotTop = 24
const priceBottom = 296
const plotWidth = computed(() => width.value - plotLeft - plotRight)
const plotHeight = priceBottom - plotTop
const candleWidth = computed(() =>
  Math.max(2, Math.min(10, (plotWidth.value / Math.max(1, props.series.bars.length)) * 0.58)),
)
const hoverIndex = ref<number | null>(null)

watch(
  () => props.series.symbol,
  () => {
    hoverIndex.value = null
  },
)

const candleData = computed(() => buildCandleData(props.series.bars))
const hasCompleteCoverage = computed(
  () => props.series.bars.length > 0 && candleData.value.every((values) => values !== null),
)
const validPrices = computed(() =>
  props.series.bars.flatMap((bar) => {
    const values = [
      chartNumber(bar.open),
      chartNumber(bar.high),
      chartNumber(bar.low),
      chartNumber(bar.close),
      chartNumber(bar.ma5),
      chartNumber(bar.ma20),
    ]
    return values.filter((value): value is number => value !== null)
  }),
)
const priceRange = computed(() => {
  if (!validPrices.value.length) return { minimum: 0, maximum: 1 }
  const rawMinimum = Math.min(...validPrices.value)
  const rawMaximum = Math.max(...validPrices.value)
  const padding = Math.max((rawMaximum - rawMinimum) * 0.08, Math.abs(rawMaximum) * 0.002, 0.1)
  return { minimum: rawMinimum - padding, maximum: rawMaximum + padding }
})
const ticks = computed(() => {
  const { minimum, maximum } = priceRange.value
  return Array.from({ length: 5 }, (_, index) => minimum + ((maximum - minimum) * index) / 4)
})
const axisIndexes = computed(() => sparseAxisIndexes(props.series.bars.length, 6))
const selectedIndex = computed(() =>
  props.series.bars.findIndex((bar) => bar.date === props.selectedDate),
)
const activeIndex = computed(() => hoverIndex.value ?? selectedIndex.value)
const activeBar = computed(() =>
  activeIndex.value >= 0 ? (props.series.bars[activeIndex.value] ?? null) : null,
)

function xFor(index: number) {
  return plotLeft + ((index + 0.5) / Math.max(1, props.series.bars.length)) * plotWidth.value
}

function yFor(value: number) {
  const { minimum, maximum } = priceRange.value
  return priceBottom - ((value - minimum) / Math.max(0.0001, maximum - minimum)) * plotHeight
}

const ma5Segments = computed(() =>
  splitLineSegments(
    props.series.bars.map((bar) => chartNumber(bar.ma5)),
    xFor,
    yFor,
  ),
)
const ma20Segments = computed(() =>
  splitLineSegments(
    props.series.bars.map((bar) => chartNumber(bar.ma20)),
    xFor,
    yFor,
  ),
)
const candles = computed(() =>
  candleData.value.flatMap((values, index) => {
    if (!values) return []
    const [open, close, low, high] = values
    return [
      {
        index,
        x: xFor(index),
        openY: yFor(open),
        closeY: yFor(close),
        lowY: yFor(low),
        highY: yFor(high),
        up: close >= open,
      },
    ]
  }),
)
const priceExtremes = computed(() =>
  findPriceExtremes(props.series.bars).map((extreme) => {
    const x = xFor(extreme.index)
    const y = yFor(extreme.value)
    const placeLeft = x > width.value - plotRight - 154
    return {
      ...extreme,
      x,
      y,
      labelX: x + (placeLeft ? -8 : 8),
      labelY: y + (extreme.kind === 'high' ? -10 : 18),
      textAnchor: placeLeft ? 'end' : 'start',
      label: `${hasCompleteCoverage.value ? '' : '已知'}${extreme.kind === 'high' ? '最高' : '最低'} ${formatNumber(extreme.value, 2)} · ${extreme.date.slice(5)}`,
    }
  }),
)
const tooltipStyle = computed(() => {
  if (hoverIndex.value === null || !props.series.bars.length) return { display: 'none' }
  return tooltipPosition(xFor(hoverIndex.value), 250)
})

function setHoverFromPointer(event: PointerEvent) {
  if (!props.series.bars.length) return
  const bounds = (event.currentTarget as SVGElement).getBoundingClientRect()
  const chartX = ((event.clientX - bounds.left) / bounds.width) * width.value
  const index = Math.floor(((chartX - plotLeft) / plotWidth.value) * props.series.bars.length)
  hoverIndex.value = Math.max(0, Math.min(props.series.bars.length - 1, index))
}

function moveCursor(step: number) {
  if (!props.series.bars.length) return
  const current = hoverIndex.value ?? selectedIndex.value
  hoverIndex.value = Math.max(0, Math.min(props.series.bars.length - 1, current + step))
  revealX(xFor(hoverIndex.value))
}
</script>

<template>
  <div ref="chartHost" class="chart-wrap">
    <div class="legend">
      <span><i class="legend-candle" />日 K</span>
      <span><i class="legend-line legend-line--ma5" />MA5</span>
      <span><i class="legend-line legend-line--ma20" />MA20</span>
      <span class="coverage">
        {{ series.window_actual }} 日 · 缺失 {{ series.missing_days }} 日
      </span>
    </div>
    <svg
      class="kline-chart"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-label="`${series.symbol} 个股日 K 线、MA5 与 MA20`"
      tabindex="0"
      @pointermove="setHoverFromPointer"
      @pointerleave="hoverIndex = null"
      @keydown.left.prevent="moveCursor(-1)"
      @keydown.right.prevent="moveCursor(1)"
      @keydown.esc="hoverIndex = null"
      @blur="hoverIndex = null"
    >
      <rect
        v-if="selectedIndex >= 0"
        class="selected-band"
        :x="xFor(selectedIndex) - plotWidth / Math.max(1, series.bars.length) / 2"
        :y="plotTop"
        :width="plotWidth / Math.max(1, series.bars.length)"
        :height="priceBottom - plotTop"
      />

      <g v-for="tick in ticks" :key="tick">
        <line
          class="grid-line"
          :x1="plotLeft"
          :x2="width - plotRight"
          :y1="yFor(tick)"
          :y2="yFor(tick)"
        />
        <text class="axis-value" :x="width - plotRight + 8" :y="yFor(tick) + 3">
          {{ formatNumber(tick, 2) }}
        </text>
      </g>

      <g v-for="candle in candles" :key="`candle-${candle.index}`">
        <line
          class="wick"
          :class="candle.up ? 'candle-up' : 'candle-down'"
          :x1="candle.x"
          :x2="candle.x"
          :y1="candle.highY"
          :y2="candle.lowY"
        />
        <rect
          class="body"
          :class="candle.up ? 'candle-up' : 'candle-down'"
          :x="candle.x - candleWidth / 2"
          :y="Math.min(candle.openY, candle.closeY)"
          :width="candleWidth"
          :height="Math.max(1.4, Math.abs(candle.openY - candle.closeY))"
          rx="0.8"
        />
      </g>

      <path
        v-for="(segment, index) in ma5Segments"
        :key="`ma5-${index}`"
        :d="linePath(segment)"
        class="ma-line ma5"
      />
      <path
        v-for="(segment, index) in ma20Segments"
        :key="`ma20-${index}`"
        :d="linePath(segment)"
        class="ma-line ma20"
      />

      <g v-for="extreme in priceExtremes" :key="extreme.kind" class="extreme-marker">
        <line
          class="extreme-guide"
          :x1="plotLeft"
          :x2="width - plotRight"
          :y1="extreme.y"
          :y2="extreme.y"
        />
        <circle :cx="extreme.x" :cy="extreme.y" r="3.2" />
        <text :x="extreme.labelX" :y="extreme.labelY" :text-anchor="extreme.textAnchor">
          {{ extreme.label }}
        </text>
      </g>

      <line
        v-if="activeIndex >= 0"
        class="hover-line"
        :x1="xFor(activeIndex)"
        :x2="xFor(activeIndex)"
        :y1="plotTop"
        :y2="priceBottom"
      />

      <text
        v-for="index in axisIndexes"
        :key="`date-${index}`"
        class="date-label"
        :x="xFor(index)"
        :y="height - 10"
        text-anchor="middle"
      >
        {{ series.bars[index]?.date.slice(5) }}
      </text>

      <rect
        v-for="(_, index) in series.bars"
        :key="`hit-${index}`"
        class="hit-zone"
        :x="plotLeft + (index / Math.max(1, series.bars.length)) * plotWidth"
        :y="plotTop"
        :width="plotWidth / Math.max(1, series.bars.length)"
        :height="priceBottom - plotTop"
        @pointerenter="hoverIndex = index"
      />
    </svg>

    <div v-if="activeBar && hoverIndex !== null" class="chart-tooltip" :style="tooltipStyle">
      <b>{{ activeBar.date }}</b>
      <span>
        <i>开</i>
        <strong>{{ formatNumber(activeBar.open, 2) }}</strong>
      </span>
      <span>
        <i>高</i>
        <strong>{{ formatNumber(activeBar.high, 2) }}</strong>
      </span>
      <span>
        <i>低</i>
        <strong>{{ formatNumber(activeBar.low, 2) }}</strong>
      </span>
      <span>
        <i>收</i>
        <strong>{{ formatNumber(activeBar.close, 2) }}</strong>
      </span>
      <span>
        <i>涨跌</i>
        <strong>{{ formatSignedPercent(activeBar.change_pct) }}</strong>
      </span>
      <span>
        <i class="ma5-text">MA5</i>
        <strong>{{ formatNumber(activeBar.ma5, 2) }}</strong>
      </span>
      <span>
        <i class="ma20-text">MA20</i>
        <strong>{{ formatNumber(activeBar.ma20, 2) }}</strong>
      </span>
    </div>

    <p class="chart-note">仅绘制完整 OHLC；缺失日不补蜡烛，MA 在历史样本不完整时断开。</p>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  min-width: 440px;
  display: grid;
  gap: 3px;
}

.legend {
  display: flex;
  align-items: center;
  gap: 14px;
  color: var(--muted);
  font-size: 11.5px;
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.legend .coverage {
  margin-left: auto;
  font-family: var(--mono);
}

.legend i {
  display: inline-block;
}

.legend-candle {
  width: 8px;
  height: 11px;
  border-radius: 1px;
  background: var(--up);
}

.legend-line {
  width: 15px;
  height: 2px;
}

.legend-line--ma5 {
  background: var(--accent);
}

.legend-line--ma20 {
  background: var(--warn);
}

.kline-chart {
  display: block;
  width: 100%;
  height: 340px;
  outline: none;
}

.kline-chart:focus-visible {
  border-radius: var(--radius-sm);
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}

.selected-band {
  fill: color-mix(in oklab, var(--accent) 7%, transparent);
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

.wick {
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.body {
  stroke-width: 0;
}

.candle-up {
  fill: var(--up);
  stroke: var(--up);
}

.candle-down {
  fill: var(--down);
  stroke: var(--down);
}

.ma-line {
  fill: none;
  stroke-width: 1.35;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.ma5 {
  stroke: var(--accent);
}

.ma20 {
  stroke: var(--warn);
}

.extreme-marker circle {
  fill: var(--brand);
  stroke: var(--surface);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.extreme-marker text {
  fill: var(--fg);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 650;
  paint-order: stroke;
  stroke: var(--bg2);
  stroke-width: 3px;
  stroke-linejoin: round;
}

.extreme-guide {
  stroke: color-mix(in oklab, var(--brand) 44%, transparent);
  stroke-width: 1;
  stroke-dasharray: 3 5;
  vector-effect: non-scaling-stroke;
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
  top: 26px;
  z-index: 2;
  width: 250px;
  display: grid;
  grid-template-columns: auto auto;
  gap: 3px 14px;
  padding: 9px 11px;
  border: 1px solid var(--border2);
  border-radius: 7px;
  background: color-mix(in oklab, var(--surface3) 96%, transparent);
  box-shadow: var(--shadow);
  color: var(--fg2);
  font-size: 11.5px;
  pointer-events: none;
  transform: translateX(-50%);
}

.chart-tooltip b {
  grid-column: 1 / -1;
  margin-bottom: 2px;
  color: var(--fg);
  font-family: var(--mono);
  font-size: 12px;
}

.chart-tooltip span {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.chart-tooltip i {
  color: var(--muted);
  font-style: normal;
}

.chart-tooltip strong {
  color: var(--fg);
  font-family: var(--mono);
  font-weight: 600;
}

.ma5-text {
  color: var(--accent) !important;
}

.ma20-text {
  color: var(--warn) !important;
}

.chart-note {
  margin: 0;
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.55;
}
</style>
