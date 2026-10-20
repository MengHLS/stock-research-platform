import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createRenderer,
  defineComponent,
  nextTick,
  reactive,
  ssrContextKey,
  type SetupContext,
} from 'vue'

import ReviewDrawer from '../components/market/ReviewDrawer.vue'
import { lockBackground } from './scroll-lock'

class Style {
  private values = new Map<string, [string, string]>()

  getPropertyValue(name: string) {
    return this.values.get(name)?.[0] ?? ''
  }

  getPropertyPriority(name: string) {
    return this.values.get(name)?.[1] ?? ''
  }

  setProperty(name: string, value: string, priority = '') {
    this.values.set(name, [value, priority])
  }

  removeProperty(name: string) {
    this.values.delete(name)
  }

  get overflow() {
    return this.getPropertyValue('overflow-y') || this.getPropertyValue('overflow')
  }

  set overflow(value: string) {
    this.setProperty('overflow', value)
  }
}

class Element {
  style = new Style()
  attributes = new Map<string, string>()
  isConnected = true
  focus = vi.fn()
  getAttribute = (name: string) => this.attributes.get(name) ?? null
  setAttribute = (name: string, value: string) => this.attributes.set(name, value)
  removeAttribute = (name: string) => this.attributes.delete(name)
}

// Exercise the real setup/watch/unmount lifecycle without a DOM package or browser.
// Geometry below models classic scrollbars; real layout remains a browser acceptance check.
const renderer = createRenderer<object, object>({
  patchProp: () => {},
  insert: () => {},
  remove: () => {},
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  setText: () => {},
  setElementText: () => {},
  parentNode: () => null,
  nextSibling: () => null,
})

const unmounts: (() => void)[] = []

afterEach(async () => {
  unmounts
    .splice(0)
    .reverse()
    .forEach((unmount) => unmount())
  await nextTick()
  vi.unstubAllGlobals()
})

function page(scrollbarWidth: number) {
  const root = new Element()
  const body = new Element()
  const app = new Element()
  const trigger = new Element()
  let activeElement: Element = trigger
  const viewport = {
    innerWidth: 1280,
    scrollX: 0,
    scrollY: 420,
    scrollTo: vi.fn(),
    scrollBy: vi.fn(),
    getComputedStyle: (element: Element) => ({
      scrollbarGutter: element.style.getPropertyValue('scrollbar-gutter') || 'auto',
    }),
  }
  Object.defineProperty(root, 'clientWidth', {
    get: () => {
      const hidden = root.style.overflow === 'hidden' || body.style.overflow === 'hidden'
      const reserved = root.style.getPropertyValue('scrollbar-gutter').includes('stable')
      return viewport.innerWidth - (!hidden || reserved ? scrollbarWidth : 0)
    },
  })
  vi.stubGlobal('HTMLElement', Element)
  vi.stubGlobal('window', viewport)
  vi.stubGlobal('document', {
    documentElement: root,
    body,
    get activeElement() {
      return activeElement
    },
    defaultView: viewport,
    getElementById: () => app,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })
  return {
    root,
    body,
    app,
    trigger,
    viewport,
    setActive: (element: Element) => {
      activeElement = element
    },
    width: () => (root as unknown as HTMLElement).clientWidth,
    locked: () => root.style.overflow === 'hidden' || body.style.overflow === 'hidden',
  }
}

function drawer(open = false) {
  const props = reactive({ open, title: 'Review' })
  const setup = (
    ReviewDrawer as unknown as { setup: (p: typeof props, c: SetupContext) => unknown }
  ).setup
  const instance = renderer.createApp(
    defineComponent({
      setup(_, context) {
        setup(props, context)
        return () => null
      },
    }),
  )
  instance.provide(ssrContextKey, { modules: new Set() })
  instance.mount({})
  const unmount = () => instance.unmount()
  unmounts.push(unmount)
  return { props, unmount }
}

describe('shared review dialog background', () => {
  it.each([0, 13])('keeps page width with a %ipx scrollbar through open/close', async (gap) => {
    const browser = page(gap)
    const dialog = drawer()
    const width = browser.width()

    dialog.props.open = true
    await nextTick()
    expect(browser.locked()).toBe(true)
    expect(browser.width()).toBe(width)
    expect(browser.app.getAttribute('inert')).toBe('')
    expect(browser.app.getAttribute('aria-hidden')).toBe('true')

    dialog.props.open = false
    await nextTick()
    await nextTick()
    expect(browser.locked()).toBe(false)
    expect(browser.width()).toBe(width)
    expect(browser.root.style.getPropertyValue('overflow-x')).toBe('')
    expect(browser.root.style.getPropertyValue('overflow-y')).toBe('')
    expect(browser.root.style.getPropertyValue('scrollbar-gutter')).toBe('')
    expect(browser.viewport.scrollTo).not.toHaveBeenCalled()
    expect(browser.viewport.scrollBy).not.toHaveBeenCalled()
    expect(browser.viewport.scrollY).toBe(420)
    expect(browser.trigger.focus).toHaveBeenCalledWith({ preventScroll: true })
  })

  it('locks an initially open dialog and releases on unmount', async () => {
    const browser = page(13)
    const dialog = drawer(true)
    await nextTick()
    expect(browser.locked()).toBe(true)
    expect(browser.width()).toBe(1267)

    dialog.unmount()
    await nextTick()
    expect(browser.locked()).toBe(false)
    expect(browser.root.style.getPropertyValue('scrollbar-gutter')).toBe('')
    expect(browser.app.getAttribute('inert')).toBeNull()
    expect(browser.app.getAttribute('aria-hidden')).toBeNull()
    expect(browser.trigger.focus).toHaveBeenCalledWith({ preventScroll: true })
  })

  it.each([true, false])(
    'keeps overlapping dialogs locked when the first owner closes first: %s',
    async (firstClosesFirst) => {
      const browser = page(13)
      const first = drawer()
      first.props.open = true
      await nextTick()
      const dialogFocus = new Element()
      browser.setActive(dialogFocus)
      const second = drawer()
      second.props.open = true
      await nextTick()
      const closing = firstClosesFirst ? first : second
      const remaining = firstClosesFirst ? second : first

      closing.props.open = false
      await nextTick()
      await nextTick()
      expect(browser.locked()).toBe(true)
      expect(browser.width()).toBe(1267)
      expect(browser.app.getAttribute('inert')).toBe('')
      expect(browser.trigger.focus).not.toHaveBeenCalled()
      closing.unmount()
      expect(browser.locked()).toBe(true)

      remaining.unmount()
      await nextTick()
      expect(browser.locked()).toBe(false)
      expect(browser.trigger.focus).toHaveBeenCalledOnce()
    },
  )

  it('restores original styles and accessibility attributes without erasing unrelated changes', async () => {
    const browser = page(13)
    browser.root.style.setProperty('overflow-x', 'clip', 'important')
    browser.root.style.setProperty('overflow-y', 'scroll')
    browser.root.style.setProperty('scrollbar-gutter', 'stable both-edges', 'important')
    browser.body.style.setProperty('overflow', 'auto', 'important')
    browser.app.setAttribute('inert', 'existing')
    browser.app.setAttribute('aria-hidden', 'false')
    const dialog = drawer(true)
    await nextTick()
    expect(browser.root.style.getPropertyValue('scrollbar-gutter')).toBe('stable both-edges')
    browser.root.style.setProperty('color', 'red')
    dialog.unmount()
    await nextTick()

    expect(browser.root.style.getPropertyValue('overflow-x')).toBe('clip')
    expect(browser.root.style.getPropertyPriority('overflow-x')).toBe('important')
    expect(browser.root.style.getPropertyValue('overflow-y')).toBe('scroll')
    expect(browser.root.style.getPropertyValue('scrollbar-gutter')).toBe('stable both-edges')
    expect(browser.root.style.getPropertyPriority('scrollbar-gutter')).toBe('important')
    expect(browser.root.style.getPropertyValue('color')).toBe('red')
    expect(browser.body.style.getPropertyValue('overflow')).toBe('auto')
    expect(browser.body.style.getPropertyPriority('overflow')).toBe('important')
    expect(browser.app.getAttribute('inert')).toBe('existing')
    expect(browser.app.getAttribute('aria-hidden')).toBe('false')
  })

  it('ignores repeated release and does not corrupt a later lock', () => {
    const browser = page(13)
    const firstRelease = lockBackground()
    const secondRelease = lockBackground()
    firstRelease()
    firstRelease()
    expect(browser.locked()).toBe(true)
    secondRelease()
    expect(browser.locked()).toBe(false)

    const laterRelease = lockBackground()
    secondRelease()
    expect(browser.locked()).toBe(true)
    laterRelease()
    expect(browser.locked()).toBe(false)
  })

  it('keeps focus suspended while a later background lock remains', async () => {
    const browser = page(0)
    const dialog = drawer(true)
    await nextTick()
    browser.setActive(new Element())
    const heldLock = lockBackground()
    dialog.props.open = false
    await nextTick()
    expect(browser.trigger.focus).not.toHaveBeenCalled()
    heldLock()
  })

  it('discards a detached return target before the next dialog', async () => {
    const browser = page(0)
    const dialog = drawer()
    browser.trigger.isConnected = false

    dialog.props.open = true
    await nextTick()
    dialog.props.open = false
    await nextTick()
    await nextTick()
    expect(browser.trigger.focus).not.toHaveBeenCalled()

    const replacement = new Element()
    browser.setActive(replacement)
    dialog.props.open = true
    await nextTick()
    dialog.props.open = false
    await nextTick()
    await nextTick()
    expect(replacement.focus).toHaveBeenCalledWith({ preventScroll: true })
  })
})
