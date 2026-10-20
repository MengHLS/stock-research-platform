import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import IntradayChart from '../components/market/IntradayChart.vue'
import type { IntradayBar } from './intraday'

const bars: IntradayBar[] = [
  {
    start: '2026-10-20T01:31:00Z',
    trading_day: '2026-10-20',
    open: '100',
    high: '101',
    low: '99.5',
    close: '100.5',
    volume_shares: '1000',
  },
  {
    start: '2026-10-20T01:32:00Z',
    trading_day: '2026-10-20',
    open: '100.5',
    high: '102',
    low: '100.2',
    close: '101.5',
    volume_shares: '1200',
  },
]

describe('intraday chart without previous close', () => {
  it('draws a price path from the bar interval and labels the missing reference', async () => {
    const html = await renderToString(createSSRApp(IntradayChart, { bars }))
    const pathTag = html.match(/<path[^>]*price-line[^>]*>/)?.[0] ?? ''
    const path = pathTag.match(/d="([^"]+)"/)?.[1] ?? ''

    expect(path).toMatch(/^M[\d.\s]+L[\d.\s]+/)
    expect(html).toContain('纵轴按价格区间展示；涨跌幅不可用')
    expect(html).not.toContain('无法绘制价格轴')
    expect(html).not.toContain('axis-pct')
    expect(html).not.toContain('previous-line')
  })
})
