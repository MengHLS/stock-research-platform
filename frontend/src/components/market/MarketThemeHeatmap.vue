<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { ReviewHistoryRow } from '../../market/review'
import { buildHeatmap, heatCellKey, heatmapDatesNewestFirst } from '../../market/review'

const props = defineProps<{
  history: ReviewHistoryRow[]
}>()
const emit = defineEmits<{ select: [date: string, theme: string] }>()

const model = computed(() => buildHeatmap(props.history, 30, 8))
const dates = computed(() => heatmapDatesNewestFirst(model.value))
const focusedCell = ref<string | null>(null)
watch(model, () => {
  focusedCell.value = null
})

function countFor(date: string, theme: string) {
  return model.value.cells.get(heatCellKey(date, theme))?.count ?? null
}

function cellLevel(count: number | null) {
  return count === null
    ? undefined
    : count === 0
      ? 0
      : Math.max(1, Math.ceil((count / model.value.max) * 4))
}

function cellTabIndex(date: string, theme: string) {
  const firstCell = heatCellKey(dates.value[0] ?? '', model.value.themes[0] ?? '')
  return (focusedCell.value ?? firstCell) === heatCellKey(date, theme) ? 0 : -1
}

function moveCell(event: KeyboardEvent) {
  const moves: Record<string, [number, number]> = {
    ArrowLeft: [0, -1],
    ArrowRight: [0, 1],
    ArrowUp: [-1, 0],
    ArrowDown: [1, 0],
  }
  const move = moves[event.key]
  const target = event.target as HTMLElement
  if (!move || !target.matches('.cell')) return
  event.preventDefault()
  const row = Math.max(
    0,
    Math.min(model.value.themes.length - 1, Number(target.dataset.row) + move[0]),
  )
  const column = Math.max(
    0,
    Math.min(dates.value.length - 1, Number(target.dataset.column) + move[1]),
  )
  const next = (event.currentTarget as HTMLTableElement).querySelector<HTMLButtonElement>(
    `[data-row="${row}"][data-column="${column}"]`,
  )
  next?.focus({ preventScroll: true })
  next?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>题材热力日历</h2>
      <span class="sub">
        最近 {{ dates.length }} 个交易日 · 最新日期在左 · 展示前
        {{ model.themes.length }} 个活跃题材 · 点击查看同日同题材涨停
      </span>
      <span class="grow" />
    </header>

    <div class="panel-body">
      <div class="legend" aria-label="热力图图例">
        <span><i data-level="0" />0</span>
        <span><i data-level="1" />低</span>
        <span><i data-level="2" />中</span>
        <span><i data-level="3" />较高</span>
        <span><i data-level="4" />高</span>
        <span><i class="missing" />缺失</span>
      </div>
      <div v-if="model.themes.length" class="heat-wrap">
        <table class="heat" aria-label="题材涨停家数热力图" @keydown="moveCell">
          <colgroup>
            <col class="heat-topic" />
            <col v-for="date in dates" :key="`col-${date}`" />
            <col class="heat-total" />
          </colgroup>
          <thead>
            <tr>
              <th class="theme-head" scope="col">题材</th>
              <th v-for="date in dates" :key="date" scope="col">{{ date.slice(5) }}</th>
              <th class="total-head" scope="col">合计</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(theme, rowIndex) in model.themes"
              :key="theme"
              :class="{ 'unknown-row': theme === '未知' }"
            >
              <th class="theme-cell" scope="row">{{ theme }}</th>
              <td v-for="(date, columnIndex) in dates" :key="`${date}-${theme}`">
                <button
                  type="button"
                  class="cell"
                  :data-level="cellLevel(countFor(date, theme))"
                  :data-missing="countFor(date, theme) === null ? '1' : undefined"
                  :data-row="rowIndex"
                  :data-column="columnIndex"
                  :tabindex="cellTabIndex(date, theme)"
                  :aria-label="`${date} ${theme} ${countFor(date, theme) ?? '缺失'} 家`"
                  :title="`${date} ${theme}：${countFor(date, theme) ?? '缺失'} 家`"
                  @focus="focusedCell = heatCellKey(date, theme)"
                  @click="emit('select', date, theme)"
                >
                  {{ countFor(date, theme) === 0 ? '·' : (countFor(date, theme) ?? '—') }}
                </button>
              </td>
              <td class="total num">
                {{ model.hasMissingDays ? '≥' : '' }}{{ model.totals.get(theme) ?? 0 }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">当前窗口没有可用题材记录。</div>
      <p class="note">
        · 表示 0 家，即已读取记录中未出现该题材；斜纹 —
        表示该日涨停记录缺失。题材按最新日热度、区间总量排序，仅保留前 8
        个并保留未知分组；存在缺失日时，合计以 ≥ 表示已知下限。
      </p>
    </div>
  </section>
</template>

<style scoped>
.panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.panel-head h2 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 650;
}

.sub {
  color: var(--muted);
  font-size: 11.5px;
}

.grow {
  flex: 1 1 auto;
}

.panel-body {
  padding: 16px;
}

.legend {
  display: flex;
  align-items: center;
  gap: 8px 14px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  color: var(--muted);
  font-size: 10px;
  white-space: nowrap;
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.legend i {
  width: 16px;
  height: 10px;
  border-radius: 3px;
}

.heat-wrap {
  width: 100%;
  max-height: 520px;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}

.heat {
  width: 100%;
  min-width: 1320px;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 3px;
  font-size: 11px;
}

.heat-topic {
  width: clamp(144px, 14%, 220px);
}

.heat-total {
  width: 68px;
}

.heat th,
.heat td {
  padding: 0;
}

.heat thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  height: 28px;
  background: var(--surface);
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 500;
}

.theme-head,
.theme-cell {
  position: sticky;
  left: 0;
  z-index: 3;
  width: auto;
  min-width: 0;
  padding: 5px 10px !important;
  background: var(--surface);
  text-align: left;
  white-space: nowrap;
}

.unknown-row .theme-cell,
.unknown-row td {
  border-top: 1px solid var(--border2);
}

.heat thead .theme-head {
  z-index: 4;
  background: var(--surface);
}

.theme-cell {
  color: var(--fg2);
  font-size: 11px;
  font-weight: 550;
}

.heat td {
  width: auto;
  height: 37px;
  text-align: center;
}

.cell {
  width: calc(100% - 8px);
  height: 32px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--fg);
  font-family: var(--mono);
  font-size: 10.5px;
  cursor: pointer;
}

.cell:hover {
  outline: 1px solid var(--fg2);
  outline-offset: 1px;
}

[data-level='0'] {
  background: color-mix(in oklab, var(--surface2) 94%, var(--fg) 6%);
  color: var(--muted);
}

[data-level='1'] {
  background: color-mix(in oklab, var(--brand) 11%, var(--surface2));
}

[data-level='2'] {
  background: color-mix(in oklab, var(--brand) 24%, var(--surface2));
}

[data-level='3'] {
  background: color-mix(in oklab, var(--brand) 43%, var(--surface2));
}

[data-level='4'] {
  background: color-mix(in oklab, var(--brand) 64%, var(--surface2));
}

[data-missing='1'],
.legend .missing {
  background:
    repeating-linear-gradient(
      135deg,
      transparent 0 4px,
      color-mix(in oklab, var(--muted) 15%, transparent) 4px 5px
    ),
    var(--surface2);
  color: var(--muted);
}

.total,
.total-head {
  width: auto;
  min-width: 0;
  border-left: 1px solid var(--border);
  color: var(--fg2);
  font-family: var(--mono);
  text-align: center;
}

.empty {
  padding: 28px 12px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  text-align: center;
  color: var(--muted);
  font-size: 12px;
}

.note {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}

@media (max-width: 620px) {
  .panel-head {
    align-items: flex-start;
  }
}

@media (min-width: 2200px) {
  .heat {
    min-width: 100%;
  }

  .heat-wrap {
    max-height: none;
  }
}
</style>
