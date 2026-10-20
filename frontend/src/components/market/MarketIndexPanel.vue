<script setup lang="ts">
import { computed } from 'vue'

import MarketSparkline from './MarketSparkline.vue'
import type { components } from '../../api/schema'
import type { ReviewIndices } from '../../market/review'
import { chartNumber, compareClass, formatNumber, formatSignedPercent } from '../../market/review'

type OverviewIndex = components['schemas']['OverviewIndexRead']

const props = defineProps<{
  date: string
  items: OverviewIndex[]
  series: ReviewIndices | null
  loading: boolean
  failure: string | null
  requestId?: string | null
}>()
const emit = defineEmits<{ select: [symbol: string] }>()

const cards = computed(() =>
  props.items.map((item) => {
    const indexSeries =
      props.series?.indices.find((series) => series.symbol === item.symbol) ?? null
    const current = indexSeries?.bars.find((bar) => bar.date === props.date) ?? null
    const closes = (indexSeries?.bars ?? []).map((bar) => chartNumber(bar.close))
    return {
      ...item,
      ma5: current?.ma5 ?? null,
      ma20: current?.ma20 ?? null,
      closes,
      tone: compareClass(item.change_pct),
    }
  }),
)

const windowDays = computed(() => props.series?.window_actual ?? 0)
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>核心指数</h2>
      <span class="sub">
        截至 {{ date }} · {{ windowDays ? `近 ${windowDays} 个交易日` : '窗口数据待读取' }} · 收盘 +
        MA
      </span>
      <span class="grow" />
      <span v-if="loading" class="state">指数加载中…</span>
      <span v-else-if="failure" class="state state--error">
        {{ failure }}
        <span v-if="requestId">请求编号 {{ requestId }}</span>
      </span>
    </header>
    <div class="panel-body">
      <div v-if="cards.length" class="grid">
        <button
          v-for="item in cards"
          :key="item.symbol"
          type="button"
          class="index-card"
          :aria-label="`${item.name} 打开历史 K 线`"
          @click="emit('select', item.symbol)"
        >
          <span class="index-head">
            <b>{{ item.name }}</b>
            <code>{{ item.symbol }}</code>
          </span>
          <span class="index-value">
            <strong class="num" :class="item.tone">{{ formatNumber(item.close, 2) }}</strong>
            <span class="num" :class="compareClass(item.change_pct)">
              {{ formatSignedPercent(item.change_pct) }}
            </span>
          </span>
          <MarketSparkline
            v-if="item.closes.some((value) => Number.isFinite(value))"
            :values="item.closes"
            :height="46"
            :label="`${item.name}最近收盘走势`"
            :color="`var(--${item.tone})`"
          />
          <span v-else class="spark-empty">暂无趋势数据</span>
          <span class="index-foot">
            <span>MA5 {{ formatNumber(item.ma5, 2) }}</span>
            <span>MA20 {{ formatNumber(item.ma20, 2) }}</span>
            <span>截至 {{ date.slice(5) }} ›</span>
          </span>
        </button>
      </div>
      <div v-else-if="!loading" class="empty">该窗口没有可展示的指数日线。</div>
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

.state {
  color: var(--muted);
  font-size: 11px;
}

.state--error {
  color: var(--up);
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.index-card {
  min-width: 0;
  padding: 13px 14px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in oklab, var(--surface2) 90%, var(--surface));
  color: var(--fg);
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 3px;
  transition:
    border-color var(--duration),
    background var(--duration),
    transform var(--duration);
}

.index-card:hover {
  border-color: var(--border2);
  background: var(--surface3);
  transform: translateY(-1px);
}

.index-head,
.index-value,
.index-foot {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.index-head b {
  font-size: 12.5px;
}

.index-head code {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
}

.index-value {
  justify-content: flex-start;
  margin-top: 7px;
  margin-bottom: 5px;
}

.index-value strong {
  font-size: 22px;
}

.index-value span {
  font-size: 12px;
  font-weight: 650;
}

.index-foot {
  justify-content: flex-start;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 10px;
  margin-top: 5px;
}

.index-foot span:last-child {
  margin-left: auto;
  color: var(--accent);
}

.spark-empty {
  height: 42px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 10px;
}

.empty {
  min-height: 130px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  font-size: 12px;
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

@media (max-width: 1180px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
