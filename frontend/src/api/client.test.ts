import createClient from 'openapi-fetch'
import { describe, expect, it, vi } from 'vitest'
import { api, describeApiError, callApi, toApiResult, type EndpointOutcome } from './client'
import {
  abortedFailure,
  extractRequestId,
  failureFromResponse,
  invalidResponseFailure,
  isAuthNotConfigured,
  networkFailure,
  timeoutFailure,
} from './errors'
import {
  ACCESS_POLICIES,
  DEFAULT_TIMEOUT_MS,
  DIAGNOSTIC_POLICY,
  DIAGNOSTIC_TIMEOUT_MS,
  READ_POLICY,
  READ_RETRY_DELAY_MS,
  RETRYABLE_READ_STATUSES,
  WRITE_POLICY,
  WRITE_TIMEOUT_MS,
  policyForMethod,
  shouldRetry,
} from './policies'
import type { paths } from './schema'

const noWait = async () => true

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function networkError(): never {
  throw new TypeError('Failed to fetch')
}

describe('API failures', () => {
  it('preserves the server explanation for an unconfigured identity provider', () => {
    expect(
      describeApiError({ detail: { code: 'AUTH_NOT_CONFIGURED', message: '登录尚未接入' } }),
    ).toBe('登录尚未接入')
  })
  it('handles validation and network failures without leaking raw objects', () => {
    expect(describeApiError({ detail: [{ msg: 'invalid' }] })).not.toContain('[object Object]')
    expect(describeApiError(undefined)).toContain('请求失败')
  })
  it('never echoes raw exception text or [object Object] through failure messages', () => {
    const failures = [
      networkFailure(),
      timeoutFailure(15_000),
      abortedFailure(),
      invalidResponseFailure(200, null),
      failureFromResponse(jsonResponse('gateway exploded', 502), 'gateway exploded'),
      failureFromResponse(jsonResponse({ unexpected: { nested: true } }, 500), {
        unexpected: { nested: true },
      }),
      failureFromResponse(jsonResponse(null, 429), null),
    ]
    for (const failure of failures) {
      expect(failure.message).not.toContain('[object Object]')
      expect(failure.message).not.toContain('TypeError')
      expect(failure.message).not.toContain('Failed to fetch')
      expect(failure.message.length).toBeGreaterThan(0)
    }
  })
})

describe('policy table', () => {
  it('defaults to a 15s read timeout with a single 300ms-backoff retry', () => {
    expect(DEFAULT_TIMEOUT_MS).toBe(15_000)
    expect(READ_POLICY).toEqual({
      timeoutMs: DEFAULT_TIMEOUT_MS,
      maxRetries: 1,
      retryDelayMs: READ_RETRY_DELAY_MS,
      retryOn: ['network', 'status'],
      retryStatuses: RETRYABLE_READ_STATUSES,
    })
    expect(READ_RETRY_DELAY_MS).toBe(300)
    expect(RETRYABLE_READ_STATUSES).toEqual([502, 503, 504])
  })
  it('gives writes a 30s timeout and never retries them', () => {
    expect(WRITE_POLICY.timeoutMs).toBe(WRITE_TIMEOUT_MS)
    expect(WRITE_TIMEOUT_MS).toBe(30_000)
    expect(WRITE_POLICY.maxRetries).toBe(0)
    expect(WRITE_POLICY.retryOn).toEqual([])
  })
  it('gives diagnostics a 5s timeout and no retry', () => {
    expect(DIAGNOSTIC_POLICY.timeoutMs).toBe(DIAGNOSTIC_TIMEOUT_MS)
    expect(DIAGNOSTIC_TIMEOUT_MS).toBe(5_000)
    expect(DIAGNOSTIC_POLICY.maxRetries).toBe(0)
    expect(ACCESS_POLICIES.read).toBe(READ_POLICY)
    expect(ACCESS_POLICIES.write).toBe(WRITE_POLICY)
    expect(ACCESS_POLICIES.diagnostic).toBe(DIAGNOSTIC_POLICY)
  })
  it('infers read for GET/HEAD and write for mutating methods', () => {
    expect(policyForMethod('GET')).toBe(READ_POLICY)
    expect(policyForMethod('HEAD')).toBe(READ_POLICY)
    expect(policyForMethod('POST')).toBe(WRITE_POLICY)
    expect(policyForMethod('PUT')).toBe(WRITE_POLICY)
    expect(policyForMethod('PATCH')).toBe(WRITE_POLICY)
    expect(policyForMethod('DELETE')).toBe(WRITE_POLICY)
  })
  it('retries only transient network/502/503/504 failures under the read policy', () => {
    expect(shouldRetry(networkFailure(), READ_POLICY)).toBe(true)
    for (const status of [502, 503, 504]) {
      const failure = failureFromResponse(jsonResponse({}, status), {})
      expect(shouldRetry(failure, READ_POLICY)).toBe(true)
    }
    for (const status of [400, 401, 403, 404, 422, 429, 500]) {
      const failure = failureFromResponse(jsonResponse({}, status), {})
      expect(shouldRetry(failure, READ_POLICY)).toBe(false)
    }
    expect(shouldRetry(timeoutFailure(15_000), READ_POLICY)).toBe(false)
    expect(shouldRetry(abortedFailure(), READ_POLICY)).toBe(false)
    expect(shouldRetry(invalidResponseFailure(200, null), READ_POLICY)).toBe(false)
    expect(shouldRetry(networkFailure(), WRITE_POLICY)).toBe(false)
    expect(shouldRetry(networkFailure(), DIAGNOSTIC_POLICY)).toBe(false)
  })
})

describe('request policy execution', () => {
  it('retries one failed read attempt and returns the recovered data', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      async (): Promise<EndpointOutcome<{ items: string[] }>> => {
        attempts += 1
        if (attempts === 1) networkError()
        return {
          data: { items: ['a'] },
          response: jsonResponse({ items: ['a'] }, 200, { 'X-Request-ID': 'rid-retry' }),
        }
      },
      { access: 'read', sleep },
    )
    expect(attempts).toBe(2)
    expect(sleep).toHaveBeenCalledWith(300, expect.anything())
    expect(result).toEqual({ ok: true, data: { items: ['a'] }, requestId: 'rid-retry' })
  })

  it('does not retry a read that failed with 500', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      async () => {
        attempts += 1
        return {
          error: { detail: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试。' } },
          response: jsonResponse({ detail: { code: 'INTERNAL_ERROR' } }, 500),
        }
      },
      { access: 'read', sleep },
    )
    expect(attempts).toBe(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.failure.kind).toBe('business')
      expect(result.failure.status).toBe(500)
      expect(result.failure.retryable).toBe(false)
    }
  })

  it('does not retry a rate-limited read', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      async () => {
        attempts += 1
        return {
          error: { detail: { code: 'RATE_LIMITED', message: '请求过于频繁，请稍后重试。' } },
          response: jsonResponse({ detail: { code: 'RATE_LIMITED' } }, 429),
        }
      },
      { access: 'read', sleep },
    )
    expect(attempts).toBe(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('business')
  })

  it('retries a read on 503 but not on AUTH_NOT_CONFIGURED', async () => {
    let transientAttempts = 0
    const recovered = await callApi(
      async () => {
        transientAttempts += 1
        if (transientAttempts === 1) {
          return { error: undefined, response: new Response('', { status: 503 }) }
        }
        return { data: { items: [] }, response: jsonResponse({ items: [] }) }
      },
      { access: 'read', sleep: noWait },
    )
    expect(transientAttempts).toBe(2)
    expect(recovered.ok).toBe(true)

    let authAttempts = 0
    const auth = await callApi(
      async () => {
        authAttempts += 1
        return {
          error: {
            detail: {
              code: 'AUTH_NOT_CONFIGURED',
              message: '登录模块尚未接入；私人资源不可访问。',
            },
          },
          response: jsonResponse(
            {
              detail: {
                code: 'AUTH_NOT_CONFIGURED',
                message: '登录模块尚未接入；私人资源不可访问。',
              },
            },
            503,
          ),
        }
      },
      { access: 'read', sleep: noWait },
    )
    expect(authAttempts).toBe(1)
    expect(auth.ok).toBe(false)
    if (!auth.ok) {
      expect(isAuthNotConfigured(auth.failure)).toBe(true)
      expect(auth.failure.retryable).toBe(false)
      expect(auth.failure.message).toContain('登录模块尚未接入')
    }
  })

  it('never retries writes, even on network failure', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      async () => {
        attempts += 1
        networkError()
      },
      { access: 'write', sleep },
    )
    expect(attempts).toBe(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('network')
  })

  it('never retries diagnostics', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      async () => {
        attempts += 1
        networkError()
      },
      { access: 'diagnostic', sleep },
    )
    expect(attempts).toBe(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('network')
  })

  it('gives up after the single read retry and reports the last failure', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      async () => {
        attempts += 1
        networkError()
      },
      { access: 'read', sleep },
    )
    expect(attempts).toBe(2)
    expect(sleep).toHaveBeenCalledTimes(1)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('network')
  })

  it('maps a per-attempt timeout to kind=timeout without retrying', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      (signal) => {
        attempts += 1
        return new Promise<EndpointOutcome<never>>((_, reject) => {
          signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
        })
      },
      { access: 'read', timeoutMs: 20, sleep },
    )
    expect(attempts).toBe(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.failure.kind).toBe('timeout')
      expect(result.failure.retryable).toBe(false)
      expect(result.failure.message).toContain('超时')
    }
  })

  it('maps external cancellation to kind=aborted and does not retry', async () => {
    const controller = new AbortController()
    const sleep = vi.fn(noWait)
    let attempts = 0
    const pending = callApi(
      (signal) => {
        attempts += 1
        return new Promise<EndpointOutcome<never>>((_, reject) => {
          signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
        })
      },
      { access: 'read', signal: controller.signal, timeoutMs: 5_000, sleep },
    )
    setTimeout(() => controller.abort(), 10)
    const result = await pending
    expect(attempts).toBe(1)
    expect(sleep).not.toHaveBeenCalled()
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.failure.kind).toBe('aborted')
      expect(result.failure.message).toBe('请求已取消。')
    }
  })

  it('does not call the endpoint when the signal is already aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    const call = vi.fn(async () => ({ data: { items: [] }, response: jsonResponse({}) }))
    const result = await callApi(call, { access: 'read', signal: controller.signal })
    expect(call).not.toHaveBeenCalled()
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('aborted')
  })

  it('stops retrying when the signal is aborted during the backoff wait', async () => {
    const controller = new AbortController()
    let attempts = 0
    const result = await callApi(
      async () => {
        attempts += 1
        networkError()
      },
      {
        access: 'read',
        signal: controller.signal,
        sleep: async () => {
          controller.abort()
          return false
        },
      },
    )
    expect(attempts).toBe(1)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('aborted')
  })

  it('maps an unparsable successful response to kind=invalid-response without retrying', async () => {
    const sleep = vi.fn(noWait)
    let attempts = 0
    const result = await callApi(
      async () => {
        attempts += 1
        throw new SyntaxError('Unexpected token < in JSON at position 0')
      },
      { access: 'read', sleep },
    )
    expect(attempts).toBe(1)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.failure.kind).toBe('invalid-response')
      expect(result.failure.message).not.toContain('Unexpected token')
    }
  })

  it('treats a successful response without data as invalid-response', () => {
    const result = toApiResult({ response: new Response(null, { status: 204 }) })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('invalid-response')
  })
})

describe('failure classification and request ids', () => {
  it('reads X-Request-ID from the response header first', () => {
    const response = jsonResponse({}, 503, { 'X-Request-ID': 'header-id' })
    expect(extractRequestId(response, { detail: { request_id: 'body-id' } })).toBe('header-id')
  })

  it('falls back to detail.request_id from the error body', () => {
    const response = jsonResponse({ detail: { request_id: 'body-id' } }, 503)
    expect(extractRequestId(response, { detail: { request_id: 'body-id' } })).toBe('body-id')
  })

  it('keeps the request id on the classified failure', () => {
    const failure = failureFromResponse(jsonResponse({}, 422, { 'X-Request-ID': 'rid-422' }), {
      detail: { code: 'VALIDATION_FAILED', message: '请求参数校验未通过。' },
    })
    expect(failure.requestId).toBe('rid-422')
    expect(failure.fields).toEqual([])
  })

  it('keeps only field paths and stable codes from the error contract', () => {
    const failure = failureFromResponse(jsonResponse({}, 422), {
      detail: {
        code: 'VALIDATION_FAILED',
        message: '请求参数校验未通过。',
        fields: [
          { path: 'body.name', code: 'MISSING' },
          { path: 'body.description', code: 'TOO_LONG' },
          { path: 'body.secret', code: 'BAD', value: 'raw-input' },
        ],
      },
    })
    expect(failure.fields).toEqual([
      { path: 'body.name', code: 'MISSING' },
      { path: 'body.description', code: 'TOO_LONG' },
      { path: 'body.secret', code: 'BAD' },
    ])
    expect(JSON.stringify(failure)).not.toContain('raw-input')
  })

  it('maps FastAPI validation errors to field paths and stable codes only', () => {
    const failure = failureFromResponse(jsonResponse({}, 422), {
      detail: [
        { loc: ['query', 'limit'], msg: 'Input should be a valid integer', type: 'int_parsing' },
      ],
    })
    expect(failure.kind).toBe('http')
    expect(failure.fields).toEqual([{ path: 'query.limit', code: 'int_parsing' }])
    expect(failure.message).toBe('请求参数校验未通过。')
    expect(JSON.stringify(failure)).not.toContain('Input should be a valid integer')
  })

  it('classifies 502/503/504 without a business code as retryable http failures', () => {
    for (const status of [502, 503, 504]) {
      const failure = failureFromResponse(new Response('bad gateway', { status }), 'bad gateway')
      expect(failure.kind).toBe('http')
      expect(failure.code).toBeNull()
      expect(failure.retryable).toBe(true)
      expect(failure.status).toBe(status)
    }
  })

  it('classifies other statuses as non-retryable', () => {
    for (const status of [400, 401, 403, 404, 422, 429, 500]) {
      const failure = failureFromResponse(jsonResponse({}, status), {})
      expect(failure.retryable).toBe(false)
      expect(failure.kind).toBe('http')
    }
  })
})

describe('openapi-fetch integration', () => {
  // Node 的 Request 需要绝对地址，浏览器端由页面同源相对路径解析。
  const baseUrl = 'http://api.test'

  it('drives a real GET request through the shared client and keeps the generated data type', async () => {
    const requests: Request[] = []
    const client = createClient<paths>({
      baseUrl,
      credentials: 'same-origin',
      fetch: async (input: Request) => {
        requests.push(input)
        return jsonResponse(
          {
            items: [{ id: '1', name: 'n', description: 'd', row_version: 1 }],
            total: 1,
            offset: 0,
            limit: 20,
          },
          200,
          { 'X-Request-ID': 'rid-catalog' },
        )
      },
    })
    const result = await callApi(
      (signal) =>
        client.GET('/api/v1/catalog', { params: { query: { offset: 0, limit: 20 } }, signal }),
      { access: 'read' },
    )
    expect(result).toEqual({
      ok: true,
      data: {
        items: [{ id: '1', name: 'n', description: 'd', row_version: 1 }],
        total: 1,
        offset: 0,
        limit: 20,
      },
      requestId: 'rid-catalog',
    })
    expect(requests).toHaveLength(1)
    expect(requests[0]?.url).toBe('http://api.test/api/v1/catalog?offset=0&limit=20')
    expect(requests[0]?.credentials).toBe('same-origin')
  })

  it('retries a real client call once when the network layer rejects', async () => {
    let calls = 0
    const client = createClient<paths>({
      baseUrl,
      fetch: async () => {
        calls += 1
        if (calls === 1) throw new TypeError('Failed to fetch')
        return jsonResponse({ status: 'ok', version: '0.1.0', authentication: 'not_configured' })
      },
    })
    const sleep = vi.fn(noWait)
    const result = await callApi((signal) => client.GET('/health/live', { signal }), {
      access: 'read',
      sleep,
    })
    expect(calls).toBe(2)
    expect(sleep).toHaveBeenCalledTimes(1)
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.data.version).toBe('0.1.0')
  })

  it('maps a non-JSON 2xx body from the real client to invalid-response', async () => {
    const client = createClient<paths>({
      baseUrl,
      fetch: async () => new Response('<html>proxy</html>', { status: 200 }),
    })
    const result = await callApi((signal) => client.GET('/health/live', { signal }), {
      access: 'diagnostic',
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.failure.kind).toBe('invalid-response')
  })

  it('does not retry a real client read when the response is a 500', async () => {
    let calls = 0
    const client = createClient<paths>({
      baseUrl,
      fetch: async () => {
        calls += 1
        return jsonResponse(
          { detail: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试。' } },
          500,
          { 'X-Request-ID': 'rid-500' },
        )
      },
    })
    const result = await callApi((signal) => client.GET('/health/live', { signal }), {
      access: 'read',
    })
    expect(calls).toBe(1)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.failure.kind).toBe('business')
      expect(result.failure.requestId).toBe('rid-500')
    }
  })

  it('exposes the shared client with same-origin credentials', () => {
    expect(api).toBeDefined()
    expect(typeof api.GET).toBe('function')
  })
})
