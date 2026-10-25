import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import {
  positionBandLabel,
  type FirstBoardCatalog,
  type FirstBoardClass,
  type FirstBoardClassification,
  type FirstBoardEventList,
  type FirstBoardShortPath,
  type FirstBoardTrend,
} from './first-board-classifier'

export function useFirstBoardClassifierPage() {
  const catalog = ref<FirstBoardCatalog | null>(null)
  const catalogFailure = ref<ApiFailure | null>(null)
  const catalogLoading = ref(false)
  const position = ref<string | number>('')
  const trend = ref<FirstBoardTrend>('up')
  const shortPath = ref<FirstBoardShortPath>('up_pullback')
  const result = ref<FirstBoardClassification | null>(null)
  const classifyFailure = ref<ApiFailure | null>(null)
  const classifying = ref(false)
  const stockCode = ref('')
  const eventDate = ref('')
  const events = ref<FirstBoardEventList | null>(null)
  const eventsFailure = ref<ApiFailure | null>(null)
  const eventsLoading = ref(false)

  let catalogController: AbortController | null = null
  let classifyController: AbortController | null = null
  let eventsController: AbortController | null = null

  const selectedCode = computed(() => result.value?.class_code ?? '')
  const selectedGroup = computed(() => result.value?.group_code ?? '')

  watch([position, trend, shortPath], () => {
    classifyController?.abort()
    result.value = null
    classifyFailure.value = null
    classifying.value = false
  })
  watch([stockCode, eventDate], () => {
    eventsController?.abort()
    events.value = null
    eventsFailure.value = null
    eventsLoading.value = false
  })

  function failureText(value: ApiFailure): string {
    if (isAuthNotConfigured(value)) return '登录服务尚未启用，无法读取首板分类。'
    if (value.kind === 'network') return '无法连接后台服务，请确认 API 已启动。'
    if (value.code === 'SOURCE_NOT_CONFIGURED') {
      return '冻结首板账本尚未配置，暂无可查询的真实事件。'
    }
    if (value.kind === 'business' && value.code === 'FIRST_BOARD_CLASSIFICATION_UNSUPPORTED') {
      return '这组背景轴不在原十六类口径内，不会静默归到其他类别。'
    }
    return value.message
  }

  function classesFor(groupCode: string): FirstBoardClass[] {
    return catalog.value?.classes.filter((item) => item.group_code === groupCode) ?? []
  }

  async function loadCatalog() {
    catalogController?.abort()
    const current = new AbortController()
    catalogController = current
    catalogLoading.value = true
    catalogFailure.value = null
    const loaded = await callApi(
      (signal) => api.GET('/api/v1/research/first-board-classifier', { signal }),
      { access: 'read', signal: current.signal },
    )
    if (catalogController !== current || current.signal.aborted) return
    catalogLoading.value = false
    if (loaded.ok) {
      catalog.value = loaded.data
    } else if (loaded.failure.kind !== 'aborted') {
      catalog.value = null
      catalogFailure.value = loaded.failure
    }
  }

  async function classify() {
    classifyController?.abort()
    const current = new AbortController()
    classifyController = current
    classifying.value = true
    classifyFailure.value = null
    result.value = null
    const rawPosition = String(position.value).trim()
    const classified = await callApi(
      (signal) =>
        api.POST('/api/v1/research/first-board-classifier/classify', {
          body: {
            position_60d_pct: rawPosition === '' ? null : rawPosition,
            trend: trend.value,
            short_path: shortPath.value,
          },
          signal,
        }),
      { access: 'write', signal: current.signal },
    )
    if (classifyController !== current || current.signal.aborted) return
    classifying.value = false
    if (classified.ok) {
      result.value = classified.data
    } else if (classified.failure.kind !== 'aborted') {
      classifyFailure.value = classified.failure
    }
  }

  async function loadEvents() {
    eventsController?.abort()
    const current = new AbortController()
    eventsController = current
    eventsLoading.value = true
    eventsFailure.value = null
    events.value = null
    const loaded = await callApi(
      (signal) =>
        api.GET('/api/v1/research/first-board-classifier/events', {
          params: {
            query: {
              stock_code: stockCode.value.trim(),
              date: eventDate.value || null,
              limit: 100,
            },
          },
          signal,
        }),
      { access: 'read', signal: current.signal },
    )
    if (eventsController !== current || current.signal.aborted) return
    eventsLoading.value = false
    if (loaded.ok) {
      events.value = loaded.data
    } else if (loaded.failure.kind !== 'aborted') {
      eventsFailure.value = loaded.failure
    }
  }

  onMounted(loadCatalog)
  onUnmounted(() => {
    catalogController?.abort()
    classifyController?.abort()
    eventsController?.abort()
  })

  return {
    catalog,
    catalogFailure,
    catalogLoading,
    position,
    trend,
    shortPath,
    result,
    classifyFailure,
    classifying,
    stockCode,
    eventDate,
    events,
    eventsFailure,
    eventsLoading,
    selectedCode,
    selectedGroup,
    failureText,
    classesFor,
    positionBandLabel,
    loadCatalog,
    classify,
    loadEvents,
  }
}
