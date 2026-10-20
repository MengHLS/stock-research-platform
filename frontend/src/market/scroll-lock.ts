type ReleaseBackground = () => HTMLElement | null

const locks = new WeakMap<Document, { release: ReleaseBackground; count: number }>()

export function isBackgroundLocked(doc: Document = document): boolean {
  return locks.has(doc)
}

export function lockBackground(doc: Document = document): ReleaseBackground {
  let lock = locks.get(doc)
  if (!lock) {
    const root = doc.documentElement
    const app = doc.getElementById('app')
    const focus = doc.activeElement instanceof HTMLElement ? doc.activeElement : null
    const properties = ['overflow-x', 'overflow-y', 'scrollbar-gutter']
    const styles = properties.map((name) => ({
      name,
      value: root.style.getPropertyValue(name),
      priority: root.style.getPropertyPriority(name),
    }))
    const attributes = ['inert', 'aria-hidden'].map((name) => ({
      name,
      value: app?.getAttribute(name) ?? null,
    }))
    const view = doc.defaultView
    // Reserve only an existing gutter; short pages and overlay scrollbars need none.
    if (
      view &&
      view.innerWidth > root.clientWidth &&
      !view.getComputedStyle(root).scrollbarGutter.includes('stable')
    ) {
      root.style.setProperty('scrollbar-gutter', 'stable')
    }
    root.style.setProperty('overflow-x', 'hidden')
    root.style.setProperty('overflow-y', 'hidden')
    app?.setAttribute('inert', '')
    app?.setAttribute('aria-hidden', 'true')
    lock = {
      count: 0,
      release: () => {
        for (const { name, value, priority } of styles) {
          if (value) root.style.setProperty(name, value, priority)
          else root.style.removeProperty(name)
        }
        for (const { name, value } of attributes) {
          if (value === null) app?.removeAttribute(name)
          else app?.setAttribute(name, value)
        }
        return focus
      },
    }
    locks.set(doc, lock)
  }
  lock.count++
  const acquired = lock
  let released = false
  return () => {
    if (released) return null
    released = true
    if (--acquired.count) return null
    locks.delete(doc)
    return acquired.release()
  }
}
