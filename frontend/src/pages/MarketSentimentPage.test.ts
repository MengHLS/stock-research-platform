import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, defineComponent, nextTick, reactive, type App } from 'vue'

import type { LimitUpReviewRow, ReviewOverview } from '../market/review'
import { useMarketSentimentPage } from '../market/useMarketSentimentPage'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
let route: { path: string; query: Record<string, string> }
const router = {
  push: vi.fn((value: { query: Record<string, string> }) => {
    route.query = value.query
    return Promise.resolve()
  }),
  replace: vi.fn((value: { query: Record<string, string> }) => {
    route.query = value.query
    return Promise.resolve()
  }),
}
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => router }))
vi.mock('../api/client', () => ({
  api: { GET: get },
  callApi: (invoke: (signal: AbortSignal) => unknown, options: { signal: AbortSignal }) =>
    invoke(options.signal),
}))

interface TestNode {
  tag: string
  props: Record<string, unknown>
  children: TestNode[]
  parent: TestNode | null
}
function node(tag: string): TestNode {
  return { tag, props: {}, children: [], parent: null }
}
const renderer = createRenderer<TestNode, TestNode>({
  createElement: node,
  createText: () => node('text'),
  createComment: () => node('comment'),
  setText: () => {},
  setElementText: () => {},
  parentNode: (element) => element.parent,
  nextSibling: () => null,
  patchProp: (element, key, _previous, value) => {
    element.props[key] = value
  },
  insert: (element, parent) => {
    element.parent = parent
    parent.children.push(element)
  },
  remove: (element) => {
    if (element.parent) {
      element.parent.children = element.parent.children.filter((item) => item !== element)
    }
  },
})
function deferred() {
  let resolve!: (value: unknown) => void
  const promise = new Promise<unknown>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
const success = (data: unknown) => ({ ok: true, data, requestId: null })
const overview = (date: string) =>
  ({
    date,
    history: [],
    ladder: { connection: [], first: [], broken: [], unknown: [] },
    issues: [],
    window_requested: 40,
    window_actual: 40,
  }) as unknown as ReviewOverview
interface RequestOptions {
  params: { query: { date?: string; window?: number } }
  signal: AbortSignal
}
const context = (requested?: string) => ({
  default_date: '2026-10-16',
  requested_date: requested,
  requested_date_known: requested ? true : null,
  window_max: 120,
})
async function settle() {
  for (let index = 0; index < 12; index += 1) {
    await Promise.resolve()
    await nextTick()
  }
}

let state: ReturnType<typeof useMarketSentimentPage>
const Harness = defineComponent({
  setup() {
    state = useMarketSentimentPage()
    return () => null
  },
})
let app: App
let host: TestNode
beforeEach(() => {
  vi.clearAllMocks()
  route = reactive({ path: '/market/sentiment', query: { date: '2026-10-16' } })
  host = node('root')
})
afterEach(() => app?.unmount())

describe('sentiment page request ownership and details', () => {
  it('keeps the replacement date when an aborted overview returns late', async () => {
    const old = deferred()
    let oldSignal: AbortSignal | undefined
    get.mockImplementation((path: string, options: RequestOptions) => {
      const query = options.params.query
      if (path.endsWith('/context')) return Promise.resolve(success(context(query.date)))
      if (query.date === '2026-10-16') {
        oldSignal = options.signal
        return old.promise
      }
      return Promise.resolve(success(overview(query.date!)))
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    route.query = { date: '2026-10-15', window: '60' }
    await settle()
    expect(oldSignal?.aborted).toBe(true)
    expect(state.overview.value?.date).toBe('2026-10-15')
    expect(state.selectedWindow.value).toBe(60)
    expect(get).toHaveBeenCalledWith(
      '/api/v1/market/review/overview',
      expect.objectContaining({
        params: { query: { date: '2026-10-15', window: 60 } },
      }),
    )
    old.resolve(success(overview('2026-10-16')))
    await settle()
    expect(state.overview.value?.date).toBe('2026-10-15')
  })

  it('uses the selected peer for drawer identity and cancels lookup when closed', async () => {
    const a = {
      symbol: '600001',
      name: '股票A',
      sector: '算力',
      date: '2026-10-16',
      boards: 3,
      limit_up_time: '09:31',
      boards_as_of_date: '2026-10-16',
      status: 'limit_up',
    } as LimitUpReviewRow
    const b = { ...a, symbol: '600002', name: '股票B' }
    const late = deferred()
    let lookupSignal: AbortSignal | undefined
    let lookup = 0
    get.mockImplementation((path: string, options: RequestOptions) => {
      if (path.endsWith('/context'))
        return Promise.resolve(success(context(options.params.query.date)))
      if (path.endsWith('/overview')) return Promise.resolve(success(overview('2026-10-16')))
      lookup += 1
      lookupSignal = options.signal
      return lookup === 1 ? Promise.resolve(success({ rows: [a, b] })) : late.promise
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    const select = state.openLeader
    await select(a)
    await settle()
    const selectPeer = state.selectStockFromDetail
    await selectPeer(b)
    await settle()
    expect(state.drawerTitle.value).toBe('股票B')
    expect(state.drawerMeta.value).toContain('600002')
    expect(state.selectedRow.value).toEqual(b)
    const pending = select(a)
    await settle()
    const close = state.closeDrawer
    close()
    expect(lookupSignal?.aborted).toBe(true)
    late.resolve(success({ rows: [a, b] }))
    await pending
    await settle()
    expect(state.drawerOpen.value).toBe(false)
  })

  it('redirects a missing date to the source default and queries that date', async () => {
    route.query = {}
    get.mockImplementation((path: string, options: RequestOptions) =>
      Promise.resolve(
        success(
          path.endsWith('/context')
            ? context(options.params.query.date)
            : overview(options.params.query.date!),
        ),
      ),
    )
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    expect(router.replace).toHaveBeenCalledWith({
      path: '/market/sentiment',
      query: { date: '2026-10-16', window: '40' },
    })
    expect(state.overview.value?.date).toBe('2026-10-16')
  })
})
