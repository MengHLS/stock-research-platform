<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import AppIcon from '../AppIcon'
import IntradayChart from './IntradayChart.vue'
import StockDailyKline from './StockDailyKline.vue'
import {
  SHORT_PATH_OPTIONS,
  TREND_OPTIONS,
  positionBandLabel,
  type FirstBoardHistory,
  type FirstBoardShortPath,
  type FirstBoardTrend,
} from '../../market/first-board-classifier'
import type { IntradayBar } from '../../market/intraday'
import type { LimitUpReviewRow, ReviewStockSeries } from '../../market/review'
import {
  buildCandleData,
  compareClass,
  formatMarketCapCny,
  formatSignedPercent,
  formatTurnoverPct,
  formatVolumeLots,
} from '../../market/review'
import type { ReviewStockFacts } from '../../market/stock-facts'
import { limitUpBoardLabel, limitUpSealLabel, limitUpStatusLabel } from '../../market/limit-up'

const props = defineProps<{
  row: LimitUpReviewRow
  note: string
  stockSeries: ReviewStockSeries | null
  stockLoading: boolean
  stockFailure: string | null
  stockRequestId?: string | null
  facts: ReviewStockFacts | null
  factsLoading: boolean
  factsFailure: string | null
  factsRequestId?: string | null
  intradayBars: IntradayBar[]
  intradayTradingDay: string | null
  intradayLoading: boolean
  intradayFailure: string | null
  intradayRequestId?: string | null
  firstBoardEvents: FirstBoardHistory | null
  firstBoardLoading: boolean
  firstBoardFailure: string | null
  firstBoardRequestId?: string | null
  initialChartMode?: 'daily' | 'intraday'
}>()
const emit = defineEmits<{
  'save-note': [note: string]
  'retry-stock': []
  'retry-facts': []
  'request-intraday': []
  'retry-intraday': []
  'retry-first-board': []
}>()

const draft = ref(props.note)
const savedMessage = ref('')
const chartMode = ref<'daily' | 'intraday'>(props.initialChartMode ?? 'daily')
let savedSnapshot: { key: string; note: string } | null = null
const currentRowKey = () => `${props.row.date}|${props.row.symbol}|${props.row.status}`
const hasCandles = computed(() =>
  buildCandleData(props.stockSeries?.bars ?? []).some((bar) => bar !== null),
)
const industryName = computed(() => props.facts?.industry?.name ?? '未知')
const industryMeta = computed(() => {
  const industry = props.facts?.industry
  if (!industry) return ''
  return [industry.code, industry.source, `自 ${industry.effective_from} 生效`]
    .filter(Boolean)
    .join(' · ')
})
const factsNote = computed(() =>
  (props.facts?.issues ?? [])
    .filter((issue) => issue.code.startsWith('stock_'))
    .map((issue) => issue.message)
    .join(' '),
)
const firstBoardHistory = computed(() =>
  [...(props.firstBoardEvents?.items ?? [])].sort(
    (left, right) =>
      right.event_date.localeCompare(left.event_date) ||
      right.event_id.localeCompare(left.event_id),
  ),
)
const firstBoardRange = computed(() => {
  if (!firstBoardHistory.value.length) return ''
  return `${firstBoardHistory.value.at(-1)?.event_date} ～ ${firstBoardHistory.value[0].event_date}`
})
function trendLabel(value: FirstBoardTrend): string {
  return TREND_OPTIONS.find((option) => option.value === value)?.label ?? '未知'
}
function shortPathLabel(value: FirstBoardShortPath): string {
  return SHORT_PATH_OPTIONS.find((option) => option.value === value)?.label ?? '未知'
}
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

watch(
  () => [props.row.symbol, props.row.date],
  () => {
    chartMode.value = 'daily'
  },
)

function chooseChart(mode: 'daily' | 'intraday') {
  chartMode.value = mode
  if (mode === 'intraday') emit('request-intraday')
}

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
        <dt>行业</dt>
        <dd :title="factsFailure ?? undefined">
          {{ factsLoading && !facts ? '读取中…' : industryName }}
        </dd>
        <small v-if="industryMeta">{{ industryMeta }}</small>
        <template v-if="!factsLoading && factsFailure">
          <small class="fact-error">{{ factsFailure }}</small>
          <small v-if="factsRequestId">请求编号 {{ factsRequestId }}</small>
          <button type="button" class="fact-retry" @click="emit('retry-facts')">
            重试行业与量价
          </button>
        </template>
      </div>
      <div>
        <dt>公司市值</dt>
        <dd>{{ formatMarketCapCny(facts?.valuation.total_market_cap_cny) }}</dd>
        <small>流通 {{ formatMarketCapCny(facts?.valuation.circulation_market_cap_cny) }}</small>
      </div>
      <div>
        <dt>换手率</dt>
        <dd>{{ formatTurnoverPct(facts?.valuation.turnover_pct) }}</dd>
        <small v-if="facts?.valuation.source">{{ facts.valuation.source }}</small>
      </div>
      <div>
        <dt>成交量</dt>
        <dd>{{ formatVolumeLots(facts?.trade.volume_shares) }}</dd>
        <small v-if="facts?.trade.amount_cny !== undefined">
          成交额 {{ formatMarketCapCny(facts?.trade.amount_cny) }}
        </small>
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

    <p v-if="factsNote" class="facts-note" role="status">数据缺口：{{ factsNote }}</p>

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
              <h3>个股走势</h3>
              <p v-if="chartMode === 'daily'">日 K · 按数据源价格展示，复权口径未确认</p>
              <p v-else>最近分时 · {{ intradayTradingDay ?? '读取最近交易日' }} · 1 分钟</p>
            </div>
            <div class="chart-controls">
              <span v-if="chartMode === 'daily' && stockSeries">
                {{ stockSeries.window_actual }} 个交易日
              </span>
              <div class="chart-switch" role="group" aria-label="个股图表周期">
                <button
                  type="button"
                  :class="{ active: chartMode === 'daily' }"
                  :aria-pressed="chartMode === 'daily'"
                  @click="chooseChart('daily')"
                >
                  日 K
                </button>
                <button
                  type="button"
                  :class="{ active: chartMode === 'intraday' }"
                  :aria-pressed="chartMode === 'intraday'"
                  @click="chooseChart('intraday')"
                >
                  最近分时
                </button>
              </div>
            </div>
          </div>
          <template v-if="chartMode === 'daily'">
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
            <div v-else class="chart-state">
              <span>当前窗口没有完整的个股日 K 数据。</span>
              <button type="button" @click="emit('retry-stock')">重新读取日 K</button>
            </div>
          </template>
          <template v-else>
            <div v-if="intradayLoading" class="chart-state">
              正在读取 {{ row.symbol }} 的最近分时…
            </div>
            <div v-else-if="intradayFailure" class="chart-state chart-state--error" role="alert">
              <AppIcon name="alert-triangle" :size="18" />
              <b>最近分时读取失败</b>
              <span>{{ intradayFailure }}</span>
              <small v-if="intradayRequestId">请求编号 {{ intradayRequestId }}</small>
              <button type="button" @click="emit('retry-intraday')">重试</button>
            </div>
            <div v-else-if="intradayBars.length" class="chart-scroll">
              <IntradayChart :bars="intradayBars" />
            </div>
            <div v-else class="chart-state">
              <span>最近交易日暂无分时数据。</span>
              <button type="button" @click="emit('retry-intraday')">重新读取分时</button>
            </div>
          </template>
        </section>

        <p class="data-gap">
          封单额旧源未提供（涨停记录只有封板时间），不做估算；换手率、市值与成交量见上方数据库字段。
        </p>
      </div>

      <aside class="detail-side">
        <section class="event-history">
          <div class="section-title">
            <div>
              <h3>历史首板事件分类</h3>
              <p v-if="firstBoardEvents">
                {{ firstBoardHistory.length }} 次 · {{ firstBoardRange }}
              </p>
            </div>
            <span v-if="firstBoardEvents">
              冻结 {{ firstBoardEvents.source.frozen_dataset_version_id ?? '不可用' }} · 入库
              {{ firstBoardEvents.source.stored_event_count }}
            </span>
          </div>
          <div v-if="firstBoardLoading" class="event-state">
            正在读取 {{ row.symbol }} 的历史首板…
          </div>
          <div v-else-if="firstBoardFailure" class="event-state event-state--error" role="alert">
            <AppIcon name="alert-triangle" :size="16" />
            <b>历史首板分类读取失败</b>
            <span>{{ firstBoardFailure }}</span>
            <small v-if="firstBoardRequestId">请求编号 {{ firstBoardRequestId }}</small>
            <button type="button" @click="emit('retry-first-board')">重试事件分析</button>
          </div>
          <div
            v-else-if="
              firstBoardEvents?.source.frozen_status === 'BAD_DATA' && !firstBoardHistory.length
            "
            class="event-state event-state--error"
            role="alert"
          >
            <AppIcon name="alert-triangle" :size="16" />
            <b>冻结首板历史未通过校验</b>
            <span>平台当前也没有该股票已入库的首板事件，因此不返回猜测结果。</span>
            <button type="button" @click="emit('retry-first-board')">重试事件分析</button>
          </div>
          <template v-else-if="firstBoardHistory.length">
            <div
              v-if="firstBoardEvents?.source.frozen_status !== 'PASS'"
              class="event-source-warning"
            >
              <span>冻结历史当前不可用，仅显示平台已入库事件。</span>
              <button type="button" @click="emit('retry-first-board')">重试事件分析</button>
            </div>
            <article
              v-for="item in firstBoardHistory"
              :key="item.event_id"
              class="event-row"
              :class="{ 'event-row--current': item.event_date === row.date }"
            >
              <header>
                <time>{{ item.event_date }}</time>
                <span class="limit-up-mark">首板涨停</span>
                <span class="source-mark">
                  {{ item.source_kind === 'stored' ? '平台入库' : '冻结历史' }}
                </span>
                <span v-if="item.quality_status !== 'COMPLETE'" class="quality-mark">
                  信息不足
                </span>
                <span v-if="item.event_date === row.date" class="current-mark">当前复盘日</span>
              </header>
              <strong>
                {{ item.class_code ?? '待核对' }} ·
                {{ item.class_name ?? '不支持的背景轴组合' }}
              </strong>
              <p>{{ item.group_code ?? '—' }} · {{ item.group_name ?? '分类信息不足' }}</p>
              <dl>
                <div>
                  <dt>位置</dt>
                  <dd>{{ positionBandLabel(item.position_band) }}</dd>
                </div>
                <div>
                  <dt>趋势</dt>
                  <dd>{{ trendLabel(item.trend) }}</dd>
                </div>
                <div>
                  <dt>短期路径</dt>
                  <dd>{{ shortPathLabel(item.short_path) }}</dd>
                </div>
              </dl>
              <footer>
                <span>
                  60 日位置
                  {{
                    item.position_60d_pct === null
                      ? '未知'
                      : `${Number(item.position_60d_pct).toFixed(2)}%`
                  }}
                </span>
                <code>{{ item.source_detail_code ?? '—' }}</code>
              </footer>
            </article>
            <p class="event-source">
              合并已验证冻结历史与平台当前入库快照 · 仅描述 T-1 背景，不预示后续收益
            </p>
          </template>
          <p v-else-if="firstBoardEvents?.source.frozen_status === 'PASS'" class="side-empty">
            该股票在已验证首板账本和当前入库快照中没有历史事件。
          </p>
          <p
            v-else-if="firstBoardEvents?.source.frozen_status === 'NOT_CONFIGURED'"
            class="side-empty"
          >
            冻结历史未配置，当前也没有该股票的入库事件。
          </p>
          <p v-else class="side-empty">冻结历史不可用，当前也没有该股票的入库事件。</p>
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
  border: 1px solid color-mix(in oklab, var(--up) 72%, white 8%);
  background: color-mix(in oklab, var(--up) 80%, #000);
  color: #fff;
  font-weight: 650;
}

.status--broken {
  border: 1px solid color-mix(in oklab, var(--warn) 42%, var(--border));
  background: color-mix(in oklab, var(--warn) 13%, transparent);
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
  grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
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

.facts .fact-error {
  color: var(--warn);
}

.fact-retry {
  margin-top: 6px;
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font: inherit;
  font-size: 11.5px;
  cursor: pointer;
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
.event-history {
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

.chart-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.chart-switch {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.chart-switch button {
  min-height: 27px;
  padding: 2px 9px;
  border: 0;
  border-radius: calc(var(--radius-sm) - 2px);
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 11.5px;
  cursor: pointer;
}

.chart-switch button.active {
  background: var(--surface);
  color: var(--fg);
  box-shadow: 0 1px 2px color-mix(in oklab, var(--fg) 10%, transparent);
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

.facts-note {
  margin: 0;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--muted);
  font-size: 11px;
  line-height: 1.55;
}

.event-history {
  display: grid;
  gap: 9px;
}

.event-history .section-title {
  margin-bottom: 3px;
}

.event-row {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
}

.event-row--current {
  border-color: color-mix(in oklab, var(--up) 58%, var(--border));
  box-shadow: inset 3px 0 0 var(--up);
}

.event-row header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.event-row time {
  margin-right: auto;
  color: var(--accent);
  font: 11px var(--mono);
}

.limit-up-mark,
.source-mark,
.quality-mark,
.current-mark {
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 9.5px;
}

.limit-up-mark {
  background: color-mix(in oklab, var(--up) 80%, #000);
  color: #fff;
  font-weight: 650;
}

.source-mark {
  border: 1px solid var(--border2);
  color: var(--muted);
}

.quality-mark {
  border: 1px solid color-mix(in oklab, var(--warn) 42%, var(--border));
  color: var(--warn);
}

.current-mark {
  border: 1px solid color-mix(in oklab, var(--up) 40%, var(--border));
  color: var(--up);
}

.event-row > strong {
  display: block;
  margin-top: 7px;
  color: var(--fg);
  font-size: 12px;
  line-height: 1.45;
}

.event-row > p {
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 10px;
}

.event-row dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 5px;
  margin: 8px 0 0;
}

.event-row dl div {
  min-width: 0;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.event-row dt {
  color: var(--muted);
  font-size: 9px;
}

.event-row dd {
  margin: 2px 0 0;
  color: var(--fg2);
  font-size: 9.5px;
  line-height: 1.35;
}

.event-row footer {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  color: var(--muted);
  font-size: 9.5px;
}

.event-row code {
  color: var(--accent);
  font-family: var(--mono);
}

.event-source {
  margin: 0;
  color: var(--muted);
  font-size: 9.5px;
  line-height: 1.55;
}

.event-source-warning {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  border: 1px solid color-mix(in oklab, var(--warn) 30%, var(--border));
  border-radius: var(--radius-sm);
  background: color-mix(in oklab, var(--warn) 7%, transparent);
  color: var(--warn);
  font-size: 10px;
  line-height: 1.5;
}

.event-source-warning button {
  flex: none;
  min-height: 26px;
  padding: 2px 7px;
  border: 1px solid color-mix(in oklab, var(--warn) 40%, var(--border));
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--warn);
  font-size: 9.5px;
  cursor: pointer;
}

.event-state {
  display: grid;
  justify-items: center;
  gap: 6px;
  padding: 22px 12px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 11.5px;
  text-align: center;
}

.event-state--error {
  border-color: color-mix(in oklab, var(--up) 34%, var(--border));
  color: var(--up);
}

.event-state b {
  color: var(--fg2);
}

.event-state small {
  font-family: var(--mono);
}

.event-state button {
  min-height: 30px;
  padding: 3px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--fg2);
  font-size: 11px;
  cursor: pointer;
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

  .event-row dl {
    grid-template-columns: minmax(0, 1fr);
  }

  .save {
    min-height: 44px;
  }

  .chart-state button {
    min-height: 44px;
  }
}
</style>
