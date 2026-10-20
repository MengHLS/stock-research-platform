<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { IntradayBar } from '../../market/intraday'
import {
  INTRADAY_CONTINUOUS_SLOTS,
  INTRADAY_TIME_TICKS,
  continuousIntradaySegments,
  formatShares,
  formatShanghaiTime,
  intradaySlotIndex,
  positivePrice,
  symmetricIntradayRange,
} from '../../market/intraday'
import { chartNumber, formatNumber, formatSignedPercent } from '../../market/review'
import { linePath } from '../../market/chart'
import { useChartViewport } from '../../market/useChartViewport'

const props = defineProps<{
  bars: IntradayBar[]
  previousClose?: string | null
}>()

const { chartHost, width, revealX, tooltipPosition } = useChartViewport(620, 940)
const height = 360
const plotLeft = 12
const plotRight = 64
const plotTop = 24
const priceBottom = 250
const volumeTop = 282
const volumeBottom = 342
const plotWidth = computed(() => width.value - plotLeft - plotRight)
const priceHeight = priceBottom - plotTop
const volumeHeight = volumeBottom - volumeTop
const hoverIndex = ref<number | null>(null)
const timedBars = computed(() =>
  props.bars.flatMap((bar, index) => {
    const slot = intradaySlotIndex(bar.start)
    return slot === null ? [] : [{ bar, index, slot }]
  }),
)

watch(
  () => [props.bars, props.previousClose],
  () => {
    hoverIndex.value = null
  },
)

const previousClose = computed(() => positivePrice(props.previousClose))
const axis = computed(() =>
  symmetricIntradayRange(
    previousClose.value,
    timedBars.value.map(({ bar }) => bar.close),
  ),
)
const ticks = computed(() => {
  if (!axis.value) return []
  const { center, boundPct } = axis.value
  return [-1, -0.5, 0, 0.5, 1].map((ratio) => ({
    value: center * (1 + boundPct * ratio),
    pct: boundPct * ratio * 100,
  }))
})
const volumeMaximum = computed(() =>
  timedBars.value.reduce((maximum, { bar }) => {
    const value = chartNumber(bar.volume_shares)
    return value !== null && value > 0 ? Math.max(maximum, value) : maximum
  }, 0),
)
const hasVolumeValues = computed(() =>
  timedBars.value.some(({ bar }) => chartNumber(bar.volume_shares) !== null),
)
const hasPositiveVolume = computed(() => volumeMaximum.value > 0)
const latestIndex = computed(() => timedBars.value.at(-1)?.index ?? -1)
const activeIndex = computed(() => hoverIndex.value ?? latestIndex.value)
const activeBar = computed(() =>
  activeIndex.value >= 0 ? (props.bars[activeIndex.value] ?? null) : null,
)
const activePct = computed(() => {
  const close = positivePrice(activeBar.value?.close)
  const center = previousClose.value
  return close !== null && center !== null ? (close / center - 1) * 100 : null
})
const activePctTone = computed(() => {
  if (activePct.value === null) return ''
  if (activePct.value > 0) return 'up'
  if (activePct.value < 0) return 'down'
  return 'flat'
})

function xFor(index: number) {
  const slot = intradaySlotIndex(props.bars[index]?.start)
  return xForSlot(slot ?? 0)
}

function xForSlot(slot: number) {
  return plotLeft + (slot / Math.max(1, INTRADAY_CONTINUOUS_SLOTS - 1)) * plotWidth.value
}

function yFor(value: number) {
  if (!axis.value) return priceBottom
  const { top, bottom } = axis.value
  return plotTop + ((top - value) / Math.max(0.0001, top - bottom)) * priceHeight
}

function volumeY(value: number) {
  return volumeBottom - (value / Math.max(1, volumeMaximum.value)) * volumeHeight
}

const pricePaths = computed(() =>
  axis.value
    ? continuousIntradaySegments(props.bars).map((segment) =>
        linePath(segment.map(({ slot, value }) => ({ x: xForSlot(slot), y: yFor(value) }))),
      )
    : [],
)
const volumeBars = computed(() =>
  timedBars.value.flatMap(({ bar, index, slot }) => {
    const volume = chartNumber(bar.volume_shares)
    if (volume === null || volume <= 0) return []
    const previous = index ? positivePrice(props.bars[index - 1]?.close) : previousClose.value
    const close = positivePrice(bar.close)
    const top = volumeY(volume)
    const barWidth = Math.max(1, (plotWidth.value / INTRADAY_CONTINUOUS_SLOTS) * 0.68)
    return [
      {
        index,
        x: xForSlot(slot) - barWidth / 2,
        y: top,
        width: barWidth,
        height: Math.max(0.8, volumeBottom - top),
        up: close !== null && previous !== null ? close >= previous : null,
      },
    ]
  }),
)
const latest = computed(() => timedBars.value.at(-1) ?? null)
const latestPoint = computed(() => {
  if (!latest.value || !axis.value) return null
  const close = positivePrice(latest.value.bar.close)
  return close === null ? null : { slot: latest.value.slot, y: yFor(close) }
})
const tooltipStyle = computed(() => {
  if (hoverIndex.value === null) return { display: 'none' }
  return tooltipPosition(xFor(hoverIndex.value), 230)
})

function setHoverFromPointer(event: PointerEvent) {
  if (!timedBars.value.length) return
  const bounds = (event.currentTarget as SVGElement).getBoundingClientRect()
  const chartX = ((event.clientX - bounds.left) / bounds.width) * width.value
  const ratio = (chartX - plotLeft) / Math.max(1, plotWidth.value)
  const slot = Math.max(
    0,
    Math.min(INTRADAY_CONTINUOUS_SLOTS - 1, Math.round(ratio * (INTRADAY_CONTINUOUS_SLOTS - 1))),
  )
  let nearest = timedBars.value[0]
  for (const point of timedBars.value) {
    if (Math.abs(point.slot - slot) <= Math.abs((nearest?.slot ?? 0) - slot)) nearest = point
  }
  hoverIndex.value = nearest?.index ?? null
}

function moveCursor(step: number) {
  if (!timedBars.value.length) return
  const positions = timedBars.value.map(({ index }) => index)
  const current = positions.indexOf(hoverIndex.value ?? latestIndex.value)
  const next = positions[Math.max(0, Math.min(positions.length - 1, current + step))]
  if (next === undefined) return
  hoverIndex.value = next
  revealX(xFor(next))
}
</script>

<template>
  <div ref="chartHost" class="chart-wrap">
    <div class="legend">
      <span><i class="line-key" />价格</span>
      <span v-if="previousClose !== null"><i class="prev-key" />昨收</span>
      <span><i class="volume-key" />成交量 · 股</span>
      <span class="period">240 分钟 · 1 分钟线</span>
    </div>
    <svg
      class="intraday-chart"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      aria-label="当日一分钟价格与成交量；方向键可逐分钟查看"
      tabindex="0"
      @pointermove="setHoverFromPointer"
      @pointerleave="hoverIndex = null"
      @keydown.left.prevent="moveCursor(-1)"
      @keydown.right.prevent="moveCursor(1)"
      @keydown.esc="hoverIndex = null"
      @blur="hoverIndex = null"
    >
      <g v-for="tick in ticks" :key="tick.value">
        <line
          class="grid-line"
          :x1="plotLeft"
          :x2="width - plotRight"
          :y1="yFor(tick.value)"
          :y2="yFor(tick.value)"
        />
        <text class="axis-value" :x="width - plotRight + 8" :y="yFor(tick.value) + 3">
          {{ formatNumber(tick.value, 2) }}
        </text>
        <text class="axis-pct" :x="width - plotRight + 8" :y="yFor(tick.value) + 14">
          {{ formatSignedPercent(tick.pct) }}
        </text>
      </g>

      <line
        v-if="previousClose !== null"
        class="previous-line"
        :x1="plotLeft"
        :x2="width - plotRight"
        :y1="yFor(previousClose)"
        :y2="yFor(previousClose)"
      />
      <path v-for="(path, index) in pricePaths" :key="index" class="price-line" :d="path" />
      <text
        v-if="!axis"
        class="price-empty"
        :x="(plotLeft + width - plotRight) / 2"
        :y="plotTop + 42"
      >
        昨收缺失，无法计算涨跌幅及价格轴
      </text>

      <line
        class="volume-divider"
        :x1="plotLeft"
        :x2="width - plotRight"
        :y1="volumeTop - 13"
        :y2="volumeTop - 13"
      />
      <text class="axis-title" :x="plotLeft" :y="volumeTop - 2">成交量 · 股</text>
      <rect
        v-for="volume in volumeBars"
        :key="volume.index"
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
        rx="0.5"
      />
      <text
        v-if="!hasVolumeValues"
        class="volume-empty"
        :x="(plotLeft + width - plotRight) / 2"
        :y="volumeTop + 30"
      >
        该区间没有成交量数据
      </text>
      <text
        v-else-if="!hasPositiveVolume"
        class="volume-empty"
        :x="(plotLeft + width - plotRight) / 2"
        :y="volumeTop + 30"
      >
        该区间成交量为 0
      </text>

      <line
        v-if="activeIndex >= 0"
        class="hover-line"
        :x1="xFor(activeIndex)"
        :x2="xFor(activeIndex)"
        :y1="plotTop"
        :y2="volumeBottom"
      />
      <circle
        v-if="latestPoint"
        class="latest-point"
        :cx="xForSlot(latestPoint.slot)"
        :cy="Math.max(plotTop, Math.min(priceBottom, latestPoint.y))"
        r="3.2"
      />

      <text
        v-for="tick in INTRADAY_TIME_TICKS"
        :key="tick.slot"
        class="time-label"
        :x="xForSlot(tick.slot)"
        :y="height - 7"
        :text-anchor="tick.slot === 0 ? 'start' : tick.slot === 239 ? 'end' : 'middle'"
      >
        {{ tick.label }}
      </text>

      <rect
        v-for="point in timedBars"
        :key="`hit-${point.index}`"
        class="hit-zone"
        :x="xForSlot(point.slot) - plotWidth / INTRADAY_CONTINUOUS_SLOTS / 2"
        :y="plotTop"
        :width="plotWidth / INTRADAY_CONTINUOUS_SLOTS"
        :height="volumeBottom - plotTop"
        @pointerenter="hoverIndex = point.index"
      />
    </svg>

    <div v-if="activeBar && hoverIndex !== null" class="chart-tooltip" :style="tooltipStyle">
      <b>{{ formatShanghaiTime(activeBar.start) }}</b>
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
        <i>涨跌幅</i>
        <strong :class="activePctTone">
          {{ formatSignedPercent(activePct) }}
        </strong>
      </span>
      <span class="volume-tooltip">
        <i>成交量</i><strong>{{ formatShares(activeBar.volume_shares) }}</strong>
      </span>
    </div>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  min-width: 620px;
}

.legend {
  min-height: 23px;
  display: flex;
  align-items: center;
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

.line-key {
  width: 15px;
  height: 2px;
  border-radius: 999px;
  background: var(--brand);
}

.prev-key {
  width: 15px;
  height: 1px;
  border-top: 1px dashed var(--muted);
}

.volume-key {
  width: 8px;
  height: 8px;
  border-radius: 1px;
  background: color-mix(in oklab, var(--accent) 54%, var(--surface2));
}

.legend .period {
  color: var(--fg2);
  font-family: var(--mono);
}

.intraday-chart {
  display: block;
  width: 100%;
  height: 360px;
  outline: none;
}

.intraday-chart:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: var(--radius-sm);
}

.grid-line {
  stroke: var(--grid);
  stroke-width: 1;
  stroke-dasharray: 2 4;
}

.axis-value,
.axis-pct,
.axis-title,
.time-label,
.price-empty,
.previous-label,
.volume-empty {
  fill: var(--muted);
  font-family: var(--mono);
  font-size: 10.5px;
}

.axis-title {
  fill: var(--fg2);
  font-size: 10px;
}

.axis-pct {
  fill: var(--muted);
  font-size: 8.5px;
}

.volume-empty {
  text-anchor: middle;
}

.price-empty {
  fill: var(--muted);
  font-family: var(--sans);
  font-size: 11px;
  text-anchor: middle;
}

.previous-line {
  stroke: var(--muted);
  stroke-width: 1;
  stroke-dasharray: 4 4;
  opacity: 0.56;
  vector-effect: non-scaling-stroke;
}

.previous-label {
  fill: var(--muted);
  font-size: 9px;
}

.price-line {
  fill: none;
  stroke: var(--brand);
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.volume-divider {
  stroke: var(--border2);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.volume-bar {
  opacity: 0.64;
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
  opacity: 0.52;
  vector-effect: non-scaling-stroke;
}

.latest-point {
  fill: var(--brand);
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
  top: 25px;
  z-index: 2;
  width: 210px;
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

.volume-tooltip {
  grid-column: 1 / -1;
}
</style>
