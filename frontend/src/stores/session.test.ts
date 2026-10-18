/**
 * Session store behaviour.
 *
 * These assertions cover the states the UI depends on — resolving, signed in,
 * signed out — and the 401 path that drops the signed-in chrome.
 *
 * The store talks to the module-level `api` client. openapi-fetch captures its
 * transport when the client is created, so `vi.stubGlobal('fetch')` after import
 * has no effect. The test therefore replaces the `callApi` seam — the single
 * function through which the store performs requests — with a queue of canned
 * results. That keeps the store's own logic (state transitions, error
 * propagation, local cleanup) the thing under test.
 */
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiFailure, ApiResult } from '../api/errors'
import { setUnauthorizedHandler } from '../api/client'
import { useSession } from './session'

/** Results the mocked `callApi` hands out, in order. */
const queue: (ApiResult<unknown> | Error)[] = []

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    callApi: vi.fn(async () => {
      const next = queue.shift()
      if (next instanceof Error) throw next
      return next
    }),
  }
})

function ok<T>(data: T): ApiResult<T> {
  return { ok: true, data, requestId: null }
}

function fail(partial: Partial<ApiFailure>): ApiResult<never> {
  return {
    ok: false,
    failure: {
      kind: 'business',
      code: null,
      message: '请求失败',
      status: null,
      requestId: null,
      retryable: false,
      fields: [],
      ...partial,
    },
  }
}

const user = {
  id: 1,
  email: 'demo@example.com',
  display_name: '演示',
  role: 'user',
  is_active: true,
  created_at: '2026-10-18T00:00:00Z',
  last_signed_in_at: null,
}

describe('session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setUnauthorizedHandler(null)
    queue.length = 0
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('starts in the resolving state so the UI does not flash the login screen', () => {
    const session = useSession()
    expect(session.isResolving).toBe(true)
    expect(session.isAuthenticated).toBe(false)
  })

  it('treats a signed-out probe as anonymous rather than a failure', async () => {
    // The API answers 204 with no body when nobody is signed in, so the client
    // reports success with `data === undefined`.
    queue.push(ok(undefined))
    const session = useSession()
    await session.refresh()
    expect(session.status).toBe('anonymous')
    expect(session.user).toBeNull()
    expect(session.error).toBeNull()
  })

  it('treats a session payload as signed in', async () => {
    queue.push(ok({ user, expires_at: '2026-10-25T00:00:00Z' }))
    const session = useSession()
    await session.refresh()
    expect(session.status).toBe('authenticated')
    expect(session.user?.email).toBe('demo@example.com')
  })

  it('keeps a failed probe distinguishable from signed out', async () => {
    queue.push(
      fail({
        kind: 'business',
        code: 'SERVICE_UNAVAILABLE',
        message: '服务暂不可用。',
        status: 503,
      }),
    )
    const session = useSession()
    await session.refresh()
    expect(session.status).toBe('anonymous')
    expect(session.error).toBe('服务暂不可用。')
  })

  it('reports a login failure instead of pretending success', async () => {
    queue.push(fail({ code: 'INVALID_CREDENTIALS', message: '邮箱或密码不正确。', status: 401 }))
    const session = useSession()
    const error = await session.login('demo@example.com', 'wrong-password')
    expect(error).toBe('邮箱或密码不正确。')
    expect(session.isAuthenticated).toBe(false)
  })

  it('refreshes after a successful login so the shell knows the user', async () => {
    queue.push(ok({ user, expires_at: '2026-10-25T00:00:00Z' }))
    queue.push(ok({ user, expires_at: '2026-10-25T00:00:00Z' }))
    const session = useSession()
    const error = await session.login('demo@example.com', 'a-long-password')
    expect(error).toBeNull()
    expect(session.isAuthenticated).toBe(true)
  })

  it('clears local state on logout even if the request fails', async () => {
    queue.push(new Error('network down'))
    const session = useSession()
    session.$patch({ status: 'authenticated', user })
    await session.logout()
    expect(session.status).toBe('anonymous')
    expect(session.user).toBeNull()
  })

  it('expire() drops the signed-in state when any request answers 401', () => {
    const session = useSession()
    session.$patch({ status: 'authenticated', user })
    session.expire()
    expect(session.status).toBe('anonymous')
    expect(session.user).toBeNull()
  })
})
