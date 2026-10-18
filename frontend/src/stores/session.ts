/**
 * Session state for the SPA.
 *
 * The cookie is HttpOnly, so the browser cannot read it and this store never
 * tries: it asks `GET /api/v1/auth/session` after load and after any change that
 * could end the session. `user === null` therefore means "resolved and not signed
 * in", while `status === 'unknown'` means "not asked yet" — the UI must not flash
 * a login screen before the first answer, and must not show app chrome to a
 * signed-out stranger either.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, callApi } from '../api/client'

export interface SessionUser {
  id: number
  email: string
  display_name: string
  role: string
  is_active: boolean
  created_at: string
  last_signed_in_at: string | null
}

type Status = 'unknown' | 'authenticated' | 'anonymous'

export const useSession = defineStore('session', () => {
  const status = ref<Status>('unknown')
  const user = ref<SessionUser | null>(null)
  const error = ref<string | null>(null)
  const busy = ref(false)

  const isAuthenticated = computed(() => status.value === 'authenticated')
  /** True while the very first session probe is still in flight. */
  const isResolving = computed(() => status.value === 'unknown')

  async function refresh() {
    const result = await callApi((signal) => api.GET('/api/v1/auth/session', { signal }))
    if (!result.ok) {
      // A failed probe is not "signed out": surfacing the failure keeps a broken
      // backend distinguishable from a missing session.
      error.value = result.failure.message ?? '无法确认登录状态'
      status.value = 'anonymous'
      user.value = null
      return
    }
    // A signed-out probe answers 204 with no body, so `data` is undefined here.
    const session = result.data as { user: SessionUser } | undefined
    user.value = session?.user ?? null
    status.value = session ? 'authenticated' : 'anonymous'
    error.value = null
  }

  async function login(email: string, password: string): Promise<string | null> {
    busy.value = true
    error.value = null
    try {
      const result = await callApi((signal) =>
        api.POST('/api/v1/auth/login', { body: { email, password }, signal }),
      )
      if (!result.ok) {
        error.value = result.failure.message ?? '登录失败'
        return error.value
      }
      await refresh()
      return null
    } finally {
      busy.value = false
    }
  }

  async function register(
    email: string,
    password: string,
    displayName: string,
    invitationCode: string,
  ): Promise<string | null> {
    busy.value = true
    error.value = null
    try {
      const result = await callApi((signal) =>
        api.POST('/api/v1/auth/register', {
          body: {
            email,
            password,
            display_name: displayName,
            // Sent as null when blank so the server treats it as "not provided"
            // rather than an empty string that fails code lookup.
            invitation_code: invitationCode.trim() || null,
          },
          signal,
        }),
      )
      if (!result.ok) {
        error.value = result.failure.message ?? '注册失败'
        return error.value
      }
      await refresh()
      return null
    } finally {
      busy.value = false
    }
  }

  async function logout() {
    busy.value = true
    try {
      await callApi((signal) => api.POST('/api/v1/auth/logout', { signal }))
    } catch {
      // `callApi` reports failures as values, not exceptions, so reaching here
      // means something unexpected (a bug, not an outage). Swallowing it is still
      // right: the user asked to end the session, and the local state below is
      // what the UI must reflect either way.
    } finally {
      // Clear locally even if the request failed: the UI must not keep showing a
      // session the user asked to end. The server row is revoked on its own.
      user.value = null
      status.value = 'anonymous'
      busy.value = false
    }
  }

  /** Called by the request layer when any endpoint answers 401. */
  function expire() {
    user.value = null
    status.value = 'anonymous'
  }

  return {
    status,
    user,
    error,
    busy,
    isAuthenticated,
    isResolving,
    refresh,
    login,
    register,
    logout,
    expire,
  }
})
