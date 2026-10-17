import { describe, expect, it } from 'vitest'
import { describeApiError } from './client'

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
})
