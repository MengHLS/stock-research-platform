import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import MarketIndexDetail from '../components/market/MarketIndexDetail.vue'
import MarketIndexPanel from '../components/market/MarketIndexPanel.vue'
import type { ReviewIndices } from './review'

const instruments = [
  ['000001.SH', '上证指数', '3030'],
  ['399001.SZ', '深证成指', '10120'],
  ['000300.SH', '沪深300', '3980'],
  ['000905.SH', '中证500', '6120'],
  ['399006.SZ', '创业板指', '4030'],
  ['000688.SH', '科创50', '1030'],
] as const

describe('market index panel', () => {
  it('renders all six reviewed indices and their missing public history independently', async () => {
    const items = instruments.map(([symbol, name, close]) => ({
      symbol,
      name,
      coverage: {
        status: symbol === '399006.SZ' ? 'missing' : 'available',
        row_count: symbol === '399006.SZ' ? 0 : 1,
        completeness: 'presence_only',
      },
      close: symbol === '399006.SZ' ? null : close,
      change_pct: symbol === '399006.SZ' ? null : '1.25',
    }))
    const series = {
      date: '2026-10-20',
      window_requested: 60,
      window_actual: 1,
      history_dates: ['2026-10-20'],
      indices: instruments.map(([symbol, name, close]) => ({
        symbol,
        name,
        coverage: {
          status: symbol === '399006.SZ' ? 'missing' : 'available',
          row_count: symbol === '399006.SZ' ? 0 : 1,
          completeness: 'presence_only',
        },
        missing_days: symbol === '399006.SZ' ? 1 : 0,
        bars: [
          {
            date: '2026-10-20',
            open: symbol === '399006.SZ' ? null : close,
            high: symbol === '399006.SZ' ? null : close,
            low: symbol === '399006.SZ' ? null : close,
            close: symbol === '399006.SZ' ? null : close,
            change_pct: symbol === '399006.SZ' ? null : '1.25',
            ma5: symbol === '399006.SZ' ? null : close,
            ma20: symbol === '399006.SZ' ? null : close,
            amount_source: null,
            volume_source: null,
          },
        ],
      })),
      issues: [],
      methodology: {},
    } as unknown as ReviewIndices

    const html = await renderToString(
      createSSRApp(MarketIndexPanel, {
        date: '2026-10-20',
        items,
        series,
        loading: false,
        failure: null,
      }),
    )

    expect(html.match(/class="index-card"/g)).toHaveLength(6)
    for (const [, name] of instruments) expect(html).toContain(name)
    expect(html).toContain('暂无趋势数据')
  })

  it('keeps the detail empty state distinct from a zero value', async () => {
    const series = {
      symbol: '399006.SZ',
      name: '创业板指',
      coverage: { status: 'missing', row_count: 0, completeness: 'presence_only' },
      missing_days: 20,
      bars: [
        {
          date: '2026-10-20',
          open: null,
          high: null,
          low: null,
          close: null,
          change_pct: null,
          ma5: null,
          ma20: null,
          amount_source: null,
          volume_source: null,
        },
      ],
    } as unknown as ReviewIndices['indices'][number]

    const html = await renderToString(
      createSSRApp(MarketIndexDetail, {
        series,
        date: '2026-10-20',
      }),
    )

    expect(html).toContain('该窗口没有完整的日 K 数据。')
    expect(html).toContain('缺失日')
    expect(html).toContain('—')
  })
})
