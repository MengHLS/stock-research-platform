/**
 * Router instance and the session guard.
 *
 * The guard resolves the session once before the first navigation settles.
 * Guarding on `isResolving` matters: redirecting a signed-in user to /login while
 * the probe is still in flight is the classic flash-of-login-screen bug.
 */
import { createRouter, createWebHistory } from 'vue-router'

import { routes } from './routes'
import { useSession } from './stores/session'

export { routes }

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const session = useSession()
  if (session.isResolving) {
    await session.refresh()
  }
  if (to.meta.public) {
    return true
  }
  if (!session.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})
