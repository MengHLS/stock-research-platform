/**
 * 统一请求执行层：超时、主动取消与自动重试的唯一实现。
 *
 * 分工：
 * - `errors.ts` 负责把一次失败归类成安全结构；
 * - `policies.ts` 负责“哪种访问类型允许什么”（超时/重试/退避）；
 * - 本文件只负责按策略执行尝试、把 AbortSignal 与超时接到每次尝试上，并判断是否重试。
 *
 * 每次尝试都有独立的超时计时器；重试间隔不计入下一次尝试的超时。
 * 外部取消优先于超时：用户离开页面导致的 abort 归类为 aborted，不提示错误。
 * 自动重试只参考 `shouldRetry`，业务失败（带受控业务码）、4xx、429、超时、
 * 主动取消与非预期响应一律不重试。
 */

import { abortedFailure, networkFailure, timeoutFailure, type ApiResult } from './errors'
import { shouldRetry, type AccessPolicy } from './policies'

/** 可注入的等待实现，返回 false 表示等待期间被取消。生产代码不要传。 */
export type SleepFn = (delayMs: number, signal: AbortSignal) => Promise<boolean>

/** 与访问类型无关的调用选项。 */
export interface RequestCallOptions {
  /** 外部取消信号：页面卸载或新查询替代旧查询时触发。 */
  signal?: AbortSignal
  /** 显式覆盖策略默认超时（毫秒）；0 表示不设超时，仅建议测试使用。 */
  timeoutMs?: number
  /** 仅测试注入，避免真实等待退避。 */
  sleep?: SleepFn
}

export interface RunWithPolicyOptions extends RequestCallOptions {
  policy: AccessPolicy
}

/** 一次原始尝试：拿到信号后执行 HTTP 调用，并返回已归类的成功/失败。 */
export type ApiAttempt<T> = (signal: AbortSignal) => Promise<ApiResult<T>>

function defaultSleep(delayMs: number, signal: AbortSignal): Promise<boolean> {
  if (signal.aborted) return Promise.resolve(false)
  return new Promise((resolve) => {
    const timer: ReturnType<typeof setTimeout> = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve(true)
    }, delayMs)
    const onAbort = () => {
      clearTimeout(timer)
      resolve(false)
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

type AttemptOutcome<T> =
  | { kind: 'result'; result: ApiResult<T> }
  | { kind: 'network' }
  | { kind: 'timeout' }
  | { kind: 'aborted' }

/**
 * 执行单次尝试。只依赖标志位判断取消/超时，不读取也不回显异常文本，
 * 因此上游 fetch 的异常名称与消息不会进入用户界面。
 */
async function runAttempt<T>(
  attempt: ApiAttempt<T>,
  timeoutMs: number,
  lifetimeSignal: AbortSignal,
): Promise<AttemptOutcome<T>> {
  if (lifetimeSignal.aborted) return { kind: 'aborted' }
  const controller = new AbortController()
  let timedOut = false
  let abortedExternally = false
  const onLifetimeAbort = () => {
    abortedExternally = true
    controller.abort()
  }
  lifetimeSignal.addEventListener('abort', onLifetimeAbort, { once: true })
  const timer: ReturnType<typeof setTimeout> | null =
    timeoutMs > 0
      ? setTimeout(() => {
          timedOut = true
          controller.abort()
        }, timeoutMs)
      : null
  try {
    return { kind: 'result', result: await attempt(controller.signal) }
  } catch {
    // 主动取消优先于超时：两种信号几乎同时到达时按用户意图处理。
    if (abortedExternally || lifetimeSignal.aborted) return { kind: 'aborted' }
    if (timedOut) return { kind: 'timeout' }
    return { kind: 'network' }
  } finally {
    if (timer !== null) clearTimeout(timer)
    lifetimeSignal.removeEventListener('abort', onLifetimeAbort)
  }
}

function failureForOutcome(
  outcome: Exclude<AttemptOutcome<never>, { kind: 'result' }>,
  timeoutMs: number,
) {
  switch (outcome.kind) {
    case 'timeout':
      // timeoutMs 为 0 时不会产生 timeout；这里传入实际配置值即可。
      return timeoutFailure(timeoutMs)
    case 'aborted':
      return abortedFailure()
    case 'network':
      return networkFailure()
  }
}

/**
 * 按访问策略执行一次请求（页面通常经由 client.ts 的 `callApi` 调用）。
 *
 * - 成功直接返回 `{ok:true,data,requestId}`；
 * - 失败时若策略允许且仍有重试次数，退避后重新尝试；
 * - 外部取消发生在等待/尝试期间时返回 `kind: 'aborted'`，页面据此不提示错误。
 */
export async function runWithPolicy<T>(
  attempt: ApiAttempt<T>,
  options: RunWithPolicyOptions,
): Promise<ApiResult<T>> {
  const { policy, signal: externalSignal, sleep = defaultSleep } = options
  const timeoutMs = options.timeoutMs ?? policy.timeoutMs

  const lifetime = new AbortController()
  const onExternalAbort = () => lifetime.abort()
  if (externalSignal) {
    if (externalSignal.aborted) return { ok: false, failure: abortedFailure() }
    externalSignal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    for (let attemptIndex = 0; ; attemptIndex += 1) {
      if (lifetime.signal.aborted) return { ok: false, failure: abortedFailure() }
      const outcome = await runAttempt(attempt, timeoutMs, lifetime.signal)

      let failure
      if (outcome.kind === 'result') {
        if (outcome.result.ok) return outcome.result
        failure = outcome.result.failure
      } else {
        failure = failureForOutcome(outcome, timeoutMs)
      }

      if (attemptIndex >= policy.maxRetries || !shouldRetry(failure, policy)) {
        return { ok: false, failure }
      }
      const waited = await sleep(policy.retryDelayMs, lifetime.signal)
      if (!waited) return { ok: false, failure: abortedFailure() }
    }
  } finally {
    externalSignal?.removeEventListener('abort', onExternalAbort)
  }
}
