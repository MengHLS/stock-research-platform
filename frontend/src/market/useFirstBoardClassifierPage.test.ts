import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, defineComponent, nextTick, type App } from 'vue'

import { useFirstBoardClassifierPage } from './useFirstBoardClassifierPage'
import { useFirstBoardDaily } from './useFirstBoardDaily'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({
  api: { GET: get, POST: post },
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
const catalog = {
  classes: [],
  groups: [],
  notes: [],
  low_position_max_pct: '35',
  high_position_min_pct: '75',
  taxonomy_version: 'first-board-background-v1',
}
async function settle() {
  for (let index = 0; index < 8; index += 1) {
    await Promise.resolve()
    await nextTick()
  }
}

let state: ReturnType<typeof useFirstBoardClassifierPage>
const Harness = defineComponent({
  setup() {
    state = useFirstBoardClassifierPage()
    return () => null
  },
})
let app: App
let host: TestNode
beforeEach(() => {
  vi.clearAllMocks()
  host = node('root')
  get.mockResolvedValue(success(catalog))
})
afterEach(() => app?.unmount())

describe('first-board classifier page state', () => {
  it('submits a numeric position input without throwing or hanging', async () => {
    post.mockResolvedValue(
      success({
        class_code: 'FBC-01',
        class_name: '高位上升趋势·短期回调背景首板',
      }),
    )
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    state.position.value = 80
    await settle()
    await state.classify()
    await settle()
    expect(post).toHaveBeenCalledWith(
      '/api/v1/research/first-board-classifier/classify',
      expect.objectContaining({
        body: expect.objectContaining({ position_60d_pct: '80' }),
      }),
    )
    expect(state.result.value?.class_code).toBe('FBC-01')
    expect(state.classifying.value).toBe(false)
  })

  it('cancels an obsolete classification when an axis changes', async () => {
    const pending = deferred()
    let signal: AbortSignal | undefined
    post.mockImplementation((_path, options) => {
      signal = options.signal
      return pending.promise
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    const classify = state.classify
    const request = classify()
    await settle()
    state.trend.value = 'down'
    await settle()
    expect(signal?.aborted).toBe(true)
    pending.resolve(success({ class_code: 'FBC-01', class_name: '过期分类结果' }))
    await request
    await settle()
    expect(state.result.value).toBeNull()
    expect(state.classifyFailure.value).toBeNull()
  })

  it('keeps source failure and request id separate from an empty event result', async () => {
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/events')
          ? {
              ok: false,
              failure: {
                kind: 'business',
                code: 'SOURCE_NOT_CONFIGURED',
                message: 'source unavailable',
                requestId: 'source-request-42',
              },
            }
          : success(catalog),
      ),
    )
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    state.stockCode.value = '603121'
    await settle()
    await state.loadEvents()
    await settle()
    expect(state.events.value).toBeNull()
    expect(state.failureText(state.eventsFailure.value!)).toContain('冻结首板账本尚未配置')
    expect(state.eventsFailure.value?.requestId).toBe('source-request-42')
  })

  it('clears stale events when the stock filter changes', async () => {
    const pending = deferred()
    let signal: AbortSignal | undefined
    get.mockImplementation((path: string, options) => {
      if (path.endsWith('/events')) {
        signal = options.signal
        return pending.promise
      }
      return Promise.resolve(success(catalog))
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    state.stockCode.value = '603121'
    await settle()
    const request = state.loadEvents()
    await settle()
    expect(signal?.aborted).toBe(false)
    state.stockCode.value = '603122'
    await settle()
    expect(signal?.aborted).toBe(true)
    pending.resolve(success({ items: [{ event_id: 'stale' }], total: 1 }))
    await request
    await settle()
    expect(state.events.value).toBeNull()
  })

  it('ignores a late failure from the replaced stock filter', async () => {
    const pending = deferred()
    let signal: AbortSignal | undefined
    get.mockImplementation((path: string, options) => {
      if (path.endsWith('/events')) {
        signal = options.signal
        return pending.promise
      }
      return Promise.resolve(success(catalog))
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    state.stockCode.value = '603121'
    await settle()
    const request = state.loadEvents()
    await settle()
    expect(signal?.aborted).toBe(false)
    state.stockCode.value = '603122'
    await settle()
    pending.resolve({
      ok: false,
      failure: {
        kind: 'business',
        code: 'FIRST_BOARD_DATASET_BAD_DATA',
        message: 'stale failure',
        requestId: 'stale-request',
      },
    })
    await request
    await settle()
    expect(state.eventsFailure.value).toBeNull()
  })
})

describe('stored daily first-board results', () => {
  let daily: ReturnType<typeof useFirstBoardDaily>
  const DailyHarness = {
    setup() {
      daily = useFirstBoardDaily()
      return () => null
    },
  }

  it('reads stored results on mount and pins pagination to the displayed batch', async () => {
    const snapshot = {
      trading_day: '2026-10-23',
      batch_id: 'a'.repeat(64),
      status: 'PARTIAL',
      total: 155,
      items: [],
    }
    get.mockResolvedValue(success(snapshot))
    app = renderer.createApp(DailyHarness)
    app.mount(host)
    await settle()
    expect(daily.data.value?.status).toBe('PARTIAL')
    await daily.load(100)
    expect(get).toHaveBeenLastCalledWith(
      '/api/v1/research/first-board-classifier/daily',
      expect.objectContaining({
        params: {
          query: {
            date: '2026-10-23',
            batch_id: 'a'.repeat(64),
            offset: 100,
            limit: 100,
          },
        },
      }),
    )
    await daily.load(0, true)
    expect(get).toHaveBeenLastCalledWith(
      '/api/v1/research/first-board-classifier/daily',
      expect.objectContaining({
        params: {
          query: { date: '2026-10-23', batch_id: 'a'.repeat(64), offset: 0, limit: 100 },
        },
      }),
    )
  })

  it('clears a changed date and ignores the old response', async () => {
    const pending = deferred()
    let signal: AbortSignal | undefined
    get.mockImplementation((_path, options) => {
      signal = options.signal
      return pending.promise
    })
    app = renderer.createApp(DailyHarness)
    app.mount(host)
    await settle()
    daily.date.value = '2026-10-22'
    await settle()
    expect(signal?.aborted).toBe(true)
    pending.resolve(success({ status: 'COMPLETE', trading_day: '2026-10-23' }))
    await settle()
    expect(daily.data.value).toBeNull()
    expect(daily.loading.value).toBe(false)
  })

  it('keeps a database failure with request id distinct from not refreshed', async () => {
    get.mockResolvedValue({
      ok: false,
      failure: {
        kind: 'business',
        code: 'FIRST_BOARD_STORAGE_UNAVAILABLE',
        message: '分类数据库暂不可用',
        requestId: 'daily-42',
      },
    })
    app = renderer.createApp(DailyHarness)
    app.mount(host)
    await settle()
    expect(daily.failure.value?.requestId).toBe('daily-42')
    expect(daily.data.value).toBeNull()
    get.mockResolvedValue(success({ status: 'NOT_REFRESHED', total: 0, items: [] }))
    await daily.load()
    expect(daily.failure.value).toBeNull()
    expect(daily.data.value?.status).toBe('NOT_REFRESHED')
  })
})
