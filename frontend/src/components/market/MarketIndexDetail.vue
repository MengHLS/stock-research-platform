<script setup lang="ts">
import { computed } from 'vue'

import MarketIndexKline from './MarketIndexKline.vue'
import type { IndexSeries } from '../../market/review'
import {
  buildCandleData,
  compareClass,
  formatNumber,
  formatSignedPercent,
} from '../../market/review'

const props = defineProps<{
  series: IndexSeries
  date: string
}>()

const current = computed(
  () =>
    props.series.bars.find((bar) => bar.date === props.date) ?? props.series.bars.at(-1) ?? null,
)
const candleData = computed(() => buildCandleData(props.series.bars))
const hasCompleteBars = computed(() => candleData.value.some((values) => values !== null))
</script>

<template>
  <div class="detail">
    <div class="quote">
      <span class="name">{{ series.name }}</span>
      <strong class="num">{{ formatNumber(current?.close, 2) }}</strong>
      <span class="num" :class="compareClass(current?.change_pct)">
        {{ formatSignedPercent(current?.change_pct) }}
      </span>
    </div>
    <dl class="kv">
      <div>
        <dt>MA5</dt>
        <dd class="num">{{ formatNumber(current?.ma5, 2) }}</dd>
      </div>
      <div>
        <dt>MA20</dt>
        <dd class="num">{{ formatNumber(current?.ma20, 2) }}</dd>
      </div>
      <div>
        <dt>缺失日</dt>
        <dd class="num">{{ series.missing_days }}</dd>
      </div>
      <div>
        <dt>K 线覆盖</dt>
        <dd class="num">{{ series.coverage.row_count }}</dd>
      </div>
    </dl>
    <div v-if="hasCompleteBars" class="chart-scroll">
      <MarketIndexKline :bars="series.bars" :selected-date="date" />
    </div>
    <div v-else class="empty">该窗口没有完整的日 K 数据。</div>
    <p class="note">缺失交易日不补画；均线在样本不足时断开。</p>
  </div>
</template>

<style scoped>
.detail {
  display: grid;
  gap: 12px;
}

.chart-scroll {
  overflow-x: auto;
}

.quote {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.quote .name {
  color: var(--muted);
  font-size: 11px;
}

.quote strong {
  font-size: 24px;
}

.quote span:last-child {
  font-size: 13px;
  font-weight: 650;
}

.kv {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin: 0;
}

.kv div {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.kv dt {
  color: var(--muted);
  font-size: 10px;
}

.kv dd {
  margin: 2px 0 0;
  color: var(--fg);
  font-size: 14px;
}

.note {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}

.empty {
  min-height: 220px;
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

@media (max-width: 520px) {
  .kv {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
