/**
 * 按访问类型分组的请求策略。
 *
 * 规则（与架构“前端公共请求层”一致，别处不要再硬编码）：
 *
 * | 访问类型 | 方法 | 超时 | 自动重试 | 退避 | 可重试条件 |
 * | --- | --- | --- | --- | --- | --- |
 * | read（默认） | GET / HEAD | 15s | 最多 1 次 | 300ms | 仅网络故障与 502/503/504 |
 * | write（默认） | POST / PUT / PATCH / DELETE | 30s | 永不 | — | — |
 * | diagnostic（显式） | 健康探活 | 5s | 永不 | — | — |
 *
 * 任何访问类型都不自动重试：超时、429、主动取消、4xx 校验/权限错误，以及 AUTH_NOT_CONFIGURED
 *（状态是 503 但反映认证配置状态，重试不会有不同结果）。
 * 写请求永不自动重试，避免重复提交；幂等键与防重复点击仍由服务端与页面各自负责。
 */

import { RETRYABLE_STATUSES, type ApiFailure } from './errors'

export type AccessType = 'read' | 'write' | 'diagnostic'

/** 可自动重试的失败来源：网络层错误，或受控状态码。 */
export type RetrySource = 'network' | 'status'

export interface AccessPolicy {
  /** 单次尝试的超时（毫秒）。 */
  timeoutMs: number
  /** 自动重试次数上限，0 表示不重试。 */
  maxRetries: number
  /** 两次尝试之间的固定退避（毫秒）。 */
  retryDelayMs: number
  /** 允许自动重试的失败来源。 */
  retryOn: readonly RetrySource[]
  /** 仅当 retryOn 含 'status' 时生效的可重试状态码。 */
  retryStatuses: readonly number[]
}

/** 普通请求默认超时 15 秒；读请求显式沿用。 */
export const DEFAULT_TIMEOUT_MS = 15_000

/** 写请求超时 30 秒：写操作更慢，但永不自动重试。 */
export const WRITE_TIMEOUT_MS = 30_000

/** 健康探活只回答“现在是否可用”，必须快速失败。 */
export const DIAGNOSTIC_TIMEOUT_MS = 5_000

/** 读请求唯一一次重试的固定退避。 */
export const READ_RETRY_DELAY_MS = 300

/** 读请求可自动重试的网关/暂不可用状态；不含 500、429 与任何 4xx。 */
export const RETRYABLE_READ_STATUSES: readonly number[] = RETRYABLE_STATUSES

export const READ_POLICY: AccessPolicy = {
  timeoutMs: DEFAULT_TIMEOUT_MS,
  maxRetries: 1,
  retryDelayMs: READ_RETRY_DELAY_MS,
  retryOn: ['network', 'status'],
  retryStatuses: RETRYABLE_READ_STATUSES,
}

export const WRITE_POLICY: AccessPolicy = {
  timeoutMs: WRITE_TIMEOUT_MS,
  maxRetries: 0,
  retryDelayMs: 0,
  retryOn: [],
  retryStatuses: [],
}

export const DIAGNOSTIC_POLICY: AccessPolicy = {
  timeoutMs: DIAGNOSTIC_TIMEOUT_MS,
  maxRetries: 0,
  retryDelayMs: 0,
  retryOn: [],
  retryStatuses: [],
}

export const ACCESS_POLICIES: Readonly<Record<AccessType, AccessPolicy>> = {
  read: READ_POLICY,
  write: WRITE_POLICY,
  diagnostic: DIAGNOSTIC_POLICY,
}

export type ApiMethod = 'GET' | 'HEAD' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/**
 * 未显式指定访问类型时按 HTTP 方法推断：GET/HEAD 是读，其余是写。
 * diagnostic 必须显式传入，不能由方法推断。
 */
export function policyForMethod(method: ApiMethod): AccessPolicy {
  return method === 'GET' || method === 'HEAD' ? READ_POLICY : WRITE_POLICY
}

/**
 * 该失败在当前策略下是否允许自动重试。
 * - 网络错误按 retryOn 决定；
 * - 只有被归类为瞬时故障（`failure.retryable`，即 502/503/504）且状态码在 retryStatuses
 *   内时才按状态重试；AUTH_NOT_CONFIGURED 这类业务失败显式不算瞬时故障；
 * - 超时、主动取消、非预期响应、429 与其余 4xx 一律不重试。
 */
export function shouldRetry(failure: ApiFailure, policy: AccessPolicy): boolean {
  if (policy.maxRetries <= 0) return false
  if (failure.kind === 'network') return policy.retryOn.includes('network')
  if (!failure.retryable || failure.status === null) return false
  return policy.retryOn.includes('status') && policy.retryStatuses.includes(failure.status)
}
