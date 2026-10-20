import { describe, expect, it } from 'vitest'

import { formatLayerMetric, signedValueTone, stateClassificationTone } from './state-description'

describe('market state description presentation', () => {
  it('keeps percentages and percentage points distinct', () => {
    expect(formatLayerMetric('-5.126', 'pct')).toBe('-5.13%')
    expect(formatLayerMetric('12.5', 'pp')).toBe('+12.50 个百分点')
    expect(formatLayerMetric(null, 'pct')).toBe('—')
  })

  it('maps classifications without inventing a positive tone for unavailable data', () => {
    expect(stateClassificationTone('weakening')).toBe('down')
    expect(stateClassificationTone('conflicted')).toBe('warn')
    expect(stateClassificationTone('unavailable')).toBe('flat')
    expect(signedValueTone(null)).toBe('')
    expect(signedValueTone('0')).toBe('flat')
  })
})
