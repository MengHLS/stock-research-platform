import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import LimitUpDetail from '../components/market/LimitUpDetail.vue'
import type { LimitUpReviewRow } from './review'

const row: LimitUpReviewRow = {
  date: '2026-10-20',
  symbol: '600519.SH',
  name: '贵州茅台',
  sector: '白酒',
  status: 'limit_up',
  boards: 1,
  boards_as_of_date: '2026-10-20',
  limit_up_time: '09:35:00',
  limit_up_time_as_of_date: '2026-10-20',
  broken_kind: null,
  change_pct: '10.00',
  one_word_board: false,
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    row,
    sameSector: [],
    note: '',
    stockSeries: null,
    stockLoading: false,
    stockFailure: null,
    stockRequestId: null,
    industry: '白酒Ⅱ',
    industryProvider: 'eastmoney',
    industryLoading: false,
    industryFailure: null,
    industryRequestId: null,
    intradayBars: [],
    intradayTradingDay: null,
    intradayLoading: false,
    intradayFailure: null,
    intradayRequestId: null,
    ...overrides,
  }
}

describe('limit-up stock detail industry', () => {
  it('shows a provider industry separately from the limit-up theme', async () => {
    const html = await renderToString(createSSRApp(LimitUpDetail, props()))

    expect(html).toContain('>行业</dt>')
    expect(html).toContain('白酒Ⅱ')
    expect(html).toContain('>题材</dt>')
  })

  it('does not substitute the theme when industry is explicitly unavailable', async () => {
    const html = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({
          industry: null,
          industryProvider: null,
          industryFailure: '行业来源暂不可用',
          industryRequestId: 'req-industry',
        }),
      ),
    )

    expect(html).toContain('未获取')
    expect(html).toContain('行业来源暂不可用')
    expect(html).toContain('请求编号 req-industry')
    expect(html).toContain('重试行业')
  })

  it('offers daily and latest-intraday chart modes in the same area', async () => {
    const html = await renderToString(createSSRApp(LimitUpDetail, props()))

    expect(html).toContain('个股走势')
    expect(html).toContain('日 K')
    expect(html).toContain('最近分时')
  })
})
