export interface ChartPoint {
  x: number
  y: number
}

export function chartTooltipPosition(
  x: number,
  viewportLeft: number,
  viewportWidth: number,
  tooltipWidth: number,
) {
  const size = Math.min(tooltipWidth, Math.max(0, viewportWidth - 16))
  const minimum = viewportLeft + size / 2 + 8
  const maximum = viewportLeft + viewportWidth - size / 2 - 8
  return {
    left: `${Math.max(minimum, Math.min(maximum, x))}px`,
    maxWidth: `${size}px`,
  }
}

export function splitLineSegments(
  values: Array<number | null>,
  xFor: (index: number) => number,
  yFor: (value: number) => number,
): ChartPoint[][] {
  const segments: ChartPoint[][] = []
  let current: ChartPoint[] = []
  values.forEach((value, index) => {
    if (value === null) {
      if (current.length) segments.push(current)
      current = []
      return
    }
    current.push({ x: xFor(index), y: yFor(value) })
  })
  if (current.length) segments.push(current)
  return segments
}

export function linePath(points: ChartPoint[]): string {
  return points
    .map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(' ')
}

export function areaPath(points: ChartPoint[], bottom: number): string {
  if (points.length < 2) return ''
  const first = points[0]
  const last = points.at(-1)
  if (!first || !last) return ''
  return `${linePath(points)} L${last.x.toFixed(1)} ${bottom.toFixed(1)} L${first.x.toFixed(1)} ${bottom.toFixed(1)} Z`
}

export function sparseAxisIndexes(length: number, maximum = 6): number[] {
  if (length <= 0) return []
  if (length === 1) return [0]
  const count = Math.min(length, Math.max(2, maximum))
  return Array.from(
    new Set(
      Array.from({ length: count }, (_, index) => Math.round((index * (length - 1)) / (count - 1))),
    ),
  )
}
