/**
 * Navigation model and route wiring.
 *
 * The assertions are about consistency, which is what actually breaks when pages
 * are added: a nav entry without a route, a route showing a planned page while
 * claiming to be implemented, or a mismatch between the nav label and the page
 * title. They do not assert markup.
 */
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { navGroups } from './navigation'
import PlannedPage from './pages/PlannedPage.vue'
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
    // Both directions must hold for a planned entry: the route explains itself,
    // and it renders the placeholder rather than a real page that would then be
    // presented as "coming soon" while actually working.
    for (const item of planned) {
      const route = routes.find((candidate) => candidate.path === item.path)
      expect(route?.meta?.pending, `${item.path} needs a pending explanation`).toBeTruthy()
      expect(route?.component, `${item.path} is planned`).toBe(PlannedPage)
    }
  })

  it('never claims an entry is implemented while it renders the placeholder', () => {
    // `/market/intraday` used to be marked implemented while its route rendered
    // `PlannedPage`, so the rail offered a page that only says "not built".
    //
    // The non-empty assertion matters: without it, marking *every* entry as
    // planned would make the loop body never run and the test silently pass.
    const implemented = allItems.filter((entry) => entry.implemented)
    expect(implemented.length).toBeGreaterThan(0)
    for (const item of implemented) {
      const route = routes.find((candidate) => candidate.path === item.path)
      expect(route?.component, `${item.path} is marked implemented`).not.toBe(PlannedPage)
      expect(route?.meta?.pending, `${item.path} is implemented`).toBeUndefined()
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
  /**
   * Public routes are an explicit allow-list, not "anything without a guard".
   * Adding an entry here is a deliberate statement that the page is safe for a
   * signed-out visitor; the test exists so that stays a decision, not an
   * accident.
   */
  const PUBLIC_PATHS = ['/login', '/about']

  it('exposes only the allow-listed pages without a session', () => {
    for (const path of PUBLIC_PATHS) {
      const route = routes.find((candidate) => candidate.path === path)
      expect(route?.meta?.public, `${path} must be public`).toBe(true)
    }

    const guarded = routes.filter(
      (route) => !PUBLIC_PATHS.includes(route.path) && route.path !== '/:pathMatch(.*)*',
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

  it('temporarily lands on the market review overview', () => {
    expect(routes.find((route) => route.path === '/')?.redirect).toBe('/market/overview')
    expect(routes.find((route) => route.path === '/:pathMatch(.*)*')?.redirect).toBe(
      '/market/overview',
    )
  })

  it('navigates the landing path and unknown paths to the market overview route', async () => {
    const landingRouter = createRouter({
      history: createMemoryHistory(),
      routes,
    })
    await landingRouter.push('/')
    expect(landingRouter.currentRoute.value.name).toBe('market-overview')
    await landingRouter.push('/path-that-does-not-exist')
    expect(landingRouter.currentRoute.value.name).toBe('market-overview')
  })
})
