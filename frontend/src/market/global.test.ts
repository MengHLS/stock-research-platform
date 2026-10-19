import { describe, expect, it } from 'vitest'

import { globalDetailBars, groupGlobalItems, marketBreadth, type GlobalMarketItem } from './global'

function item(
  key: string,
  group: GlobalMarketItem['group'],
  changePct: string | null,
): GlobalMarketItem {
  return {
    key,
    name: key,
    symbol: key,
    group,
    market: 'TEST',
    currency: 'USD',
    unit: '点',
    precision: 2,
    assessment: changePct === null ? 'missing' : 'available',
    quote:
      changePct === null
        ? null
        : {
            price: '100',
            previous_close: '99',
            open: '99',
            high: '101',
            low: '98',
            change: '1',
            change_pct: changePct,
            quote_time: '2026-10-19T08:00:00Z',
          },
    bars: [],
    issues: [],
  }
}

const items = [
  item('nasdaq', 'us', '1.20'),
  item('gold', 'commodity', '0'),
  item('kospi', 'asia', '-0.30'),
  item('missing', 'cn', null),
]

describe('global market helpers', () => {
  it('keeps the reviewed group order and filters to one group', () => {
    expect(groupGlobalItems(items).map((group) => group.key)).toEqual([
      'us',
      'asia',
      'cn',
      'commodity',
    ])
    expect(groupGlobalItems(items, 'asia')).toEqual([
      {
        key: 'asia',
        label: '日韩 / 半导体',
        note: '亚太市场与芯片产业链',
        items: [items[2]],
      },
    ])
  })

  it('counts breadth without treating an unavailable quote as flat', () => {
    expect(marketBreadth(items)).toEqual({
      advancing: 1,
      declining: 1,
      flat: 1,
      unavailable: 1,
    })
  })

  it('treats a missing change percentage as unavailable rather than flat', () => {
    const missingChange = item('missing-change', 'us', '1.00')
    if (!missingChange.quote) throw new Error('test fixture quote is required')
    missingChange.quote.change_pct = null

    expect(marketBreadth([missingChange])).toEqual({
      advancing: 0,
      declining: 0,
      flat: 0,
      unavailable: 1,
    })
  })

  it('derives chart moving averages only when enough closes exist', () => {
    const withBars = item('nasdaq', 'us', '1.20')
    withBars.bars = ['100', '101', '102', '103', '104', '105'].map((close, index) => ({
      date: `2026-10-${String(12 + index).padStart(2, '0')}`,
      open: close,
      high: close,
      low: close,
      close,
      change_pct: '1.00',
    }))

    const detail = globalDetailBars(withBars)
    expect(detail[3]?.ma5).toBeNull()
    expect(detail[4]?.ma5).toBe('102.00')
    expect(detail[5]?.ma5).toBe('103.00')
    expect(detail[5]?.ma20).toBeNull()
    expect(detail[5]?.volume_source).toBeNull()
  })
})
