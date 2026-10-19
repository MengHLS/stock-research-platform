import { describe, expect, it } from 'vitest'

import {
  areaPath,
  chartTooltipPosition,
  linePath,
  sparseAxisIndexes,
  splitLineSegments,
} from './chart'

describe('chart geometry', () => {
  it('keeps tooltips in the visible scroll viewport rather than the full plot', () => {
    expect(chartTooltipPosition(470, 0, 320, 200)).toEqual({ left: '212px', maxWidth: '200px' })
    expect(chartTooltipPosition(20, 160, 320, 200)).toEqual({ left: '268px', maxWidth: '200px' })
    expect(chartTooltipPosition(120, 0, 160, 200)).toEqual({ left: '80px', maxWidth: '144px' })
  })

  it('breaks line geometry where a value is missing', () => {
    const segments = splitLineSegments(
      [1, 2, null, 4, null, 6, 7],
      (index) => index * 10,
      (value) => 100 - value,
    )
    expect(segments).toEqual([
      [
        { x: 0, y: 99 },
        { x: 10, y: 98 },
      ],
      [{ x: 30, y: 96 }],
      [
        { x: 50, y: 94 },
        { x: 60, y: 93 },
      ],
    ])
  })

  it('builds matched line and area paths', () => {
    const points = [
      { x: 0, y: 8 },
      { x: 10, y: 4 },
    ]
    expect(linePath(points)).toBe('M0.0 8.0 L10.0 4.0')
    expect(areaPath(points, 12)).toBe('M0.0 8.0 L10.0 4.0 L10.0 12.0 L0.0 12.0 Z')
  })

  it('spaces date labels evenly without crowding the final two dates', () => {
    const indexes = sparseAxisIndexes(14, 6)
    expect(indexes).toEqual([0, 3, 5, 8, 10, 13])
    expect(Math.min(...indexes.slice(1).map((index, i) => index - indexes[i]!))).toBeGreaterThan(1)
  })

  it('handles empty and single-day windows without duplicate labels', () => {
    expect(sparseAxisIndexes(0)).toEqual([])
    expect(sparseAxisIndexes(1)).toEqual([0])
    expect(sparseAxisIndexes(2)).toEqual([0, 1])
  })
})
