<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import AppIcon from '../AppIcon'
import type { LimitUpReviewDay, LimitUpReviewRow } from '../../market/review'
import { compareClass, formatSignedPercent } from '../../market/review'
import {
  buildLimitUpCsv,
  defaultLimitUpFilters,
  filterLimitUpRows,
  limitUpBoardLabel,
  limitUpEmptyTitle,
  limitUpSealLabel,
  limitUpSectorOptions,
  limitUpStatusLabel,
  paginateRows,
  sortLimitUpRows,
  type LimitUpSortKey,
} from '../../market/limit-up'

const props = defineProps<{
  rows: LimitUpReviewRow[]
  selectedDate: string
  selectedDay: LimitUpReviewDay | null
  loading: boolean
  failure: string | null
  requestId?: string | null
}>()
const emit = defineEmits<{
  select: [row: LimitUpReviewRow]
  retry: []
  resetDate: []
}>()

const filters = reactive(defaultLimitUpFilters())
const page = ref(1)
const pageSize = 100
const sortKey = ref<LimitUpSortKey>('boards')
const sortDirection = ref<'asc' | 'desc'>('desc')

const sectors = computed(() => limitUpSectorOptions(props.rows, props.selectedDate, 8))
const filtered = computed(() =>
  sortLimitUpRows(filterLimitUpRows(props.rows, props.selectedDate, filters), {
    key: sortKey.value,
    direction: sortDirection.value,
  }),
)
const paged = computed(() => paginateRows(filtered.value, page.value, pageSize))
const hasFilters = computed(
  () =>
    Boolean(filters.query.trim()) ||
    filters.tier !== 'all' ||
    filters.status !== 'limit_up' ||
    filters.sector !== null,
)
const dayMissing = computed(
  () => props.selectedDay?.assessment === 'missing' && props.selectedDay.total_limit_up === null,
)
const sourceHint = computed(() => {
  if (props.loading && !props.selectedDay) return '正在读取当日涨停与断板统计…'
  if (!props.selectedDay) return '等待交易日统计…'
  if (props.selectedDay.assessment === 'missing') return '该日涨停记录缺失'
  if (props.selectedDay.assessment === 'partial') return '部分板数或断板状态无法确认'
  return `原始涨停 ${props.selectedDay.total_limit_up ?? '—'} · 断板 ${props.selectedDay.broken_count ?? '—'} · 默认展示涨停`
})
const heading = computed(() => `${props.selectedDate} 涨停 / 断板明细`)

watch(
  () => [props.selectedDate, props.rows],
  () => {
    page.value = 1
  },
)

watch(
  () => [
    filters.query,
    filters.tier,
    filters.status,
    filters.sector,
    sortKey.value,
    sortDirection.value,
  ],
  () => {
    page.value = 1
  },
)

function toggleSort(key: LimitUpSortKey) {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }
  sortKey.value = key
  sortDirection.value = key === 'date' || key === 'boards' ? 'desc' : 'asc'
}

function ariaSort(key: LimitUpSortKey) {
  if (sortKey.value !== key) return 'none'
  return sortDirection.value === 'asc' ? 'ascending' : 'descending'
}

function sortArrow(key: LimitUpSortKey) {
  if (sortKey.value !== key) return ''
  return sortDirection.value === 'asc' ? '▲' : '▼'
}

function selectRow(row: LimitUpReviewRow, event: MouseEvent) {
  const target = event.target as Element | null
  if (
    target?.closest(
      'button, a, input, textarea, select, label, summary, [role="button"], [role="link"], [contenteditable]:not([contenteditable="false"]), [data-row-action]',
    )
  ) {
    return
  }
  // Give the shared dialog a stable focus target to restore when it closes.
  ;(event.currentTarget as HTMLElement).focus({ preventScroll: true })
  emit('select', row)
}

function selectRowByKeyboard(row: LimitUpReviewRow, event: KeyboardEvent) {
  if (event.target !== event.currentTarget || (event.key !== 'Enter' && event.key !== ' ')) return
  event.preventDefault()
  if (!event.repeat) emit('select', row)
}

function resetFilters() {
  Object.assign(filters, defaultLimitUpFilters())
}

function exportCsv() {
  if (!filtered.value.length) return
  const blob = new Blob([`\uFEFF${buildLimitUpCsv(filtered.value)}`], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `limit_up_${props.selectedDate}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
  <section class="panel review-panel" :aria-busy="loading">
    <header class="panel-head">
      <div class="heading-copy">
        <h2>{{ heading }}</h2>
        <p>{{ sourceHint }} · 封单额与换手率暂无数据</p>
      </div>
      <button type="button" class="tool-button" :disabled="!filtered.length" @click="exportCsv">
        <AppIcon name="download" :size="13" />
        导出 CSV
      </button>
    </header>

    <div v-if="!failure && (!loading || rows.length)" class="filters">
      <label class="search">
        <AppIcon name="search" :size="15" />
        <input
          v-model="filters.query"
          placeholder="搜索代码 / 名称 / 题材"
          aria-label="搜索涨停记录"
        />
      </label>
      <span class="filter-label">板数</span>
      <div class="filter-group" role="group" aria-label="板数筛选">
        <button
          type="button"
          :class="{ active: filters.tier === 'all' }"
          :aria-pressed="filters.tier === 'all'"
          @click="filters.tier = 'all'"
        >
          全部
        </button>
        <button
          type="button"
          :class="{ active: filters.tier === 'first' }"
          :aria-pressed="filters.tier === 'first'"
          @click="filters.tier = filters.tier === 'first' ? 'all' : 'first'"
        >
          首板
        </button>
        <button
          type="button"
          :class="{ active: filters.tier === 'connection' }"
          :aria-pressed="filters.tier === 'connection'"
          @click="filters.tier = filters.tier === 'connection' ? 'all' : 'connection'"
        >
          连板
        </button>
        <button
          type="button"
          :class="{ active: filters.tier === 'high' }"
          :aria-pressed="filters.tier === 'high'"
          @click="filters.tier = filters.tier === 'high' ? 'all' : 'high'"
        >
          4 板+
        </button>
      </div>
      <span class="filter-label">状态</span>
      <div class="filter-group" role="group" aria-label="状态筛选">
        <button
          type="button"
          :class="{ active: filters.status === 'limit_up' }"
          :aria-pressed="filters.status === 'limit_up'"
          @click="filters.status = 'limit_up'"
        >
          涨停
        </button>
        <button
          type="button"
          :class="{ active: filters.status === 'broken' }"
          :aria-pressed="filters.status === 'broken'"
          @click="filters.status = 'broken'"
        >
          断板
        </button>
        <button
          type="button"
          :class="{ active: filters.status === 'all' }"
          :aria-pressed="filters.status === 'all'"
          @click="filters.status = 'all'"
        >
          全部
        </button>
      </div>
      <span class="filter-divider" aria-hidden="true" />
      <span class="filter-label">题材</span>
      <button
        v-for="sector in sectors"
        :key="sector"
        type="button"
        class="filter-chip"
        :class="{ active: filters.sector === sector, unknown: sector === '未知' }"
        :aria-pressed="filters.sector === sector"
        @click="filters.sector = filters.sector === sector ? null : sector"
      >
        {{ sector }}
      </button>
      <button v-if="hasFilters" type="button" class="reset" @click="resetFilters">清除筛选</button>
    </div>

    <div v-if="!failure && (!loading || rows.length)" class="result-meta">
      <span>
        当前 <b>{{ filtered.length }}</b> / {{ rows.length }} 条 · 断板默认隐藏
      </span>
      <span class="scroll-hint">窄屏可横向滚动表格查看全部列</span>
    </div>

    <div v-if="failure" class="state state--error" role="alert">
      <AppIcon name="alert-triangle" :size="22" />
      <b>明细读取失败</b>
      <span>{{ failure }}</span>
      <small v-if="requestId">请求编号 {{ requestId }}</small>
      <button type="button" class="tool-button" @click="emit('retry')">重试</button>
    </div>
    <div v-else-if="loading && !rows.length" class="state state--loading">
      <span class="loading-ring" aria-hidden="true" />
      <span>正在读取 {{ selectedDate }} 的涨停与断板记录…</span>
    </div>
    <div v-else-if="!filtered.length" class="state">
      <AppIcon name="search" :size="22" />
      <b>
        {{ limitUpEmptyTitle(selectedDay, filters) }}
      </b>
      <span v-if="dayMissing"> 缺失不等于 0 家涨停；切换日期或查看其他交易日。 </span>
      <span v-else-if="filters.status === 'broken'">
        断板仅表示前一日在榜、当日未续；可切换到“涨停”查看当日涨停记录。
      </span>
      <span v-else>调整关键词、板数、断板或题材筛选。</span>
      <button v-if="dayMissing" type="button" class="tool-button" @click="emit('resetDate')">
        回到最近有记录日
      </button>
      <button v-else-if="hasFilters" type="button" class="tool-button" @click="resetFilters">
        清除筛选
      </button>
    </div>

    <template v-else>
      <div class="table-wrap">
        <table class="detail-table">
          <colgroup>
            <col class="col-code" />
            <col class="col-name" />
            <col class="col-sector" />
            <col class="col-boards" />
            <col class="col-seal" />
            <col class="col-change" />
            <col class="col-status" />
            <col class="col-action" />
          </colgroup>
          <thead>
            <tr>
              <th :aria-sort="ariaSort('symbol')">
                <button type="button" @click="toggleSort('symbol')">
                  代码 <span>{{ sortArrow('symbol') }}</span>
                </button>
              </th>
              <th :aria-sort="ariaSort('name')">
                <button type="button" @click="toggleSort('name')">
                  名称 <span>{{ sortArrow('name') }}</span>
                </button>
              </th>
              <th :aria-sort="ariaSort('sector')">
                <button type="button" @click="toggleSort('sector')">
                  题材 <span>{{ sortArrow('sector') }}</span>
                </button>
              </th>
              <th class="align-right" :aria-sort="ariaSort('boards')">
                <button type="button" @click="toggleSort('boards')">
                  板数 <span>{{ sortArrow('boards') }}</span>
                </button>
              </th>
              <th :aria-sort="ariaSort('limit_up_time')">
                <button type="button" @click="toggleSort('limit_up_time')">
                  首封 / 一字 <span>{{ sortArrow('limit_up_time') }}</span>
                </button>
              </th>
              <th class="align-right" :aria-sort="ariaSort('change_pct')">
                <button type="button" @click="toggleSort('change_pct')">
                  涨跌幅 <span>{{ sortArrow('change_pct') }}</span>
                </button>
              </th>
              <th :aria-sort="ariaSort('status')">
                <button type="button" @click="toggleSort('status')">
                  状态 <span>{{ sortArrow('status') }}</span>
                </button>
              </th>
              <th class="align-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in paged.items"
              :key="`${row.date}-${row.symbol}-${row.status}`"
              class="detail-row"
              tabindex="0"
              :aria-label="`查看 ${row.name} ${row.symbol} ${row.date} ${limitUpStatusLabel(row)}详情`"
              aria-haspopup="dialog"
              @click="selectRow(row, $event)"
              @keydown="selectRowByKeyboard(row, $event)"
            >
              <td class="mono">{{ row.symbol }}</td>
              <td class="name-cell">
                {{ row.name }}
                <span v-if="row.one_word_board && row.status === 'limit_up'" class="tag tag--hot">
                  一字
                </span>
              </td>
              <td>
                <span class="sector-tag">{{ row.sector }}</span>
              </td>
              <td class="align-right mono">
                {{ limitUpBoardLabel(row) }}
                <small v-if="row.boards_as_of_date !== row.date">
                  截至 {{ row.boards_as_of_date.slice(5) }}
                </small>
              </td>
              <td class="mono">{{ limitUpSealLabel(row) }}</td>
              <td class="align-right mono" :class="compareClass(row.change_pct)">
                {{ formatSignedPercent(row.change_pct) }}
              </td>
              <td>
                <span
                  class="status"
                  :class="row.status === 'broken' ? 'status--broken' : 'status--up'"
                >
                  {{ limitUpStatusLabel(row) }}
                </span>
              </td>
              <td class="align-right">
                <button type="button" class="row-button" @click.stop="emit('select', row)">
                  详情
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer class="pager">
        <span>
          {{ paged.start }}–{{ paged.end }} / {{ paged.total }} 条 · 第 {{ paged.page }} /
          {{ paged.pageCount }} 页
        </span>
        <div>
          <button
            type="button"
            :disabled="paged.page <= 1"
            aria-label="上一页"
            @click="page = paged.page - 1"
          >
            <AppIcon name="chevron-left" :size="14" />
          </button>
          <button
            type="button"
            :disabled="paged.page >= paged.pageCount"
            aria-label="下一页"
            @click="page = paged.page + 1"
          >
            <AppIcon name="chevron-right" :size="14" />
          </button>
        </div>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.panel-head {
  min-height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in oklab, var(--surface) 96%, var(--fg) 4%);
}

.heading-copy {
  min-width: 220px;
  flex: 1 1 360px;
}

.panel-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 680;
}

.panel-head p {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 12.5px;
}

.tool-button,
.row-button,
.reset {
  min-height: 34px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-size: 12.5px;
  cursor: pointer;
}

.tool-button:hover:not(:disabled),
.row-button:hover,
.reset:hover {
  border-color: var(--border2);
  background: var(--surface3);
  color: var(--fg);
}

.tool-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.filters {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border);
}

.search {
  min-width: 230px;
  flex: 1 1 290px;
  height: 38px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--muted);
}

.search:focus-within {
  border-color: var(--accent);
}

.search input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13px;
}

.filter-group {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.filter-label {
  color: var(--muted);
  font-size: 11.5px;
  white-space: nowrap;
}

.filter-group button,
.filter-chip {
  min-height: 34px;
  padding: 4px 11px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}

.filter-group button {
  border: 0;
  border-left: 1px solid var(--border);
  border-radius: 0;
}

.filter-group button:first-child {
  border-left: 0;
}

.filter-group button.active,
.filter-chip.active {
  border-color: color-mix(in oklab, var(--brand) 42%, var(--border));
  background: color-mix(in oklab, var(--brand) 14%, var(--surface2));
  color: var(--brand);
}

.filter-chip {
  border-radius: var(--radius-sm);
}

.filter-chip.unknown {
  border-style: dashed;
}

.filter-divider {
  width: 1px;
  height: 20px;
  background: var(--border);
}

.reset {
  margin-left: auto;
  border-color: transparent;
  background: transparent;
  color: var(--muted);
}

.result-meta {
  min-height: 40px;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px 14px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
}

.result-meta b {
  color: var(--fg2);
  font-family: var(--mono);
}

.result-meta .warning {
  color: var(--warn);
}

.scroll-hint {
  display: none;
}

.table-wrap {
  width: 100%;
  max-height: 64vh;
  overflow: auto;
  scrollbar-gutter: stable;
}

.detail-table {
  width: 100%;
  min-width: 1150px;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
}

.col-code {
  width: 130px;
}

.col-name {
  width: 210px;
}

.col-sector {
  width: 170px;
}

.col-boards {
  width: 140px;
}

.col-seal {
  width: 160px;
}

.col-change {
  width: 120px;
}

.col-status {
  width: 130px;
}

.col-action {
  width: 90px;
}

.detail-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  height: 40px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border);
  background: var(--surface2);
  color: var(--muted);
  font-size: 12px;
  font-weight: 550;
  text-align: left;
  white-space: nowrap;
}

.detail-table th button {
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: inherit;
  text-align: inherit;
  cursor: pointer;
}

.detail-table th.align-right button {
  justify-content: flex-end;
}

.detail-table th span {
  color: var(--brand);
  font-size: 9.5px;
}

.detail-table td {
  height: 46px;
  padding: 8px 10px;
  border-bottom: 1px solid color-mix(in oklab, var(--border) 74%, transparent);
  color: var(--fg2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-row {
  cursor: pointer;
}

.detail-row:hover td,
.detail-row:focus-visible td {
  background: color-mix(in oklab, var(--surface2) 72%, transparent);
}

.detail-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.detail-table td small {
  display: block;
  color: var(--muted);
  font-size: 11px;
}

.align-right {
  text-align: right !important;
}

.mono {
  font-family: var(--mono);
}

.name-cell {
  color: var(--fg) !important;
  font-weight: 620;
}

.tag,
.sector-tag,
.status {
  display: inline-flex;
  align-items: center;
  min-height: 23px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
  white-space: nowrap;
}

.tag {
  margin-left: 5px;
}

.tag--hot {
  background: color-mix(in oklab, var(--up) 16%, transparent);
  color: var(--up);
}

.sector-tag {
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--fg2);
}

.status--up {
  background: color-mix(in oklab, var(--up) 13%, transparent);
  color: var(--up);
}

.status--broken {
  background: color-mix(in oklab, var(--warn) 13%, transparent);
  color: var(--warn);
}

.row-button {
  min-height: 30px;
  padding: 3px 9px;
}

.pager {
  min-height: 50px;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
}

.pager div {
  display: flex;
  gap: 5px;
}

.pager button {
  width: 36px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  cursor: pointer;
}

.pager button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.state {
  min-height: 260px;
  padding: 28px 18px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 7px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}

.state b {
  color: var(--fg2);
  font-size: 15px;
}

.state small {
  font-family: var(--mono);
}

.state--error {
  color: var(--up);
}

.state--loading {
  min-height: 180px;
}

.loading-ring {
  width: 22px;
  height: 22px;
  border: 2px solid color-mix(in oklab, var(--brand) 24%, transparent);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: loading-spin 720ms linear infinite;
}

@keyframes loading-spin {
  to {
    transform: rotate(360deg);
  }
}

.up {
  color: var(--up);
}

.down {
  color: var(--down);
}

.flat {
  color: var(--flat);
}

@media (max-width: 760px) {
  .panel-head {
    align-items: flex-start;
  }

  .heading-copy {
    flex-basis: 100%;
  }

  .head-actions {
    width: 100%;
  }

  .filters {
    padding-inline: 12px;
  }

  .search {
    flex-basis: 100%;
    height: 44px;
  }

  .table-wrap {
    max-height: none;
  }

  .tool-button,
  .filter-group button,
  .filter-chip {
    min-height: 44px;
  }

  .row-button {
    min-height: 44px;
    padding-inline: 12px;
  }

  .pager button {
    width: 44px;
    height: 44px;
  }
}

@media (max-width: 1400px) {
  .scroll-hint {
    display: inline;
    color: var(--muted);
  }
}

@media (min-width: 2200px) {
  .table-wrap {
    max-height: 70vh;
  }

  .detail-table {
    min-width: 100%;
  }
}
</style>
