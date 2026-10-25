import { describe, expect, it } from 'vitest'

import { positionBandLabel, positionScopeLabel } from './first-board-classifier'

describe('first-board classifier display helpers', () => {
  it('keeps every position scope explicit instead of rounding it to a generic label', () => {
    expect((['high', 'mid_or_low', 'low', 'mid', 'any'] as const).map(positionScopeLabel)).toEqual([
      '仅高位',
      '中位或低位',
      '仅低位',
      '仅中位',
      '不限位置',
    ])
  })

  it('distinguishes unknown position from a real boundary band', () => {
    expect(positionBandLabel('low')).toBe('60日低位')
    expect(positionBandLabel('high')).toBe('60日高位')
    expect(positionBandLabel('unknown')).toBe('60日位置未知')
  })
})
