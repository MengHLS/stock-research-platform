import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent } from 'vue'
import { renderToString } from 'vue/server-renderer'

import StockDetailContent from '../components/market/StockDetailContent.vue'

const { get } = vi.hoisted(() => ({ get: vi.fn(() => new Promise(() => {})) }))
vi.mock('../api/client', () => ({
  api: { GET: get },
  callApi: (invoke: (signal: AbortSignal) => unknown, options: { signal: AbortSignal }) =>
    invoke(options.signal),
}))
vi.mock('../components/market/LimitUpDetail.vue', () => ({
  default: defineComponent({ render: () => null }),
}))

describe('stock detail daily request window', () => {
  it.each([
    [undefined, 120],
    [240, 120],
    [80, 80],
  ])('uses windowMax %s to request %s trading days', async (windowMax, expected) => {
    get.mockClear()
    const app = createSSRApp(StockDetailContent, {
      row: { symbol: '002889.SZ', date: '2026-10-19', status: 'limit_up' },
      note: '',
      windowMax,
    })
    await renderToString(app)
    expect(get).toHaveBeenCalledWith(
      '/api/v1/market/review/stock-series',
      expect.objectContaining({
        params: { query: { symbol: '002889.SZ', date: '2026-10-19', window: expected } },
      }),
    )
  })
})
