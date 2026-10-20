import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ReviewDrawer from '../components/market/ReviewDrawer.vue'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import type {
  LadderRow,
  LimitUpReviewRow,
  ReviewContext,
  ReviewLimitUp,
  ReviewOverview,
} from './review'
import { routeDate } from './review'
import { SENTIMENT_WINDOWS, parseSentimentWindow } from './sentiment'

export function useMarketSentimentPage() {
  const route = useRoute()
  const router = useRouter()

  const context = ref<ReviewContext | null>(null)
  const overview = ref<ReviewOverview | null>(null)
  const contextFailure = ref<ApiFailure | null>(null)
  const overviewFailure = ref<ApiFailure | null>(null)
  const localDateError = ref('')
  const loading = ref(false)
  const reloadKey = ref(0)
  const drawerOpen = ref(false)
  const drawerLoading = ref(false)
  const drawerFailure = ref<ApiFailure | null>(null)
  const drawerMessage = ref('')
  const selectedLeader = ref<LadderRow | null>(null)
  const selectedRow = ref<LimitUpReviewRow | null>(null)
  const peerRows = ref<LimitUpReviewRow[]>([])
  const drawer = ref<InstanceType<typeof ReviewDrawer> | null>(null)
  const notes = reactive<Record<string, string>>({})

  let requestController: AbortController | null = null
  let drawerController: AbortController | null = null
  let requestSequence = 0
  let drawerSequence = 0

  const rawDateQuery = computed(() => route.query.date)
  const explicitInvalidDate = computed(
    () =>
      rawDateQuery.value !== undefined &&
      (typeof rawDateQuery.value !== 'string' || !routeDate(rawDateQuery.value)),
  )
  const maximumWindow = computed(() => context.value?.window_max ?? 120)
  const windowOptions = computed(() => {
    const values: number[] = SENTIMENT_WINDOWS.filter((item) => item <= maximumWindow.value)
    if (!values.length) values.push(maximumWindow.value)
    if (!values.includes(maximumWindow.value)) values.push(maximumWindow.value)
    return Array.from(new Set(values)).sort((left, right) => left - right)
  })
  const selectedWindow = computed(() =>
    parseSentimentWindow(route.query.window, maximumWindow.value),
  )
  const selectedDate = computed(
    () =>
      routeDate(rawDateQuery.value) ??
      context.value?.requested_date ??
      context.value?.default_date ??
      '',
  )
  const history = computed(() => overview.value?.history ?? [])
  const showInitialLoading = computed(
    () => loading.value && !overview.value && !contextFailure.value && !localDateError.value,
  )
  const drawerTitle = computed(
    () => selectedRow.value?.name ?? selectedLeader.value?.name ?? '股票记录',
  )
  const drawerMeta = computed(() => {
    const row = selectedRow.value ?? selectedLeader.value
    const date = selectedRow.value?.date ?? overview.value?.date ?? selectedDate.value
    return row ? `${row.symbol} · ${row.sector} · ${date}` : ''
  })
  const noteKey = computed(() =>
    selectedRow.value
      ? `${selectedRow.value.date}|${selectedRow.value.symbol}|${selectedRow.value.status}`
      : '',
  )

  function failureText(failure: ApiFailure): string {
    if (isAuthNotConfigured(failure)) return '服务端尚未配置认证，无法读取历史复盘数据。'
    if (failure.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
    return failure.message
  }

  function updateQuery(patch: Record<string, string | undefined>) {
    const query = { ...route.query, ...patch }
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === '') delete query[key]
    }
    void router.push({ path: route.path, query })
  }

  function chooseDate(value: string) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return
    updateQuery({ date: value, window: String(selectedWindow.value) })
  }

  function chooseWindow(value: number) {
    updateQuery({ window: String(value) })
  }

  function goDate(value: string | null | undefined) {
    if (value) updateQuery({ date: value })
  }

  function resetToLatest() {
    updateQuery({ date: undefined, window: String(selectedWindow.value) })
  }

  function closeDrawer() {
    drawerController?.abort()
    drawerSequence += 1
    drawerOpen.value = false
    drawerLoading.value = false
    drawerFailure.value = null
    drawerMessage.value = ''
    selectedLeader.value = null
    selectedRow.value = null
    peerRows.value = []
  }

  async function openLeader(row: LadderRow) {
    drawerController?.abort()
    const current = new AbortController()
    drawerController = current
    const sequence = ++drawerSequence
    selectedLeader.value = row
    selectedRow.value = null
    peerRows.value = []
    drawerFailure.value = null
    drawerMessage.value = ''
    drawerLoading.value = true
    drawerOpen.value = true
    await nextTick()
    drawer.value?.focusPanel()

    const date = overview.value?.date ?? selectedDate.value
    const result = await callApi(
      (signal) =>
        api.GET('/api/v1/market/review/limit-up', {
          params: { query: { date, window: 1 } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    )
    if (drawerController !== current || sequence !== drawerSequence) return
    drawerLoading.value = false
    if (!result.ok) {
      if (result.failure.kind !== 'aborted') drawerFailure.value = result.failure
      return
    }
    const payload: ReviewLimitUp = result.data
    peerRows.value = payload.rows
    selectedRow.value =
      payload.rows.find(
        (item) => item.date === date && item.symbol === row.symbol && item.status === 'limit_up',
      ) ??
      payload.rows.find((item) => item.date === date && item.symbol === row.symbol) ??
      null
    if (!selectedRow.value) {
      drawerMessage.value = `${date} 的涨停明细中没有找到 ${row.symbol} ${row.name}。`
    }
  }

  async function selectStockFromDetail(row: LimitUpReviewRow) {
    selectedRow.value = row
    await nextTick()
    drawer.value?.focusPanel()
  }

  function saveNote(value: string) {
    if (noteKey.value) notes[noteKey.value] = value
  }

  async function loadRouteState() {
    requestController?.abort()
    closeDrawer()
    const current = new AbortController()
    requestController = current
    const sequence = ++requestSequence
    context.value = null
    overview.value = null
    contextFailure.value = null
    overviewFailure.value = null
    localDateError.value = ''

    if (explicitInvalidDate.value) {
      localDateError.value = '日期参数必须是有效的 YYYY-MM-DD。'
      loading.value = false
      return
    }

    loading.value = true
    const requested = routeDate(rawDateQuery.value)
    const contextResult = await callApi(
      (signal) =>
        api.GET('/api/v1/market/review/context', {
          params: { query: requested ? { date: requested } : {} },
          signal,
        }),
      { access: 'read', signal: current.signal },
    )
    if (requestController !== current || sequence !== requestSequence) return
    if (!contextResult.ok) {
      if (contextResult.failure.kind !== 'aborted') contextFailure.value = contextResult.failure
      loading.value = false
      return
    }

    context.value = contextResult.data
    if (!requested && contextResult.data.default_date) {
      await router.replace({
        path: route.path,
        query: {
          ...route.query,
          date: contextResult.data.default_date,
          window: String(selectedWindow.value),
        },
      })
      return
    }
    if (requested && contextResult.data.requested_date_known !== true) {
      loading.value = false
      return
    }

    const effectiveDate = requested ?? contextResult.data.default_date
    if (!effectiveDate) {
      loading.value = false
      return
    }
    const overviewResult = await callApi(
      (signal) =>
        api.GET('/api/v1/market/review/overview', {
          params: { query: { date: effectiveDate, window: selectedWindow.value } },
          signal,
        }),
      { access: 'read', signal: current.signal },
    )
    if (requestController !== current || sequence !== requestSequence) return
    loading.value = false
    if (overviewResult.ok) overview.value = overviewResult.data
    else if (overviewResult.failure.kind !== 'aborted')
      overviewFailure.value = overviewResult.failure
  }

  watch(() => [route.query.date, route.query.window, reloadKey.value] as const, loadRouteState, {
    immediate: true,
  })

  onBeforeUnmount(() => {
    requestController?.abort()
    drawerController?.abort()
    drawerSequence += 1
  })

  return {
    context,
    overview,
    contextFailure,
    overviewFailure,
    localDateError,
    loading,
    reloadKey,
    drawerOpen,
    drawerLoading,
    drawerFailure,
    drawerMessage,
    selectedLeader,
    selectedRow,
    peerRows,
    drawer,
    notes,
    maximumWindow,
    windowOptions,
    selectedWindow,
    selectedDate,
    history,
    showInitialLoading,
    drawerTitle,
    drawerMeta,
    noteKey,
    failureText,
    chooseDate,
    chooseWindow,
    goDate,
    resetToLatest,
    closeDrawer,
    openLeader,
    selectStockFromDetail,
    saveNote,
  }
}
