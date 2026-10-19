<script setup lang="ts">
import { computed, useId } from 'vue'

import { chartNumber } from '../../market/review'
import { useChartViewport } from '../../market/useChartViewport'

interface Point {
  x: number
  y: number
}

const props = withDefaults(
  defineProps<{
    values: Array<number | null | undefined>
    label: string
    height?: number
    color?: string
  }>(),
  {
    height: 38,
    color: 'var(--accent)',
  },
)
const gradientId = `spark-fill-${useId().replaceAll(':', '')}`
const { chartHost, width } = useChartViewport(40, 180)

const paths = computed(() => {
  const values = props.values.map(chartNumber)
  const numeric = values.filter((value): value is number => value !== null)
  if (!numeric.length) return []
  const minimum = Math.min(...numeric)
  const maximum = Math.max(...numeric)
  const span = maximum - minimum
  const padding = 4
  const drawableHeight = Math.max(4, props.height - padding * 2)
  const x = (index: number) =>
    values.length === 1
      ? width.value / 2
      : padding + (index / (values.length - 1)) * (width.value - padding * 2)
  const y = (value: number) =>
    span === 0
      ? props.height / 2
      : props.height - padding - ((value - minimum) / span) * drawableHeight
  const segments: Point[][] = []
  let current: Point[] = []
  values.forEach((value, index) => {
    if (value === null) {
      if (current.length) segments.push(current)
      current = []
      return
    }
    current.push({ x: x(index), y: y(value) })
  })
  if (current.length) segments.push(current)
  return segments.map((points) => {
    const line = points
      .map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
      .join(' ')
    const first = points[0]
    const last = points.at(-1)
    return {
      line,
      area:
        points.length > 1 && first && last
          ? `${line} L${last.x.toFixed(1)} ${props.height} L${first.x.toFixed(1)} ${props.height} Z`
          : '',
      marker: points.length === 1 ? last : null,
      last,
    }
  })
})
</script>

<template>
  <span ref="chartHost" class="spark-host" :style="{ height: `${height}px`, color }">
    <svg class="sparkline" :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="label">
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="currentColor" stop-opacity="0.12" />
          <stop offset="1" stop-color="currentColor" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path
        v-for="(path, index) in paths"
        :key="`area-${index}`"
        :d="path.area"
        :fill="`url(#${gradientId})`"
      />
      <path
        v-for="(path, index) in paths"
        :key="`line-${index}`"
        :d="path.line"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
        vector-effect="non-scaling-stroke"
      />
      <circle
        v-for="(path, index) in paths.filter((path) => path.marker)"
        :key="`point-${index}`"
        :cx="path.marker?.x"
        :cy="path.marker?.y"
        r="1.8"
        fill="currentColor"
        vector-effect="non-scaling-stroke"
      />
      <circle
        v-if="paths.at(-1)?.last && !paths.at(-1)?.marker"
        :cx="paths.at(-1)?.last?.x"
        :cy="paths.at(-1)?.last?.y"
        r="3"
        fill="currentColor"
        stroke="var(--surface2)"
        stroke-width="1.5"
      />
    </svg>
  </span>
</template>

<style scoped>
.spark-host,
.sparkline {
  display: block;
  width: 100%;
  min-width: 0;
  height: 100%;
}
</style>
