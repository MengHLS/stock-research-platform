/**
 * Navigation model and route wiring.
 *
 * The assertions are about consistency, which is what actually breaks when pages
 * are added: a nav entry without a route, a route showing a planned page while
 * claiming to be implemented, or a mismatch between the nav label and the page
 * title. They do not assert markup.
 */
import { describe, expect, it } from 'vitest'

import { navGroups } from './navigation'
import { routes } from './routes'

const allItems = navGroups.flatMap((group) => group.items)
const routePaths = new Set(
  routes.filter((route) => route.path !== '/:pathMatch(.*)*').map((route) => route.path),
)

describe('navigation model', () => {
  it('gives every entry a unique id and path', () => {
    const ids = allItems.map((item) => item.id)
    const paths = allItems.map((item) => item.path)
    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it('resolves every implemented entry to a declared route', () => {
    const missing = allItems
      .filter((item) => item.implemented)
      .filter((item) => !routePaths.has(item.path))
      .map((item) => item.path)
    expect(missing).toEqual([])
  })

  it('also declares routes for planned entries, so the sidebar never 404s', () => {
    const missing = allItems.filter((item) => !routePaths.has(item.path)).map((item) => item.path)
    expect(missing).toEqual([])
  })

  it('keeps planned entries labelled as planned instead of silently working', () => {
    const planned = allItems.filter((item) => !item.implemented)
    expect(planned.length).toBeGreaterThan(0)
    // Every planned entry must render the honest placeholder, not a real page.
    for (const item of planned) {
      const route = routes.find((candidate) => candidate.path === item.path)
      expect(route?.meta?.pending, `${item.path} needs a pending explanation`).toBeTruthy()
    }
  })

  it('groups every item under a titled section', () => {
    expect(navGroups.length).toBeGreaterThan(0)
    for (const group of navGroups) {
      expect(group.title.length).toBeGreaterThan(0)
      expect(group.items.length).toBeGreaterThan(0)
      for (const item of group.items) {
        expect(item.name.length).toBeGreaterThan(0)
        expect(item.icon.length).toBeGreaterThan(0)
      }
    }
  })
})

describe('routes', () => {
  it('exposes the login page publicly and everything else behind a session', () => {
    const login = routes.find((route) => route.path === '/login')
    expect(login?.meta?.public).toBe(true)
    const guarded = routes.filter(
      (route) => route.path !== '/login' && route.path !== '/:pathMatch(.*)*',
    )
    expect(guarded.length).toBeGreaterThan(0)
    for (const route of guarded) {
      expect(route.meta?.public, `${route.path} must not be public`).not.toBe(true)
    }
  })

  it('gives every non-catch-all route a page title for the topbar', () => {
    const missing = routes
      .filter((route) => route.path !== '/:pathMatch(.*)*')
      .filter((route) => !route.meta?.title)
      .map((route) => route.path)
    expect(missing).toEqual([])
  })
})
