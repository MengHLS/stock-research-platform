import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import LimitUpDetail from '../components/market/LimitUpDetail.vue'
import type { FirstBoardHistory } from './first-board-classifier'
import type { LimitUpReviewRow } from './review'
import type { ReviewStockFacts } from './stock-facts'

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
const firstBoardEvents: FirstBoardHistory = {
  taxonomy_version: 'first-board-background-v1',
  stock_code: row.symbol,
  items: [
    {
      event_id: `${row.symbol}@2026-09-04`,
      stock_code: row.symbol,
      event_date: '2026-09-04',
      class_code: 'FBC-07',
      class_name: '整体方向未明确·短期中性背景首板',
      group_code: 'FBG-04',
      group_name: '整体方向未明确·短期路径分化背景',
      source_detail_code: 'G4-N',
      source_group_code: 'G4',
      position_60d_pct: '52.35',
      position_band: 'mid',
      trend: 'sideways',
      short_path: 'neutral',
      quality_status: 'COMPLETE',
      feature_reason: null,
      source_kind: 'frozen',
      data_version: 'first-board-background-v1',
    },
    {
      event_id: `${row.symbol}@2026-10-20`,
      stock_code: row.symbol,
      event_date: row.date,
      class_code: 'FBC-12',
      class_name: '高位上升趋势短期延续背景首板',
      group_code: 'FBG-05',
      group_name: '上升趋势·短期延续背景',
      source_detail_code: 'G5-H',
      source_group_code: 'G5',
      position_60d_pct: '82.10',
      position_band: 'high',
      trend: 'up',
      short_path: 'up_continuation',
      quality_status: 'COMPLETE',
      feature_reason: null,
      source_kind: 'stored',
      data_version: 'stored-daily-first-board-v1',
    },
  ],
  total: 2,
  limit: 100,
  source: {
    frozen_status: 'PASS',
    frozen_dataset_version_id: 660001,
    frozen_event_count: 73003,
    stored_batch_count: 1,
    stored_event_count: 1,
  },
  uses_forward_data: false,
}

const facts: ReviewStockFacts = {
  symbol: '600519.SH',
  date: '2026-10-20',
  industry: {
    code: 'C39',
    name: '计算机、通信和其他电子设备制造业',
    source: 'baostock',
    effective_from: '2026-08-31',
    effective_to: null,
  },
  valuation: {
    date: '2026-10-20',
    turnover_pct: '4.12',
    total_market_cap_cny: '120000000000.00',
    circulation_market_cap_cny: '95000000000.00',
    source: 'baostock-daily',
    unknown_fields: [],
  },
  trade: {
    date: '2026-10-20',
    volume_shares: '52345678.00',
    amount_cny: '612000500.00',
    source: 'tushare',
    unknown_fields: [],
  },
  issues: [],
  methodology: {},
} as unknown as ReviewStockFacts

const missingFacts: ReviewStockFacts = {
  symbol: '600519.SH',
  date: '2026-10-23',
  industry: null,
  valuation: {
    date: '2026-10-23',
    turnover_pct: null,
    total_market_cap_cny: null,
    circulation_market_cap_cny: null,
    source: null,
    unknown_fields: ['turnover_pct', 'total_market_cap_cny', 'circulation_market_cap_cny'],
  },
  trade: {
    date: '2026-10-23',
    volume_shares: null,
    amount_cny: null,
    source: null,
    unknown_fields: ['volume_shares', 'amount_cny'],
  },
  issues: [
    {
      code: 'stock_industry_missing',
      scope: '2026-10-23',
      message: '旧库没有该股票在观察日生效的行业归属，行业保持未知。',
    },
    {
      code: 'stock_liquidity_missing',
      scope: '2026-10-23',
      message: '旧库流动性日线在该交易日没有该股票记录，换手率与市值保持未知。',
    },
    {
      code: 'stock_trade_missing',
      scope: '2026-10-23',
      message: '旧库个股日线在该交易日缺少成交量或成交额，保持未知。',
    },
  ],
  methodology: {},
} as unknown as ReviewStockFacts

function props(overrides: Record<string, unknown> = {}) {
  return {
    row,
    note: '',
    stockSeries: null,
    stockLoading: false,
    stockFailure: null,
    stockRequestId: null,
    facts,
    factsLoading: false,
    factsFailure: null,
    factsRequestId: null,
    intradayBars: [],
    intradayTradingDay: null,
    intradayLoading: false,
    intradayFailure: null,
    intradayRequestId: null,
    firstBoardEvents,
    firstBoardLoading: false,
    firstBoardFailure: null,
    firstBoardRequestId: null,
    ...overrides,
  }
}

describe('limit-up stock detail database facts', () => {
  it('shows the database industry separately from the limit-up theme', async () => {
    const html = await renderToString(createSSRApp(LimitUpDetail, props()))

    expect(html).toContain('>行业</dt>')
    expect(html).toContain('计算机、通信和其他电子设备制造业')
    expect(html).toContain('>题材</dt>')
    expect(html).not.toContain('东方财富')
  })

  it('shows market cap, turnover and traded volume with their units', async () => {
    const html = await renderToString(createSSRApp(LimitUpDetail, props()))

    expect(html).toContain('>公司市值</dt>')
    expect(html).toContain('1200.00 亿')
    expect(html).toContain('流通 950.00 亿')
    expect(html).toContain('>换手率</dt>')
    expect(html).toContain('4.12%')
    expect(html).toContain('>成交量</dt>')
    expect(html).toContain('52.35 万手')
    expect(html).toContain('成交额 6.12 亿')
  })

  it('keeps unavailable values unknown and explains the database gap', async () => {
    const html = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({ row: { ...row, date: '2026-10-23' }, facts: missingFacts }),
      ),
    )

    expect(html).toContain('未知')
    expect(html).toContain('旧库没有该股票在观察日生效的行业归属')
    expect(html).toContain('换手率与市值保持未知')
    expect(html).not.toContain('0.00 亿')
  })

  it('offers a retry that is scoped to the database facts request', async () => {
    const html = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({
          facts: null,
          factsFailure: '复盘数据库暂不可用',
          factsRequestId: 'req-facts',
        }),
      ),
    )

    expect(html).toContain('复盘数据库暂不可用')
    expect(html).toContain('请求编号 req-facts')
    expect(html).toContain('重试行业与量价')
  })

  it('offers daily and latest-intraday chart modes in the same area', async () => {
    const html = await renderToString(createSSRApp(LimitUpDetail, props()))

    expect(html).toContain('个股走势')
    expect(html).toContain('日 K')
    expect(html).toContain('最近分时')
  })

  it('offers a retry in the empty daily and intraday states', async () => {
    const daily = await renderToString(createSSRApp(LimitUpDetail, props()))
    const intraday = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({
          initialChartMode: 'intraday',
          intradayTradingDay: '2026-10-20',
        }),
      ),
    )

    expect(daily).toContain('重新读取日 K')
    expect(intraday).toContain('最近分时 · 2026-10-20')
    expect(intraday).toContain('重新读取分时')
  })

  it('replaces same-day peers with the stock first-board event history', async () => {
    const html = await renderToString(createSSRApp(LimitUpDetail, props()))

    expect(html).toContain('历史首板事件分类')
    expect(html).toContain('FBC-12')
    expect(html).toContain('高位上升趋势短期延续背景首板')
    expect(html).toContain('短期向上延续')
    expect(html).toContain('首板涨停')
    expect(html).toContain('当前复盘日')
    expect(html).toContain('status--up')
    expect(html).not.toContain('同日同题材')
  })

  it('keeps event loading, empty and failure states distinct', async () => {
    const loading = await renderToString(
      createSSRApp(LimitUpDetail, props({ firstBoardEvents: null, firstBoardLoading: true })),
    )
    const empty = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({ firstBoardEvents: { ...firstBoardEvents, items: [], total: 0 } }),
      ),
    )
    const failure = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({
          firstBoardEvents: null,
          firstBoardFailure: '首板冻结事件数据暂不可用',
          firstBoardRequestId: 'event-request-9',
        }),
      ),
    )

    expect(loading).toContain('正在读取')
    expect(empty).toContain('没有历史事件')
    expect(failure).toContain('历史首板分类读取失败')
    expect(failure).toContain('event-request-9')
    expect(failure).toContain('重试事件分析')
  })

  it('does not claim a verified empty history when the frozen source is unavailable', async () => {
    const unconfigured = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({
          firstBoardEvents: {
            ...firstBoardEvents,
            items: [],
            total: 0,
            source: { ...firstBoardEvents.source, frozen_status: 'NOT_CONFIGURED' },
          },
        }),
      ),
    )
    const degraded = await renderToString(
      createSSRApp(
        LimitUpDetail,
        props({
          firstBoardEvents: {
            ...firstBoardEvents,
            source: { ...firstBoardEvents.source, frozen_status: 'BAD_DATA' },
          },
        }),
      ),
    )

    expect(unconfigured).toContain('冻结历史未配置')
    expect(unconfigured).not.toContain('已验证首板账本和当前入库快照中没有历史事件')
    expect(degraded).toContain('冻结历史当前不可用')
    expect(degraded).toContain('重试事件分析')
  })
})
