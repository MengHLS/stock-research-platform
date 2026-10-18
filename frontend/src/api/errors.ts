/**
 * 统一失败分类：把各种请求失败收敛成可安全展示的结构。
 *
 * 约束（见架构“前端公共请求层”）：
 * - 不把原始异常、堆栈、`[object Object]` 或未审核的服务端文本回显给用户；
 * - `message` 只来自受控状态码文案或后端已审核的业务文案；
 * - `fields` 只保留字段路径与稳定错误码，不带原始输入值；
 * - `requestId` 取响应头 `X-Request-ID`，缺失时回退到错误体 `detail.request_id`。
 */

export type ApiFailureKind =
  'business' | 'http' | 'network' | 'timeout' | 'aborted' | 'invalid-response'

export interface ApiFieldFailure {
  /** 字段路径，例如 `body.name`。 */
  path: string
  /** 稳定错误码，不含原始输入值。 */
  code: string
}

export interface ApiFailure {
  /** 失败类别：业务错误 / HTTP 错误 / 网络不可达 / 超时 / 主动取消 / 非预期响应。 */
  kind: ApiFailureKind
  /** 受控业务码（错误体 `detail.code`），没有则为 null。 */
  code: string | null
  /** 可直接展示给用户的安全文案。 */
  message: string
  /** HTTP 状态码；网络、超时、取消失败为 null。 */
  status: number | null
  /** 响应头 `X-Request-ID` 或错误体 `detail.request_id`。 */
  requestId: string | null
  /** 失败类别本身是否属于可重试的瞬时故障（网络错误与 502/503/504）。是否自动重试仍由访问策略决定。 */
  retryable: boolean
  /** 字段级失败：只含字段路径与稳定错误码。 */
  fields: ApiFieldFailure[]
}

export type ApiResult<T> =
  { ok: true; data: T; requestId: string | null } | { ok: false; failure: ApiFailure }

/** 兜底文案：只有这里列出的文案才会展示给用户。 */
export const SAFE_FAILURE_MESSAGE = '请求失败，请检查后台状态；当前没有加载示例数据代替结果。'

/** 认证尚未接入时后端返回的稳定业务码。 */
export const AUTH_NOT_CONFIGURED_CODE = 'AUTH_NOT_CONFIGURED'

/** 瞬时故障的 HTTP 状态（类别层面）：网关/服务暂不可用，请求本身没有副作用。 */
export const RETRYABLE_STATUSES: readonly number[] = [502, 503, 504]

export function isRetryableStatus(status: number | null): boolean {
  return status !== null && RETRYABLE_STATUSES.includes(status)
}

const STATUS_MESSAGES: Readonly<Record<number, string>> = {
  400: '请求内容无法处理。',
  401: '需要登录后访问。',
  403: '无权访问该资源。',
  404: '接口或资源不存在。',
  405: '该接口不支持此请求方法。',
  408: '请求超时，请稍后重试。',
  409: '请求与现有状态冲突。',
  422: '请求参数校验未通过。',
  429: '请求过于频繁，请按提示稍后重试。',
}

function messageForStatus(status: number): string {
  const known = STATUS_MESSAGES[status]
  if (known) return known
  if (status >= 500) return '服务暂不可用，请稍后重试。'
  if (status >= 400) return '请求未被接受，请检查后重试。'
  return SAFE_FAILURE_MESSAGE
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function safeText(value: unknown, maxLength = 200): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  return trimmed.slice(0, maxLength)
}

interface DetailInfo {
  code: string | null
  message: string | null
  requestId: string | null
  fields: ApiFieldFailure[]
}

/** 读取受控字段列表：只接受 `{path, code}` 两个字符串。 */
function readFields(value: unknown): ApiFieldFailure[] {
  if (!Array.isArray(value)) return []
  const fields: ApiFieldFailure[] = []
  for (const item of value) {
    const record = asRecord(item)
    if (!record) continue
    const path = safeText(record.path)
    const code = safeText(record.code)
    if (path && code) fields.push({ path, code })
    if (fields.length === 20) break
  }
  return fields
}

/** 兼容 FastAPI 默认校验错误 `[{loc, msg, type}]`：只保留位置与稳定类型码。 */
function readValidationFields(value: unknown): ApiFieldFailure[] {
  if (!Array.isArray(value)) return []
  const fields: ApiFieldFailure[] = []
  for (const item of value) {
    const record = asRecord(item)
    if (!record) continue
    const code = safeText(record.type)
    const location = record.loc
    const path = Array.isArray(location) ? location.map((part) => String(part)).join('.') : null
    if (path && code) fields.push({ path, code })
    if (fields.length === 20) break
  }
  return fields
}

/** 从错误体读取受控明细；结构不符合约定时返回 null，由状态码文案兜底。 */
function readDetail(body: unknown): DetailInfo | null {
  const root = asRecord(body)
  if (!root) return null
  const detail = root.detail
  const record = asRecord(detail)
  if (record) {
    return {
      code: safeText(record.code),
      message: safeText(record.message),
      requestId: safeText(record.request_id),
      fields: readFields(record.fields),
    }
  }
  if (Array.isArray(detail)) {
    return { code: null, message: null, requestId: null, fields: readValidationFields(detail) }
  }
  return null
}

/** 提取请求标识：优先响应头，其次错误体；都没有时返回 null。 */
export function extractRequestId(response: Response | null, body: unknown): string | null {
  const header = response?.headers.get('X-Request-ID')
  if (header) {
    const fromHeader = safeText(header)
    if (fromHeader) return fromHeader
  }
  return readDetail(body)?.requestId ?? null
}

/** 非 2xx 响应 → 失败；有受控业务码时为 business，否则为 http。 */
export function failureFromResponse(response: Response, body: unknown): ApiFailure {
  const detail = readDetail(body)
  const status = response.status
  const code = detail?.code ?? null
  const message = code && detail?.message ? detail.message : messageForStatus(status)
  return {
    kind: code ? 'business' : 'http',
    code,
    message,
    status,
    requestId: extractRequestId(response, body),
    // 502/503/504 在类别上属于瞬时故障；AUTH_NOT_CONFIGURED 虽然状态是 503，
    // 但反映的是认证配置状态，重试不会有不同结果，故显式排除。
    retryable: code === AUTH_NOT_CONFIGURED_CODE ? false : isRetryableStatus(status),
    fields: detail?.fields ?? [],
  }
}

export function networkFailure(): ApiFailure {
  return {
    kind: 'network',
    code: null,
    message: '无法连接后台服务，请确认 API 已启动或检查网络。',
    status: null,
    requestId: null,
    retryable: true,
    fields: [],
  }
}

export function timeoutFailure(timeoutMs: number): ApiFailure {
  const seconds = Math.max(1, Math.round(timeoutMs / 1000))
  return {
    kind: 'timeout',
    code: null,
    message: `请求超时（超过 ${seconds} 秒未响应），请稍后重试。`,
    status: null,
    requestId: null,
    // 超时一律不自动重试（规则见 policies.ts）。
    retryable: false,
    fields: [],
  }
}

export function abortedFailure(): ApiFailure {
  return {
    kind: 'aborted',
    code: null,
    message: '请求已取消。',
    status: null,
    requestId: null,
    retryable: false,
    fields: [],
  }
}

export function invalidResponseFailure(
  status: number | null,
  requestId: string | null,
): ApiFailure {
  return {
    kind: 'invalid-response',
    code: null,
    message: '后台返回了无法解析的响应，请稍后重试。',
    status,
    requestId,
    retryable: false,
    fields: [],
  }
}

/** 认证尚未接入（AUTH_NOT_CONFIGURED）：页面据此区分“未接入认证”和普通失败。 */
export function isAuthNotConfigured(failure: ApiFailure): boolean {
  return failure.kind === 'business' && failure.code === AUTH_NOT_CONFIGURED_CODE
}

/**
 * 兼容旧调用点：从原始错误体取出安全文案。
 * 只接受字符串或 `detail.message` 字符串，其余一律返回受控兜底文案。
 */
export function describeApiError(error: unknown): string {
  const root = asRecord(error)
  if (root) {
    const detail = root.detail
    if (typeof detail === 'string') {
      const text = safeText(detail)
      if (text) return text
    }
    if (Array.isArray(detail)) return messageForStatus(422)
    const record = asRecord(detail)
    if (record) {
      const message = safeText(record.message)
      if (message) return message
    }
  }
  return SAFE_FAILURE_MESSAGE
}
