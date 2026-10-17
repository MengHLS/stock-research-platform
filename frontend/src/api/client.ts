import createClient from 'openapi-fetch'
import type { paths } from './schema'

export const api = createClient<paths>({ credentials: 'same-origin' })

export function describeApiError(error: unknown): string {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = error.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && 'message' in detail) {
      return String(detail.message)
    }
  }
  return '请求失败，请检查后台状态；当前没有加载示例数据代替结果。'
}
