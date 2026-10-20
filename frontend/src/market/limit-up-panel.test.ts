import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { compile, createRenderer, nextTick, ssrContextKey, type SetupContext } from 'vue'
import { parse } from 'vue/compiler-sfc'

import LimitUpReviewPanel from '../components/market/LimitUpReviewPanel.vue'
import type { LimitUpReviewRow } from './review'

// Vitest's Node transform supplies ssrRender. Compile the real client template for event tests.
const template = parse(
  readFileSync(new URL('../components/market/LimitUpReviewPanel.vue', import.meta.url), 'utf8'),
).descriptor.template!.content
const component = {
  ...LimitUpReviewPanel,
  setup(props: unknown, context: SetupContext) {
    const setup = (
      LimitUpReviewPanel as unknown as {
        setup: (props: unknown, context: SetupContext) => object
      }
    ).setup
    return { ...setup(props, context) }
  },
  render: compile(template, { isCustomElement: (tag) => tag === 'AppIcon' }),
}

// Render the real component and exercise its bound events without adding a DOM dependency.
class Node {
  children: Node[] = []
  props: Record<string, unknown> = {}
  parent: Node | null = null
  text = ''
  focus = vi.fn()
  addEventListener = vi.fn()
  constructor(public tag: string) {}
  closest(selector: string): Node | null {
    if (selector.split(', ').includes(this.tag)) return this
    return this.parent?.closest(selector) ?? null
  }
}

const renderer = createRenderer<Node, Node>({
  createElement: (tag) => new Node(tag),
  createText: (text) => Object.assign(new Node('#text'), { text }),
  createComment: () => new Node('#comment'),
  setText: (node, text) => {
    node.text = text
  },
  setElementText: (node, text) => {
    node.text = text
  },
  patchProp: (node, key, _previous, value) => {
    node.props[key] = value
  },
  insert(node, parent, anchor) {
    node.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(node)
    else parent.children.splice(index, 0, node)
  },
  remove(node) {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  },
  parentNode: (node) => node.parent,
  nextSibling: () => null,
})

function find(root: Node, predicate: (node: Node) => boolean): Node[] {
  return [
    ...(predicate(root) ? [root] : []),
    ...root.children.flatMap((node) => find(node, predicate)),
  ]
}

const up: LimitUpReviewRow = {
  date: '2026-09-18',
  symbol: '000001.SZ',
  name: '甲',
  sector: '半导体',
  status: 'limit_up',
  boards: 2,
  boards_as_of_date: '2026-09-18',
  limit_up_time: '09:35:00',
  limit_up_time_as_of_date: '2026-09-18',
  broken_kind: null,
  change_pct: '10.00',
  one_word_board: false,
}
const broken: LimitUpReviewRow = {
  ...up,
  symbol: '000002.SZ',
  name: '乙',
  status: 'broken',
  boards_as_of_date: '2026-09-17',
  broken_kind: 'connection',
}
const unmounts: (() => void)[] = []
afterEach(() => unmounts.splice(0).forEach((unmount) => unmount()))

function mount() {
  const root = new Node('root')
  const select = vi.fn()
  const app = renderer.createApp(component, {
    rows: [up, broken, { ...up, date: '2026-09-17' }],
    selectedDate: up.date,
    selectedDay: null,
    loading: false,
    failure: null,
    onSelect: select,
  })
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)
  unmounts.push(() => app.unmount())
  return { root, select, rows: () => find(root, (node) => node.props.class === 'detail-row') }
}

function dispatch(node: Node, type: 'Click' | 'Keydown', extra = {}) {
  const event = {
    target: node,
    currentTarget: node,
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
    ...extra,
  }
  let current: Node | null = node
  while (current) {
    event.currentTarget = current
    const handler = current.props[`on${type}`] as ((event: unknown) => void) | undefined
    handler?.(event)
    if (event.stopPropagation.mock.calls.length) break
    current = current.parent
  }
  return event
}

describe('limit-up review row details', () => {
  it('opens the selected stock and date from ordinary cells for both statuses', async () => {
    const panel = mount()
    expect(panel.rows()).toHaveLength(1)
    dispatch(panel.rows()[0].children[2], 'Click')
    expect(panel.select).toHaveBeenLastCalledWith(up)
    expect(panel.rows()[0].focus).toHaveBeenCalledWith({ preventScroll: true })

    dispatch(
      find(panel.root, (node) => node.tag === 'button' && node.text.trim() === '断板')[0],
      'Click',
    )
    await nextTick()
    expect(panel.rows()).toHaveLength(1)
    dispatch(panel.rows()[0].children[0], 'Click')
    expect(panel.select).toHaveBeenLastCalledWith(broken)
    expect(panel.select).toHaveBeenCalledTimes(2)
  })

  it('supports Enter and Space with an accessible name and ignores repeated or unrelated keys', () => {
    const panel = mount()
    const row = panel.rows()[0]
    expect(row.props.tabindex).toBe('0')
    expect(row.props['aria-label']).toContain(`${up.name} ${up.symbol} ${up.date}`)
    expect(row.props['aria-haspopup']).toBe('dialog')
    for (const key of ['Enter', ' ']) {
      expect(dispatch(row, 'Keydown', { key }).preventDefault).toHaveBeenCalledOnce()
    }
    dispatch(row, 'Keydown', { key: 'Enter', repeat: true })
    expect(dispatch(row, 'Keydown', { key: 'ArrowDown' }).preventDefault).not.toHaveBeenCalled()
    expect(panel.select).toHaveBeenCalledTimes(2)
  })

  it('opens once from the detail button and leaves independent inputs and nested controls alone', () => {
    const panel = mount()
    const row = panel.rows()[0]
    const detail = find(row, (node) => node.tag === 'button')[0]
    dispatch(detail, 'Keydown', { key: 'Enter' })
    dispatch(detail, 'Click')
    expect(panel.select).toHaveBeenCalledTimes(1)
    panel.select.mockClear()

    for (const tag of ['button', 'a', 'input', 'textarea', 'select', 'label']) {
      const control = new Node(tag)
      const nested = new Node('span')
      control.parent = row.children[7]
      nested.parent = control
      dispatch(nested, 'Click')
      expect(dispatch(control, 'Keydown', { key: ' ' }).preventDefault).not.toHaveBeenCalled()
    }
    expect(panel.select).not.toHaveBeenCalled()
  })
})
