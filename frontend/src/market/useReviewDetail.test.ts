import { describe, expect, it } from 'vitest'

import type { ApiResult } from '../api/client'
import type { ReviewOverview } from './review'
import { useReviewDetail } from './useReviewDetail'

function overview(date: string): ReviewOverview {
  return { date } as ReviewOverview
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('review detail request ownership', () => {
  it('does not let an older response overwrite a newer selection', async () => {
    const old = deferred<ApiResult<ReviewOverview>>()
    const latest = deferred<ApiResult<ReviewOverview>>()
    const detail = useReviewDetail((date) => (date === '2026-09-17' ? old.promise : latest.promise))

    const oldLoad = detail.load('2026-09-17', null)
    const latestLoad = detail.load('2026-09-18', null)
    latest.resolve({ ok: true, data: overview('2026-09-18'), requestId: null })
    await latestLoad
    old.resolve({ ok: true, data: overview('2026-09-17'), requestId: null })
    await oldLoad

    expect(detail.data.value?.date).toBe('2026-09-18')
  })

  it('cancels an older request when the next selection is cached', async () => {
    const old = deferred<ApiResult<ReviewOverview>>()
    const detail = useReviewDetail(() => old.promise)

    const oldLoad = detail.load('2026-09-17', null)
    await detail.load('2026-09-18', overview('2026-09-18'))
    old.resolve({ ok: true, data: overview('2026-09-17'), requestId: null })
    await oldLoad

    expect(detail.data.value?.date).toBe('2026-09-18')
  })
})
