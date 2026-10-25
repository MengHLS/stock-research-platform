import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, defineComponent, nextTick, type App } from 'vue'

import type { ApiResult } from '../api/errors'
import type { FirstBoardHistory } from './first-board-classifier'
import { useStockFirstBoardEvents } from './useStockFirstBoardEvents'

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
    if (element.parent)
      element.parent.children = element.parent.children.filter((item) => item !== element)
  },
})
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
const success = <T>(data: T) => ({ ok: true as const, data, requestId: null })
const history = (code = 'FBC-07'): FirstBoardHistory => ({
  taxonomy_version: 'first-board-background-v1',
  stock_code: '600519.SH',
  items: [
    {
      event_id: '600519.SH@2026-09-04',
      stock_code: '600519.SH',
      event_date: '2026-09-04',
      class_code: code,
      class_name: '测试分类',
      group_code: 'FBG-04',
      group_name: '测试组',
      source_detail_code: 'G4-N',
      source_group_code: 'G4',
      position_60d_pct: '50',
      position_band: 'mid',
      trend: 'sideways',
      short_path: 'neutral',
      quality_status: 'COMPLETE',
      feature_reason: null,
      source_kind: 'frozen',
      data_version: 'first-board-background-v1',
    },
  ],
  total: 1,
  limit: 100,
  source: {
    frozen_status: 'PASS',
    frozen_dataset_version_id: 660001,
    frozen_event_count: 73003,
    stored_batch_count: 0,
    stored_event_count: 0,
  },
  uses_forward_data: false,
})
async function settle() {
  for (let index = 0; index < 6; index += 1) {
    await Promise.resolve()
    await nextTick()
  }
}

let state: ReturnType<typeof useStockFirstBoardEvents>
const Harness = defineComponent({
  setup() {
    state = useStockFirstBoardEvents((symbol, signal) => load(symbol, signal))
    return () => null
  },
})
const load = vi.fn<(symbol: string, signal: AbortSignal) => Promise<ApiResult<FirstBoardHistory>>>()
let app: App
let host: TestNode

beforeEach(() => {
  load.mockReset()
  host = node('root')
})
afterEach(() => app?.unmount())

describe('stock first-board history state', () => {
  it('loads the selected stock and exposes the verified event list', async () => {
    load.mockResolvedValue(success(history()))
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    await state.load('600519.SH')
    await settle()
    expect(load).toHaveBeenCalledWith('600519.SH', expect.any(AbortSignal))
    expect(state.events.value?.items[0].class_code).toBe('FBC-07')
    expect(state.loading.value).toBe(false)
  })

  it('cancels the previous stock and ignores its late response', async () => {
    const firstRequest = deferred<ApiResult<FirstBoardHistory>>()
    const secondRequest = deferred<ApiResult<FirstBoardHistory>>()
    let firstSignal: AbortSignal | undefined
    let callCount = 0
    load.mockImplementation((_symbol, requestSignal) => {
      callCount += 1
      if (callCount === 1) firstSignal = requestSignal
      return callCount === 1 ? firstRequest.promise : secondRequest.promise
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    const first = state.load('600519.SH')
    await settle()
    expect(firstSignal?.aborted).toBe(false)
    const second = state.load('000001.SZ')
    await settle()
    expect(firstSignal?.aborted).toBe(true)
    firstRequest.resolve(success(history('STALE')))
    secondRequest.resolve(success(history('FBC-08')))
    await Promise.all([first, second])
    await settle()
    expect(state.events.value?.items[0].class_code).toBe('FBC-08')
  })

  it('keeps a source failure separate from an empty history and retries the same stock', async () => {
    load.mockResolvedValue({
      ok: false,
      failure: {
        kind: 'business',
        code: 'SOURCE_NOT_CONFIGURED',
        message: 'source unavailable',
        requestId: 'event-42',
        status: 503,
        retryable: true,
        fields: [],
      },
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    await state.load('600519.SH')
    await settle()
    expect(state.failure.value?.requestId).toBe('event-42')
    expect(state.events.value).toBeNull()
    state.retry()
    await settle()
    expect(load).toHaveBeenLastCalledWith('600519.SH', expect.any(AbortSignal))
  })

  it('clears data and aborts on drawer close', async () => {
    const pending = deferred<ApiResult<FirstBoardHistory>>()
    let signal: AbortSignal | undefined
    load.mockImplementation((_symbol, requestSignal) => {
      signal = requestSignal
      return pending.promise
    })
    app = renderer.createApp(Harness)
    app.mount(host)
    await settle()
    const request = state.load('600519.SH')
    await settle()
    state.clear()
    expect(signal?.aborted).toBe(true)
    pending.resolve(success(history()))
    await request
    await settle()
    expect(state.events.value).toBeNull()
    expect(state.failure.value).toBeNull()
  })
})
