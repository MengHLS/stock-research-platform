<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { IndexSeries } from '../../market/review'
import { buildCandleData, chartNumber, findPriceExtremes, formatNumber } from '../../market/review'
import { linePath, sparseAxisIndexes, splitLineSegments } from '../../market/chart'
import { useChartViewport } from '../../market/useChartViewport'

const props = defineProps<{
  bars: IndexSeries['bars']
  selectedDate: string
}>()

const { chartHost, width, revealX, tooltipPosition } = useChartViewport(480, 820)
const height = 420
const plotLeft = 12
const plotRight = 60
const plotTop = 40
const priceBottom = 286
const volumeTop = 318
const volumeBottom = 382
const plotWidth = computed(() => width.value - plotLeft - plotRight)
const plotHeight = priceBottom - plotTop
const volumeHeight = volumeBottom - volumeTop
const candleWidth = computed(() =>
  Math.max(2, Math.min(9, (plotWidth.value / Math.max(1, props.bars.length)) * 0.56)),
)
const hoverIndex = ref<number | null>(null)
watch(
  () => props.bars,
  () => {
    hoverIndex.value = null
  },
)

const candleData = computed(() => buildCandleData(props.bars))
const hasCompletePriceCoverage = computed(
  () => props.bars.length > 0 && candleData.value.every((values) => values !== null),
)
const validPrices = computed(() =>
  props.bars.flatMap((bar) => {
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
const axisIndexes = computed(() => sparseAxisIndexes(props.bars.length, 7))
const selectedIndex = computed(() => props.bars.findIndex((bar) => bar.date === props.selectedDate))
const activeIndex = computed(() => hoverIndex.value ?? selectedIndex.value)
const activeBar = computed(() =>
  activeIndex.value >= 0 ? (props.bars[activeIndex.value] ?? null) : null,
)

function xFor(index: number) {
  return plotLeft + ((index + 0.5) / Math.max(1, props.bars.length)) * plotWidth.value
}

function yFor(value: number) {
  const { minimum, maximum } = priceRange.value
  return priceBottom - ((value - minimum) / Math.max(0.0001, maximum - minimum)) * plotHeight
}

const volumeMaximum = computed(() =>
  props.bars.reduce((maximum, bar) => {
    const value = chartNumber(bar.volume_source)
    return value !== null && value > 0 ? Math.max(maximum, value) : maximum
  }, 0),
)
const hasVolume = computed(() => volumeMaximum.value > 0)
const volumeTicks = computed(() => {
  if (!hasVolume.value) return []
  return [0, volumeMaximum.value / 2, volumeMaximum.value]
})

function volumeY(value: number) {
  return volumeBottom - (value / Math.max(1, volumeMaximum.value)) * volumeHeight
}

function formatVolume(value: string | number | null | undefined) {
  const number = chartNumber(value)
  if (number === null) return '—'
  return new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(number)
}

const ma5Segments = computed(() =>
  splitLineSegments(
    props.bars.map((bar) => chartNumber(bar.ma5)),
    xFor,
    yFor,
  ),
)
const ma20Segments = computed(() =>
  splitLineSegments(
    props.bars.map((bar) => chartNumber(bar.ma20)),
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
const volumeBars = computed(() =>
  props.bars.flatMap((bar, index) => {
    const value = chartNumber(bar.volume_source)
    if (value === null || value <= 0) return []
    const top = volumeY(value)
    const open = chartNumber(bar.open)
    const close = chartNumber(bar.close)
    return [
      {
        index,
        x: xFor(index) - candleWidth.value / 2,
        y: top,
        width: candleWidth.value,
        height: Math.max(1, volumeBottom - top),
        up: open !== null && close !== null ? close >= open : null,
      },
    ]
  }),
)
const priceExtremes = computed(() =>
  findPriceExtremes(props.bars).map((extreme) => {
    const x = xFor(extreme.index)
    const y = yFor(extreme.value)
    const placeLeft = x > width.value - plotRight - 148
    return {
      ...extreme,
      x,
      y,
      labelX: x + (placeLeft ? -8 : 8),
      labelY: y + (extreme.kind === 'high' ? -9 : 16),
      textAnchor: placeLeft ? 'end' : 'start',
      label: `${hasCompletePriceCoverage.value ? '' : '已知'}${extreme.kind === 'high' ? '最高' : '最低'} ${formatNumber(extreme.value, 2)} · ${extreme.date.slice(5)}`,
    }
  }),
)
const tooltipStyle = computed(() => {
  if (hoverIndex.value === null || !props.bars.length) return { display: 'none' }
  return tooltipPosition(xFor(hoverIndex.value), 244)
})

function setHoverFromPointer(event: PointerEvent) {
  if (!props.bars.length) return
  const bounds = (event.currentTarget as SVGElement).getBoundingClientRect()
  const chartX = ((event.clientX - bounds.left) / bounds.width) * width.value
  const index = Math.floor(((chartX - plotLeft) / plotWidth.value) * props.bars.length)
  hoverIndex.value = Math.max(0, Math.min(props.bars.length - 1, index))
}

function moveCursor(step: number) {
  if (!props.bars.length) return
  const current = hoverIndex.value ?? selectedIndex.value
  hoverIndex.value = Math.max(0, Math.min(props.bars.length - 1, current + step))
  revealX(xFor(hoverIndex.value))
}
</script>

<template>
  <div ref="chartHost" class="chart-wrap">
    <div class="legend">
      <span><i class="legend-candle" />日 K</span>
      <span><i class="legend-line legend-line--ma5" />MA5</span>
      <span><i class="legend-line legend-line--ma20" />MA20</span>
      <span><i class="legend-volume" />成交量 · 源单位</span>
    </div>
    <svg
      class="kline-chart"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      aria-label="指数日 K 线、MA5、MA20 与成交量"
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
        :x="xFor(selectedIndex) - plotWidth / Math.max(1, bars.length) / 2"
        :y="plotTop"
        :width="plotWidth / Math.max(1, bars.length)"
        :height="volumeBottom - plotTop"
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
        class="volume-divider"
        :x1="plotLeft"
        :x2="width - plotRight"
        :y1="volumeTop - 12"
        :y2="volumeTop - 12"
      />
      <template v-if="hasVolume">
        <text class="axis-title" :x="plotLeft" :y="volumeTop - 2">成交量 · 源单位</text>
        <g v-for="tick in volumeTicks" :key="`volume-tick-${tick}`">
          <line
            class="grid-line"
            :x1="plotLeft"
            :x2="width - plotRight"
            :y1="volumeY(tick)"
            :y2="volumeY(tick)"
          />
          <text class="axis-value" :x="width - plotRight + 8" :y="volumeY(tick) + 3">
            {{ formatVolume(tick) }}
          </text>
        </g>
        <rect
          v-for="volume in volumeBars"
          :key="`volume-${volume.index}`"
          class="volume-bar"
          :class="{
            'volume-up': volume.up === true,
            'volume-down': volume.up === false,
            'volume-flat': volume.up === null,
          }"
          :x="volume.x"
          :y="volume.y"
          :width="volume.width"
          :height="volume.height"
          rx="0.6"
        />
      </template>
      <text v-else class="volume-empty" :x="(plotLeft + width - plotRight) / 2" :y="volumeTop + 34">
        该区间没有成交量数据
      </text>

      <line
        v-if="activeIndex >= 0"
        class="hover-line"
        :x1="xFor(activeIndex)"
        :x2="xFor(activeIndex)"
        :y1="plotTop"
        :y2="volumeBottom"
      />

      <text
        v-for="index in axisIndexes"
        :key="`date-${index}`"
        class="date-label"
        :x="xFor(index)"
        :y="height - 10"
        text-anchor="middle"
      >
        {{ bars[index]?.date.slice(5) }}
      </text>

      <rect
        v-for="(_, index) in bars"
        :key="`hit-${index}`"
        class="hit-zone"
        :x="plotLeft + (index / Math.max(1, bars.length)) * plotWidth"
        :y="plotTop"
        :width="plotWidth / Math.max(1, bars.length)"
        :height="volumeBottom - plotTop"
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
        <i class="ma5-text">MA5</i>
        <strong>{{ formatNumber(activeBar.ma5, 2) }}</strong>
      </span>
      <span>
        <i class="ma20-text">MA20</i>
        <strong>{{ formatNumber(activeBar.ma20, 2) }}</strong>
      </span>
      <span class="volume-tooltip">
        <i>成交量</i>
        <strong>{{ formatVolume(activeBar.volume_source) }}</strong>
      </span>
    </div>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  display: grid;
  gap: 2px;
  min-width: 480px;
}

.legend {
  display: flex;
  justify-content: flex-end;
  gap: 14px;
  color: var(--muted);
  font-size: 10px;
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.legend i {
  display: inline-block;
}

.legend-candle {
  width: 7px;
  height: 10px;
  background: var(--up);
  border-radius: 1px;
}

.legend-line {
  width: 14px;
  height: 2px;
}

.legend-line--ma5 {
  background: var(--accent);
}

.legend-line--ma20 {
  background: var(--warn);
}

.legend-volume {
  width: 9px;
  height: 7px;
  border-radius: 1px;
  background: color-mix(in oklab, var(--accent) 42%, var(--surface2));
}

.kline-chart {
  display: block;
  width: 100%;
  height: 420px;
  outline: none;
}

.kline-chart:focus-visible {
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
.date-label,
.axis-title,
.volume-empty {
  fill: var(--muted);
  font-family: var(--mono);
  font-size: 10.5px;
}

.axis-title {
  fill: var(--fg2);
  font-size: 10px;
  letter-spacing: 0.02em;
}

.volume-empty {
  text-anchor: middle;
  font-size: 10.5px;
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
  stroke-width: 1.25;
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
  font-size: 10px;
  font-weight: 650;
  paint-order: stroke;
  stroke: var(--bg2);
  stroke-width: 3px;
  stroke-linejoin: round;
}

.extreme-guide {
  stroke: color-mix(in oklab, var(--brand) 46%, transparent);
  stroke-width: 1;
  stroke-dasharray: 3 5;
  vector-effect: non-scaling-stroke;
}

.volume-divider {
  stroke: var(--border2);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.volume-bar {
  opacity: 0.62;
}

.volume-up {
  fill: var(--up);
}

.volume-down {
  fill: var(--down);
}

.volume-flat {
  fill: var(--muted);
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
  top: 22px;
  z-index: 2;
  width: 244px;
  display: grid;
  grid-template-columns: auto auto;
  gap: 2px 14px;
  padding: 8px 10px;
  border: 1px solid var(--border2);
  border-radius: 7px;
  background: color-mix(in oklab, var(--surface3) 96%, transparent);
  box-shadow: var(--shadow);
  color: var(--fg2);
  font-size: 10px;
  pointer-events: none;
  transform: translateX(-50%);
}

.chart-tooltip b {
  grid-column: 1 / -1;
  margin-bottom: 2px;
  color: var(--fg);
  font-family: var(--mono);
  font-size: 10.5px;
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

.volume-tooltip {
  grid-column: 1 / -1;
}
</style>
