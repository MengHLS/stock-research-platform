<script setup lang="ts">
import { computed, ref } from 'vue'

import MarketBreadthChart from './MarketBreadthChart.vue'
import type { ReviewHistoryRow } from '../../market/review'
import { formatNumber } from '../../market/review'

const props = defineProps<{
  history: ReviewHistoryRow[]
}>()

const rows = computed(() =>
  [...props.history].sort((left, right) => left.date.localeCompare(right.date)),
)
const localWindow = ref(120)
const windowOptions = computed(() => {
  const values = [30, 60, 120].filter((window) => window <= rows.value.length)
  if (rows.value.length && !values.includes(rows.value.length)) values.push(rows.value.length)
  return Array.from(new Set(values)).sort((left, right) => left - right)
})
const visibleRows = computed(() => rows.value.slice(-localWindow.value))
const latest = computed(() => visibleRows.value.at(-1) ?? null)
const hasData = computed(() =>
  visibleRows.value.some(
    (row) =>
      row.total_limit_up !== null ||
      row.turnover_100m_cny !== null ||
      row.margin_balance_100m_cny !== null,
  ),
)
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>市场量能结构</h2>
      <span class="sub">
        截至 {{ latest?.date ?? '—' }} ·
        {{ visibleRows.length ? `近 ${visibleRows.length} 个交易日` : '暂无交易日数据' }}
        <template v-if="rows.length > 0 && rows.length < 120"> · 历史不足120日</template>
      </span>
      <span class="grow" />
      <div v-if="windowOptions.length" class="windows" role="group" aria-label="量能图时间窗口">
        <button
          v-for="option in windowOptions"
          :key="option"
          type="button"
          :class="{ active: option === Math.min(localWindow, rows.length) }"
          :aria-pressed="option === Math.min(localWindow, rows.length)"
          @click="localWindow = option"
        >
          {{ option }}日
        </button>
      </div>
    </header>
    <div class="panel-body">
      <div v-if="latest" class="chips" aria-label="当前交易日量能摘要">
        <span>
          <i class="up-dot" />
          涨停 {{ latest.total_limit_up ?? '—' }} 家
        </span>
        <span>
          <i class="vol-dot" />
          成交额 {{ formatNumber(latest.turnover_100m_cny, 0) }} 亿
        </span>
        <span>
          <i class="margin-dot" />
          两融 {{ formatNumber(latest.margin_balance_100m_cny, 0) }} 亿
        </span>
      </div>
      <div v-if="hasData" class="chart-scroll">
        <MarketBreadthChart :rows="visibleRows" :selected-date="latest?.date ?? ''" />
      </div>
      <div v-else class="empty">该窗口没有可绘制的量能或涨停统计；缺失未按零绘制。</div>
      <p class="note">
        上=涨停家数柱，中=成交额线，下=两融余额线；三栏共用时间轴，缺失日期保持断点。
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

.windows {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
}

.windows button {
  border: 0;
  border-radius: 999px;
  padding: 4px 11px;
  background: transparent;
  color: var(--muted);
  font-size: 10.5px;
  cursor: pointer;
}

.windows button:hover {
  color: var(--fg);
}

.windows button.active {
  background: var(--surface);
  color: var(--fg);
  box-shadow: var(--shadow);
}

.panel-body {
  padding: 14px 16px 16px;
}

.chart-scroll {
  overflow-x: auto;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--fg2);
  font-size: 11px;
  margin-bottom: 10px;
}

.chips span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.chips i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.up-dot {
  background: var(--up);
}

.vol-dot {
  background: var(--vol);
}

.margin-dot {
  background: var(--margin);
}

.empty {
  min-height: 240px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  font-size: 12px;
}

.note {
  margin: 7px 0 0;
  color: var(--muted);
  font-size: 10.5px;
  line-height: 1.6;
}

@media (max-width: 760px) {
  .chips {
    flex-basis: 100%;
  }
}
</style>
