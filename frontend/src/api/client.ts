/**
 * 有类型的请求入口：把 openapi-fetch 的 {data,error,response} 结果适配成
 * `ApiResult` 判别联合，再把单次调用交给 request.ts 按访问类型执行。
 *
 * 类型仍完全来自 `schema.d.ts` 的 `paths`：调用方写
 * `callApi((signal) => api.GET('/api/v1/catalog', { params, signal }))`，
 * 成功数据的类型由对应 path 的成功响应推导，不需要手写类型断言或复制接口模型。
 */

import createClient from 'openapi-fetch'
import type { paths } from './schema'
import {
  describeApiError,
  extractRequestId,
  failureFromResponse,
  invalidResponseFailure,
  type ApiResult,
} from './errors'
import { ACCESS_POLICIES, type AccessPolicy, type AccessType } from './policies'
import { runWithPolicy, type ApiAttempt, type RequestCallOptions } from './request'

export { describeApiError }
export type { ApiFailure, ApiResult, ApiFailureKind } from './errors'

/** 共享客户端：保持同源凭据，与后端同站部署。 */
export const api = createClient<paths>({ credentials: 'same-origin' })

/** 一次端点的原始结果：成功携带既定类型的数据，失败携带未受控错误体与响应。 */
export type EndpointOutcome<T> = {
  data?: T
  error?: unknown
  response: Response
}

/** 端点调用：外部取消信号是唯一可注入参数，其余参数由页面固定。 */
export type EndpointCall<T> = (signal: AbortSignal) => Promise<EndpointOutcome<T>>

export interface CallApiOptions extends RequestCallOptions {
  /** 访问类型，决定超时/重试；默认 read。diagnostic 必须显式传入。 */
  access?: AccessType
  /** 直接指定策略，优先于 access（仅测试或特殊端点使用）。 */
  policy?: AccessPolicy
}

/**
 * 把一次 openapi-fetch 结果转成判别联合。
 * - 非 2xx：按状态码与错误体归类（business/http），并提取 request_id；
 * - 2xx 但没有数据（如期望 JSON 却收到 204/空体）：invalid-response。
 */
export function toApiResult<T>(outcome: EndpointOutcome<T>): ApiResult<T> {
  const { response } = outcome
  if (!response.ok) {
    return { ok: false, failure: failureFromResponse(response, outcome.error) }
  }
  const requestId = extractRequestId(response, undefined)
  if (outcome.data === undefined) {
    return { ok: false, failure: invalidResponseFailure(response.status, requestId) }
  }
  return { ok: true, data: outcome.data, requestId }
}

/** 包装端点调用：把 openapi-fetch 的返回或抛出的 SyntaxError 归一到一次尝试。 */
function asAttempt<T>(call: EndpointCall<T>): ApiAttempt<T> {
  return async (signal) => {
    try {
      return toApiResult(await call(signal))
    } catch (error) {
      // openapi-fetch 在 2xx 响应无法按 JSON 解析时会抛 SyntaxError：
      // 这是“非预期响应”，不是网络不可达，因此单独归类。
      if (error instanceof SyntaxError) {
        return { ok: false, failure: invalidResponseFailure(null, null) }
      }
      // 其余异常（fetch 网络失败、取消、超时）交给 request.ts 按信号标志归类。
      throw error
    }
  }
}

/**
 * 按访问类型执行一次端点调用，返回判别联合结果。
 *
 * ```ts
 * const result = await callApi((signal) => api.GET('/health/live', { signal }), {
 *   access: 'diagnostic',
 * })
 * if (!result.ok) showFailure(result.failure)
 * else use(result.data)
 * ```
 */
export async function callApi<T>(
  call: EndpointCall<T>,
  options: CallApiOptions = {},
): Promise<ApiResult<T>> {
  const { access = 'read', policy = ACCESS_POLICIES[access], signal, timeoutMs, sleep } = options
  return runWithPolicy(asAttempt(call), { policy, signal, timeoutMs, sleep })
}
