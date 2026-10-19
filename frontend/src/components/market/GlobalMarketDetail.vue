<script setup lang="ts">
import { computed } from 'vue'

import MarketIndexKline from './MarketIndexKline.vue'
import type { GlobalMarketItem } from '../../market/global'
import { globalDetailBars } from '../../market/global'
import { compareClass, formatNumber, formatSignedPercent } from '../../market/review'

const props = defineProps<{
  item: GlobalMarketItem
}>()

const bars = computed(() => globalDetailBars(props.item))
const latest = computed(() => bars.value.at(-1) ?? null)
const selectedDate = computed(() => latest.value?.date ?? '')
const hasBars = computed(() => bars.value.length > 0)
</script>

<template>
  <div class="detail">
    <div class="quote">
      <span class="name">{{ item.name }}</span>
      <strong class="num" :class="compareClass(item.quote?.change_pct)">
        {{ formatNumber(item.quote?.price, item.precision) }}
      </strong>
      <span class="num" :class="compareClass(item.quote?.change_pct)">
        {{ formatSignedPercent(item.quote?.change_pct) }}
      </span>
      <span class="unit">{{ item.unit }}</span>
    </div>

    <dl class="kv">
      <div>
        <dt>MA5</dt>
        <dd class="num">{{ formatNumber(latest?.ma5, 2) }}</dd>
      </div>
      <div>
        <dt>MA20</dt>
        <dd class="num">{{ formatNumber(latest?.ma20, 2) }}</dd>
      </div>
      <div>
        <dt>最高</dt>
        <dd class="num">{{ formatNumber(item.quote?.high, item.precision) }}</dd>
      </div>
      <div>
        <dt>最低</dt>
        <dd class="num">{{ formatNumber(item.quote?.low, item.precision) }}</dd>
      </div>
      <div>
        <dt>日 K 覆盖</dt>
        <dd class="num">{{ bars.length }}</dd>
      </div>
    </dl>

    <div v-if="hasBars" class="chart-scroll">
      <MarketIndexKline :bars="bars" :selected-date="selectedDate" :show-volume="false" />
    </div>
    <div v-else class="empty">该标的暂无日 K 数据，不用推算值代替。</div>

    <p class="note">
      日 K 来自供应商原始日线，不复权、不补缺失日；MA5/MA20 在历史样本不足时保持空值。
    </p>
  </div>
</template>

<style scoped>
.detail {
  display: grid;
  gap: 12px;
}

.quote {
  display: flex;
  align-items: baseline;
  gap: 9px;
  flex-wrap: wrap;
}

.quote .name {
  color: var(--muted);
  font-size: 11px;
}

.quote strong {
  font-size: 25px;
  line-height: 1;
}

.quote span:not(.name):not(.unit) {
  font-size: 13px;
  font-weight: 650;
}

.unit {
  margin-left: auto;
  color: var(--muted);
  font-size: 10px;
}

.kv {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
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

.chart-scroll {
  overflow-x: auto;
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

.note {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
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

@media (max-width: 620px) {
  .kv {
    grid-template-columns: repeat(2, 1fr);
  }

  .unit {
    flex-basis: 100%;
    margin-left: 0;
  }
}
</style>
