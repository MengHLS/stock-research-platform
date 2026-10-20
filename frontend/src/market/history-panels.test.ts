import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import MarketBreadthPanel from '../components/market/MarketBreadthPanel.vue'
import MarketHighBoardTrend from '../components/market/MarketHighBoardTrend.vue'
import type { ReviewHistoryRow } from './review'

const history: ReviewHistoryRow[] = Array.from({ length: 120 }, (_, index) => ({
  date: `2026-${String(Math.floor(index / 28) + 1).padStart(2, '0')}-${String((index % 28) + 1).padStart(2, '0')}`,
  assessment: 'available',
  max_board: 7,
  total_limit_up: 20,
  turnover_100m_cny: '10000',
  high_board_stocks: Array.from({ length: 16 }, (_, stock) => ({
    symbol: `${String(stock + 1).padStart(6, '0')}.SZ`,
    name: `第${index + 1}日完整股票名称${stock + 1}`,
    boards: stock === 0 ? 7 : 6,
  })),
}))

describe('review history panels', () => {
  it('defaults both charts to all 120 supplied trading days', async () => {
    const breadth = await renderToString(createSSRApp(MarketBreadthPanel, { history }))
    expect(breadth).toContain('近 120 个交易日')
    expect(breadth).toContain('120日')
    const trend = await renderToString(
      createSSRApp(MarketHighBoardTrend, { history, selectedDate: history[119]!.date }),
    )
    expect(trend).toContain('近 120 个交易日')
    expect(trend.match(/class="daily-row"/g)).toHaveLength(120)
    for (const row of history) {
      for (const stock of row.high_board_stocks!) {
        expect(trend).toContain(`${stock.name}（${stock.boards}板）`)
      }
    }
    expect(trend).toContain('逐日六板及以上股票 · 完整名单')
  })

  it('shows the actual short window and distinguishes missing from no qualifying stocks', async () => {
    const short: ReviewHistoryRow[] = [
      { date: '2026-09-17', assessment: 'available', high_board_stocks: [] },
      { date: '2026-09-18', assessment: 'missing', high_board_stocks: [] },
    ]
    for (const panel of [MarketBreadthPanel, MarketHighBoardTrend]) {
      const html = await renderToString(
        createSSRApp(panel, { history: short, selectedDate: '2026-09-18' }),
      )
      expect(html).toContain('近 2 个交易日')
      expect(html).toContain('历史不足120日')
    }
    const html = await renderToString(
      createSSRApp(MarketHighBoardTrend, { history: short, selectedDate: '2026-09-18' }),
    )
    expect(html).toContain('无六板及以上股票')
    expect(html).toContain('暂无已知六板及以上股票')
  })
})
