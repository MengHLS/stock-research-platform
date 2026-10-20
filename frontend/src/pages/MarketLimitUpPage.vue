<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon'
import LimitUpCalendarPanel from '../components/market/LimitUpCalendarPanel.vue'
import LimitUpReviewPanel from '../components/market/LimitUpReviewPanel.vue'
import MarketReviewControls from '../components/market/MarketReviewControls.vue'
import ReviewDrawer from '../components/market/ReviewDrawer.vue'
import StockDetailContent from '../components/market/StockDetailContent.vue'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import { buildMonthCalendar, clampMonth, shiftMonth } from '../market/limit-up'
import {
  routeDate,
  type LimitUpReviewRow,
  type ReviewContext,
  type ReviewDates,
  type ReviewLimitUp,
} from '../market/review'

const route = useRoute()
const router = useRouter()

const context = ref<ReviewContext | null>(null)
const detail = ref<ReviewLimitUp | null>(null)
const dates = ref<ReviewDates | null>(null)
const contextFailure = ref<ApiFailure | null>(null)
const detailFailure = ref<ApiFailure | null>(null)
const datesFailure = ref<ApiFailure | null>(null)
const localDateError = ref('')
const loading = ref(false)
const loadingCalendar = ref(false)
const reloadKey = ref(0)
const calendarMonth = ref('')
const selectedRow = ref<LimitUpReviewRow | null>(null)
const drawer = ref<InstanceType<typeof ReviewDrawer> | null>(null)
const notes = reactive<Record<string, string>>({})

let routeController: AbortController | null = null
let calendarController: AbortController | null = null
let routeSequence = 0
let calendarSequence = 0

const detailWindow = 1
const rawDateQuery = computed(() => route.query.date)
const explicitInvalidDate = computed(
  () =>
    rawDateQuery.value !== undefined &&
    (typeof rawDateQuery.value !== 'string' || !routeDate(rawDateQuery.value)),
)
const selectedDate = computed(
  () =>
    routeDate(rawDateQuery.value) ??
    context.value?.requested_date ??
    context.value?.default_date ??
    '',
)
const selectedDay = computed(
  () => detail.value?.days.find((day) => day.date === selectedDate.value) ?? null,
)
const showInitialLoading = computed(
  () => loading.value && !context.value && !contextFailure.value && !localDateError.value,
)
const calendarModel = computed(() =>
  buildMonthCalendar(
    calendarMonth.value || selectedDate.value.slice(0, 7),
    dates.value?.dates ?? [],
  ),
)
const reviewIssues = computed(() => {
  const seen = new Set<string>()
  return [...(dates.value?.issues ?? []), ...(detail.value?.issues ?? [])].filter((issue) => {
    const key = `${issue.code}|${issue.scope}|${issue.message}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
const minimumMonth = computed(() => context.value?.calendar_start?.slice(0, 7) ?? '')
const maximumMonth = computed(() => context.value?.calendar_end?.slice(0, 7) ?? '')
const previousMonth = computed(() => {
  if (!calendarMonth.value || !minimumMonth.value || calendarMonth.value <= minimumMonth.value) {
    return null
  }
  return shiftMonth(calendarMonth.value, -1)
})
const nextMonth = computed(() => {
  if (!calendarMonth.value || !maximumMonth.value || calendarMonth.value >= maximumMonth.value) {
    return null
  }
  return shiftMonth(calendarMonth.value, 1)
})
const noteKey = computed(() =>
  selectedRow.value
    ? `${selectedRow.value.date}|${selectedRow.value.symbol}|${selectedRow.value.status}`
    : '',
)

function failureText(failure: ApiFailure): string {
  if (isAuthNotConfigured(failure)) return '登录服务尚未启用，无法读取历史复盘数据。'
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
  updateQuery({ date: value })
}

function goDate(value: string | null | undefined) {
  if (value) updateQuery({ date: value })
}

function resetToLatest() {
  if (context.value?.default_date) goDate(context.value.default_date)
  else updateQuery({ date: undefined })
}

async function loadCalendar(month: string) {
  calendarController?.abort()
  const current = new AbortController()
  calendarController = current
  const sequence = ++calendarSequence
  datesFailure.value = null
  if (!context.value) return
  const minimum = context.value.calendar_start
  const maximum = context.value.calendar_end
  if (!minimum || !maximum) {
    dates.value = null
    loadingCalendar.value = false
    return
  }
  const targetMonth = clampMonth(month, minimum, maximum)
  calendarMonth.value = targetMonth
  const monthStart = `${targetMonth}-01`
  const lastDay = new Date(
    Date.UTC(Number(targetMonth.slice(0, 4)), Number(targetMonth.slice(5, 7)), 0),
  )
    .toISOString()
    .slice(0, 10)
  const start = monthStart < minimum ? minimum : monthStart
  const end = lastDay > maximum ? maximum : lastDay
  if (start > end) {
    dates.value = null
    loadingCalendar.value = false
    return
  }
  loadingCalendar.value = true
  const result = await callApi(
    (signal) =>
      api.GET('/api/v1/market/review/dates', {
        params: { query: { start, end } },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (calendarController !== current || sequence !== calendarSequence) return
  loadingCalendar.value = false
  if (result.ok) dates.value = result.data
  else if (result.failure.kind !== 'aborted') datesFailure.value = result.failure
}

async function loadRouteState() {
  routeController?.abort()
  calendarController?.abort()
  const current = new AbortController()
  routeController = current
  const sequence = ++routeSequence
  calendarSequence += 1
  loading.value = true
  loadingCalendar.value = false
  localDateError.value = ''
  contextFailure.value = null
  detailFailure.value = null
  datesFailure.value = null
  detail.value = null
  selectedRow.value = null
  const requestedDate = routeDate(rawDateQuery.value)
  const requestedMonth = requestedDate?.slice(0, 7) ?? ''
  if (explicitInvalidDate.value) {
    context.value = null
  } else if (requestedDate) {
    if (calendarMonth.value !== requestedMonth) {
      calendarMonth.value = requestedMonth
      dates.value = null
    }
  }

  if (explicitInvalidDate.value) {
    localDateError.value = '日期参数必须是有效的 YYYY-MM-DD。'
  }

  const requested = requestedDate
  const contextResult = await callApi(
    (signal) =>
      api.GET('/api/v1/market/review/context', {
        params: { query: requested ? { date: requested } : {} },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (routeController !== current || sequence !== routeSequence) return
  if (!contextResult.ok) {
    loading.value = false
    if (contextResult.failure.kind !== 'aborted') {
      context.value = null
      contextFailure.value = contextResult.failure
    }
    return
  }
  context.value = contextResult.data
  if (explicitInvalidDate.value) {
    loading.value = false
    return
  }
  if (!requested && contextResult.data.default_date) {
    loading.value = false
    await router.replace({
      path: route.path,
      query: { ...route.query, date: contextResult.data.default_date },
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

  const targetMonth = effectiveDate.slice(0, 7)
  if (!calendarMonth.value || calendarMonth.value !== targetMonth) {
    calendarMonth.value = targetMonth
  }
  void loadCalendar(targetMonth)

  const detailResult = await callApi(
    (signal) =>
      api.GET('/api/v1/market/review/limit-up', {
        params: { query: { date: effectiveDate, window: detailWindow } },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (routeController !== current || sequence !== routeSequence) return
  loading.value = false
  if (detailResult.ok) detail.value = detailResult.data
  else if (detailResult.failure.kind !== 'aborted') detailFailure.value = detailResult.failure
}

async function selectRow(row: LimitUpReviewRow) {
  selectedRow.value = row
  await nextTick()
  drawer.value?.focusPanel()
}

function saveNote(value: string) {
  if (noteKey.value) notes[noteKey.value] = value
}

function closeDrawer() {
  selectedRow.value = null
}

watch(() => [route.query.date, reloadKey.value] as const, loadRouteState, { immediate: true })

onBeforeUnmount(() => {
  routeController?.abort()
  calendarController?.abort()
})
</script>

<template>
  <div class="limit-page">
    <section v-if="localDateError" class="banner banner--warn" role="alert">
      {{ localDateError }}
      <button type="button" class="banner-button" @click="resetToLatest">查看最近有记录日</button>
    </section>
    <section v-else-if="contextFailure" class="banner banner--error" role="alert">
      <strong>{{ failureText(contextFailure) }}</strong>
      <span v-if="contextFailure.requestId">请求编号 {{ contextFailure.requestId }}</span>
      <button type="button" class="banner-button" @click="reloadKey += 1">重试</button>
    </section>
    <section
      v-else-if="context && context.requested_date_known === false"
      class="banner banner--warn"
      role="alert"
    >
      {{ context.requested_date }} 未被交易日数据收录；页面没有自动替换成其他日期。
      <button
        v-if="context.default_date"
        type="button"
        class="banner-button"
        @click="resetToLatest"
      >
        查看 {{ context.default_date }}
      </button>
    </section>
    <section v-else-if="context && !context.default_date" class="banner banner--info">
      暂无可用的历史复盘日期。
    </section>

    <div v-if="showInitialLoading" class="loading-panel">
      <div class="loading-mark" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <span>正在读取 {{ selectedDate || '最近交易日' }} 的涨跌停复盘数据…</span>
    </div>

    <template
      v-if="context && selectedDate && !localDateError && context.requested_date_known !== false"
    >
      <LimitUpCalendarPanel
        v-if="calendarMonth"
        :model="calendarModel"
        :selected-date="selectedDate"
        :loading="loading || loadingCalendar"
        :failure="datesFailure ? failureText(datesFailure) : null"
        :previous-month="previousMonth"
        :next-month="nextMonth"
        @month="loadCalendar"
        @select="chooseDate"
      >
        <template #date-controls>
          <MarketReviewControls
            :context="context"
            :value="selectedDate"
            :window-value="detailWindow"
            :window-options="[detailWindow]"
            :loading="loading"
            :show-window="false"
            @date="chooseDate"
            @previous="goDate(context?.previous_trading_day)"
            @next="goDate(context?.next_trading_day)"
            @latest="resetToLatest"
            @reload="reloadKey += 1"
          />
        </template>
      </LimitUpCalendarPanel>

      <LimitUpReviewPanel
        :rows="detail?.rows ?? []"
        :selected-date="selectedDate"
        :selected-day="selectedDay"
        :loading="loading"
        :failure="detailFailure ? failureText(detailFailure) : null"
        :request-id="detailFailure?.requestId"
        @select="selectRow"
        @retry="reloadKey += 1"
        @reset-date="resetToLatest"
      />

      <details v-if="reviewIssues.length" class="issues">
        <summary>
          <AppIcon name="alert-triangle" :size="14" />
          {{ reviewIssues.length }} 条数据口径与缺失提示
        </summary>
        <ul>
          <li v-for="issue in reviewIssues" :key="`${issue.code}-${issue.scope}-${issue.message}`">
            <span v-if="/^\d{4}-\d{2}-\d{2}$/.test(issue.scope ?? '')">
              涉及日期 {{ issue.scope }} ·
            </span>
            {{ issue.message }}
          </li>
        </ul>
      </details>
    </template>

    <ReviewDrawer
      ref="drawer"
      :open="selectedRow !== null"
      :title="selectedRow?.name ?? '复盘记录'"
      :meta="
        selectedRow ? `${selectedRow.symbol} · ${selectedRow.sector} · ${selectedRow.date}` : ''
      "
      variant="modal"
      modal-size="detail"
      @close="closeDrawer"
    >
      <StockDetailContent
        v-if="selectedRow"
        :row="selectedRow"
        :peer-rows="detail?.rows ?? []"
        :window-max="context?.window_max"
        :note="notes[noteKey] ?? ''"
        @select="selectRow"
        @save-note="saveNote"
      />
    </ReviewDrawer>
  </div>
</template>

<style scoped>
.limit-page {
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.banner {
  padding: 11px 14px;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  font-size: 13px;
}

.banner--warn {
  border: 1px solid color-mix(in oklab, var(--warn) 36%, var(--border));
  background: color-mix(in oklab, var(--warn) 9%, transparent);
  color: var(--warn);
}

.banner--error {
  border: 1px solid color-mix(in oklab, var(--up) 36%, var(--border));
  background: color-mix(in oklab, var(--up) 9%, transparent);
  color: var(--up);
}

.banner--info {
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--fg2);
}

.banner span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 11px;
}

.banner-button {
  min-height: 32px;
  margin-left: auto;
  padding: 2px 8px;
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  background: transparent;
  color: inherit;
  font-size: 11.5px;
  cursor: pointer;
}

.loading-panel {
  min-height: 180px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  color: var(--muted);
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  font-size: 13px;
}

.loading-mark {
  display: flex;
  gap: 4px;
}

.loading-mark i {
  width: 18px;
  height: 4px;
  border-radius: 999px;
  background: var(--brand);
  animation: pulse 900ms ease-in-out infinite alternate;
}

.loading-mark i:nth-child(2) {
  animation-delay: 120ms;
}

.loading-mark i:nth-child(3) {
  animation-delay: 240ms;
}

@keyframes pulse {
  from {
    opacity: 0.24;
    transform: scaleX(0.6);
  }
  to {
    opacity: 1;
    transform: scaleX(1);
  }
}

.issues {
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--muted);
  font-size: 12px;
}

.issues summary {
  width: fit-content;
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}

.issues ul {
  margin: 8px 0 0;
  padding-left: 20px;
  display: grid;
  gap: 5px;
}

.issues li {
  color: var(--fg2);
  line-height: 1.55;
}

@media (max-width: 760px) {
  .limit-page {
    gap: 13px;
  }
}

@media (min-width: 2200px) {
  .limit-page {
    gap: 20px;
  }
}
</style>
