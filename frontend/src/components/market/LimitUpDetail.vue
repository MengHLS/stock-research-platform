<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import AppIcon from '../AppIcon'
import StockDailyKline from './StockDailyKline.vue'
import type { LimitUpReviewRow, ReviewStockSeries } from '../../market/review'
import { buildCandleData, compareClass, formatSignedPercent } from '../../market/review'
import { limitUpBoardLabel, limitUpSealLabel, limitUpStatusLabel } from '../../market/limit-up'

const props = defineProps<{
  row: LimitUpReviewRow
  sameSector: LimitUpReviewRow[]
  note: string
  stockSeries: ReviewStockSeries | null
  stockLoading: boolean
  stockFailure: string | null
  stockRequestId?: string | null
}>()
const emit = defineEmits<{
  'save-note': [note: string]
  select: [row: LimitUpReviewRow]
  'retry-stock': []
}>()

const draft = ref(props.note)
const savedMessage = ref('')
let savedSnapshot: { key: string; note: string } | null = null
const currentRowKey = () => `${props.row.date}|${props.row.symbol}|${props.row.status}`
const hasCandles = computed(() =>
  buildCandleData(props.stockSeries?.bars ?? []).some((bar) => bar !== null),
)
watch(
  () => [props.row.date, props.row.symbol, props.row.status, props.note],
  () => {
    draft.value = props.note
    if (
      savedSnapshot !== null &&
      savedSnapshot.key === currentRowKey() &&
      props.note === savedSnapshot.note
    ) {
      savedSnapshot = null
    } else {
      savedSnapshot = null
      savedMessage.value = ''
    }
  },
)

function saveNote() {
  const next = draft.value.trim()
  savedSnapshot = { key: currentRowKey(), note: next }
  emit('save-note', next)
  savedMessage.value = '已保存到当前页面'
}
</script>

<template>
  <div class="detail">
    <div class="detail-head">
      <div>
        <span class="status" :class="row.status === 'broken' ? 'status--broken' : 'status--up'">
          {{ limitUpStatusLabel(row) }}
        </span>
        <span class="date">{{ row.date }}</span>
      </div>
      <span v-if="row.one_word_board && row.status === 'limit_up'" class="one-word">一字板</span>
    </div>

    <dl class="facts">
      <div>
        <dt>代码</dt>
        <dd class="mono">{{ row.symbol }}</dd>
      </div>
      <div>
        <dt>题材</dt>
        <dd>{{ row.sector }}</dd>
      </div>
      <div>
        <dt>板数</dt>
        <dd>{{ limitUpBoardLabel(row) }}</dd>
        <small v-if="row.boards_as_of_date !== row.date"> 截至 {{ row.boards_as_of_date }} </small>
      </div>
      <div>
        <dt>{{ row.status === 'broken' ? '前日首封' : '首封 / 一字' }}</dt>
        <dd>{{ limitUpSealLabel(row) }}</dd>
      </div>
      <div>
        <dt>当日涨跌</dt>
        <dd :class="compareClass(row.change_pct)">{{ formatSignedPercent(row.change_pct) }}</dd>
      </div>
      <div>
        <dt>一字板判定</dt>
        <dd>
          {{
            row.status === 'broken'
              ? '不适用（断板）'
              : row.one_word_board === null
                ? '未知'
                : row.one_word_board
                  ? '是'
                  : '否'
          }}
        </dd>
      </div>
    </dl>

    <div v-if="row.status === 'broken'" class="notice notice--warn">
      <AppIcon name="alert-triangle" :size="15" />
      <span>
        {{ limitUpStatusLabel(row) }}。板数 {{ limitUpBoardLabel(row) }} 是
        {{ row.boards_as_of_date }} 的在榜高度，不是本次观察日的板数。
      </span>
    </div>
    <div v-else-if="row.boards === null" class="notice notice--warn">
      <AppIcon name="alert-triangle" :size="15" />
      <span>连板历史缺口或查询窗口触顶，板数保持未知，不能按首板处理。</span>
    </div>

    <div class="detail-layout">
      <div class="detail-main">
        <section class="chart-section">
          <div class="section-title">
            <div>
              <h3>个股日 K</h3>
              <p>按数据源价格展示，复权口径未确认</p>
            </div>
            <span v-if="stockSeries">{{ stockSeries.window_actual }} 个交易日</span>
          </div>
          <div v-if="stockLoading && !stockSeries" class="chart-state">
            正在读取 {{ row.symbol }} 的日线…
          </div>
          <div v-else-if="stockFailure" class="chart-state chart-state--error" role="alert">
            <AppIcon name="alert-triangle" :size="18" />
            <b>个股日线读取失败</b>
            <span>{{ stockFailure }}</span>
            <small v-if="stockRequestId">请求编号 {{ stockRequestId }}</small>
            <button type="button" @click="emit('retry-stock')">重试</button>
          </div>
          <div v-else-if="stockSeries && hasCandles" class="chart-scroll">
            <StockDailyKline :series="stockSeries" :selected-date="row.date" />
          </div>
          <div v-else class="chart-state">当前窗口没有完整的个股日 K 数据。</div>
        </section>

        <p class="data-gap">封单额与换手率暂无数据。</p>
      </div>

      <aside class="detail-side">
        <section class="same-sector">
          <div class="section-title">
            <h3>同日同题材</h3>
            <span>{{ sameSector.length }} 只</span>
          </div>
          <button
            v-for="item in sameSector"
            :key="`${item.date}-${item.symbol}-${item.status}`"
            type="button"
            @click="emit('select', item)"
          >
            <span class="mono">{{ item.symbol }}</span>
            <b>{{ item.name }}</b>
            <em>{{ limitUpBoardLabel(item) }}</em>
            <AppIcon name="chevron-right" :size="14" />
          </button>
          <p v-if="!sameSector.length" class="side-empty">当日该题材暂无其它涨停。</p>
        </section>
        <section class="note-section">
          <div class="section-title">
            <h3>复盘备注</h3>
            <span>仅保存在当前页面，刷新后清除</span>
          </div>
          <textarea
            v-model="draft"
            rows="4"
            maxlength="2000"
            placeholder="例如：封板后开板放量，次日只观察竞价承接；不要把这条备注当作交易指令。"
          />
          <div class="note-actions">
            <button type="button" class="save" @click="saveNote">保存本次备注</button>
            <span v-if="savedMessage" class="saved-message" role="status">{{ savedMessage }}</span>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.detail {
  display: grid;
  gap: 16px;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.detail-head > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status,
.one-word,
.date {
  min-height: 27px;
  padding: 2px 9px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  font-size: 12px;
}

.status--up {
  background: color-mix(in oklab, var(--up) 14%, transparent);
  color: var(--up);
}

.status--broken {
  background: color-mix(in oklab, var(--warn) 14%, transparent);
  color: var(--warn);
}

.date {
  background: var(--surface2);
  color: var(--muted);
  font-family: var(--mono);
}

.one-word {
  background: var(--up);
  color: #fff;
  font-weight: 650;
}

.facts {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 9px;
  margin: 0;
}

.facts div {
  min-width: 0;
  padding: 10px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.facts dt {
  color: var(--muted);
  font-size: 11.5px;
}

.facts dd {
  margin: 3px 0 0;
  color: var(--fg);
  font-size: 14.5px;
  overflow-wrap: anywhere;
}

.facts small {
  display: block;
  color: var(--muted);
  font-size: 10.5px;
}

.mono {
  font-family: var(--mono);
}

.notice {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 12.5px;
  line-height: 1.55;
}

.notice--warn {
  border: 1px solid color-mix(in oklab, var(--warn) 34%, var(--border));
  background: color-mix(in oklab, var(--warn) 8%, transparent);
  color: var(--warn);
}

.detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 300px);
  align-items: start;
  gap: 18px;
}

.detail-main {
  min-width: 0;
  display: grid;
  gap: 16px;
}

.detail-side {
  min-width: 0;
  padding-left: 18px;
  border-left: 1px solid var(--border);
  display: grid;
  gap: 14px;
  align-content: start;
}

.chart-section,
.note-section,
.same-sector {
  min-width: 0;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.section-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 9px;
}

.section-title h3 {
  margin: 0;
  color: var(--fg2);
  font-size: 14px;
}

.section-title span {
  color: var(--muted);
  font-size: 11.5px;
  white-space: nowrap;
}

.section-title p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.5;
}

.chart-scroll {
  min-width: 0;
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  scrollbar-gutter: stable;
}

.chart-state {
  min-height: 240px;
  padding: 20px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 7px;
  font-size: 12.5px;
  text-align: center;
}

.chart-state b {
  color: var(--fg2);
  font-size: 14px;
}

.chart-state small {
  font-family: var(--mono);
}

.chart-state button {
  min-height: 32px;
  padding: 3px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  font-size: 12px;
  cursor: pointer;
}

.chart-state--error {
  color: var(--up);
}

.note-section textarea {
  width: 100%;
  min-height: 104px;
  padding: 10px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  outline: 0;
  resize: vertical;
  background: var(--surface2);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  line-height: 1.55;
}

.note-section textarea:focus {
  border-color: var(--accent);
}

.note-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 9px;
}

.save {
  min-height: 34px;
  padding: 4px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  font-size: 12px;
  cursor: pointer;
}

.saved-message {
  color: var(--down);
  font-size: 11.5px;
}

.data-gap {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.same-sector {
  display: grid;
  gap: 6px;
}

.same-sector .section-title {
  margin-bottom: 3px;
}

.same-sector button {
  display: grid;
  grid-template-columns: 98px minmax(0, 1fr) auto 16px;
  align-items: center;
  gap: 7px;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  text-align: left;
  cursor: pointer;
}

.same-sector button:hover {
  border-color: var(--border2);
  background: var(--surface3);
}

.same-sector b {
  color: var(--fg);
  font-size: 12.5px;
}

.same-sector em {
  color: var(--muted);
  font-size: 11px;
  font-style: normal;
}

.side-empty {
  margin: 0;
  padding: 18px 10px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 12px;
  text-align: center;
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

@media (max-width: 900px) {
  .detail-layout {
    grid-template-columns: 1fr;
  }

  .detail-side {
    padding: 14px 0 0;
    border-top: 1px solid var(--border);
    border-left: 0;
  }
}

@media (max-width: 760px) {
  .facts {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .same-sector button {
    grid-template-columns: 88px minmax(0, 1fr) 16px;
  }

  .same-sector em {
    display: none;
  }

  .save {
    min-height: 44px;
  }

  .chart-state button {
    min-height: 44px;
  }
}
</style>
