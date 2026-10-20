<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

import AppIcon from '../AppIcon'
import { api, callApi, type ApiFailure } from '../../api/client'
import { isAuthNotConfigured } from '../../api/errors'
import { formatNumber, formatSignedPercent } from '../../market/review'
import {
  formatLayerMetric,
  layerLabel,
  signedValueTone,
  stateClassificationTone,
  type MarketStateDescription,
} from '../../market/state-description'

const props = defineProps<{ date: string }>()

const data = ref<MarketStateDescription | null>(null)
const failure = ref<ApiFailure | null>(null)
const loading = ref(false)
let controller: AbortController | null = null

function failureText(value: ApiFailure): string {
  if (isAuthNotConfigured(value)) return '登录服务尚未启用，无法读取市场状态描述。'
  if (value.kind === 'network') return '无法连接后台服务，请检查 API 或网络。'
  if (value.kind === 'business' && value.code === 'SOURCE_NOT_CONFIGURED') {
    return '市场状态描述暂不可用，未用实时行情替代。'
  }
  if (value.kind === 'business' && value.code === 'MARKET_STATE_DATE_UNAVAILABLE') {
    return '该日期没有可用的市场状态描述。'
  }
  return value.message
}

async function load() {
  controller?.abort()
  data.value = null
  failure.value = null
  if (!props.date) return
  const current = new AbortController()
  controller = current
  loading.value = true
  const result = await callApi(
    (signal) =>
      api.GET('/api/v1/market/state/description', {
        params: { query: { date: props.date } },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (controller !== current || current.signal.aborted) return
  loading.value = false
  if (result.ok) data.value = result.data
  else if (result.failure.kind !== 'aborted') failure.value = result.failure
}

watch(() => props.date, load, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="panel state-panel">
    <header class="panel-head">
      <div>
        <h2>市场状态描述</h2>
        <span class="sub">5日变化 · 20日趋势 · 60日结构</span>
      </div>
      <span class="grow" />
      <span v-if="loading" class="state">读取中…</span>
    </header>

    <div v-if="failure" class="panel-body state-state state-state--error" role="alert">
      <AppIcon name="alert-triangle" :size="16" />
      <span>{{ failureText(failure) }}</span>
      <span v-if="failure.requestId" class="request-id">请求编号 {{ failure.requestId }}</span>
      <button type="button" class="retry" @click="load">重试</button>
    </div>
    <div v-else-if="!data" class="panel-body state-state">
      {{ loading ? `正在读取 ${date} 的市场状态…` : '没有可展示的观察日期。' }}
    </div>
    <template v-else>
      <div class="hero">
        <div class="hero-copy">
          <span class="eyebrow">截至 {{ data.date }} 收盘 · 描述不是预测</span>
          <p>{{ data.summary }}</p>
        </div>
        <div class="fact-strip">
          <div>
            <span>沪深300 当日</span>
            <b :class="signedValueTone(data.facts.csi300_return_1d_pct)">
              {{ formatSignedPercent(data.facts.csi300_return_1d_pct) }}
            </b>
          </div>
          <div>
            <span>个股收益中位数</span>
            <b :class="signedValueTone(data.facts.median_return_pct)">
              {{ formatSignedPercent(data.facts.median_return_pct) }}
            </b>
          </div>
          <div>
            <span>上涨股票占比</span>
            <b>{{ formatNumber(data.facts.advancer_ratio_pct, 2) }}%</b>
          </div>
          <div>
            <span>MA20 / MA60 宽度</span>
            <b>
              {{ formatNumber(data.facts.above_ma20_ratio_pct, 1) }}% /
              {{ formatNumber(data.facts.above_ma60_ratio_pct, 1) }}%
            </b>
          </div>
        </div>
      </div>

      <div class="layer-grid">
        <article
          v-for="layer in data.layers"
          :key="layer.key"
          class="layer-card"
          :class="`tone-${stateClassificationTone(layer.classification)}`"
        >
          <div class="layer-head">
            <span>{{ layer.label }}</span>
            <strong>{{ layerLabel(layer) }}</strong>
          </div>
          <div class="metrics">
            <div v-for="metric in layer.metrics" :key="metric.key">
              <span>{{ metric.label }}</span>
              <b>{{ formatLayerMetric(metric.value, metric.unit) }}</b>
            </div>
          </div>
          <p>{{ layer.note }}</p>
          <small v-if="layer.base_date">对照日 {{ layer.base_date }}</small>
        </article>
      </div>

      <div class="detail-grid">
        <div class="detail-block">
          <h3>成交与风险</h3>
          <dl>
            <div>
              <dt>成交额 / 前20日均值</dt>
              <dd>{{ formatNumber(data.facts.amount_ratio_20, 2) }}</dd>
            </div>
            <div>
              <dt>120日成交额 midrank</dt>
              <dd>
                {{
                  data.facts.amount_rolling_120_midrank === null
                    ? '—'
                    : `${formatNumber(Number(data.facts.amount_rolling_120_midrank) * 100, 1)}%`
                }}
              </dd>
            </div>
            <div>
              <dt>沪深300 20日波动 / 60日回撤</dt>
              <dd>
                {{ formatNumber(data.facts.csi300_volatility_20_pct, 1) }}% /
                {{ formatSignedPercent(data.facts.csi300_drawdown_60_pct) }}
              </dd>
            </div>
          </dl>
        </div>
        <div class="detail-block">
          <h3>涨停生态</h3>
          <dl>
            <div>
              <dt>收盘涨停 / 跌停</dt>
              <dd>
                {{ data.facts.limit_up_close_count ?? '—' }} /
                {{ data.facts.limit_down_close_count ?? '—' }}
              </dd>
            </div>
            <div>
              <dt>炸板率</dt>
              <dd>{{ formatNumber(data.facts.broken_board_rate_pct, 1) }}%</dd>
            </div>
            <div>
              <dt>昨涨停反馈均值 / 胜率</dt>
              <dd>
                {{ formatSignedPercent(data.facts.yesterday_limit_up_feedback_avg_return_pct) }} /
                {{ formatNumber(data.facts.yesterday_limit_up_feedback_win_rate_pct, 1) }}%
              </dd>
            </div>
          </dl>
        </div>
      </div>

      <div v-if="data.conflicts.length" class="conflicts">
        <h3>当前分歧</h3>
        <span v-for="conflict in data.conflicts" :key="conflict.code">
          {{ conflict.message }}
        </span>
      </div>

      <details v-if="data.issues.length" class="quality">
        <summary>数据限制</summary>
        <div>
          <span v-for="issue in data.issues" :key="issue.code">{{ issue.message }}</span>
        </div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.state-panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in oklab, var(--surface) 94%, var(--fg) 6%);
}

.panel-head h2,
.panel-head .sub {
  margin: 0;
}

.panel-head h2 {
  font-size: 14px;
  line-height: 1.3;
}

.sub {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 11px;
}

.grow {
  flex: 1;
}

.state {
  color: var(--muted);
  font-size: 11px;
}

.panel-body {
  padding: 18px;
}

.state-state {
  min-height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}

.state-state--error {
  color: var(--warn);
}

.request-id {
  flex-basis: 100%;
  font-family: var(--mono);
  font-size: 10px;
}

.retry {
  padding: 4px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  cursor: pointer;
}

.hero {
  display: grid;
  grid-template-columns: minmax(280px, 1.4fr) minmax(380px, 2fr);
  gap: 18px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background:
    radial-gradient(
      circle at 8% 10%,
      color-mix(in oklab, var(--accent) 12%, transparent),
      transparent 44%
    ),
    linear-gradient(135deg, var(--surface2), color-mix(in oklab, var(--surface) 82%, var(--bg)));
}

.eyebrow {
  color: var(--muted);
  font-size: 10px;
  letter-spacing: 0.04em;
}

.hero-copy p {
  margin: 7px 0 0;
  color: var(--fg);
  font-size: 15px;
  font-weight: 620;
  line-height: 1.65;
}

.fact-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--border);
}

.fact-strip div {
  min-width: 0;
  padding: 9px 11px;
  background: color-mix(in oklab, var(--surface) 92%, transparent);
  display: grid;
  gap: 2px;
}

.fact-strip span {
  color: var(--muted);
  font-size: 9.5px;
}

.fact-strip b {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 650;
}

.layer-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.layer-card {
  --tone: var(--muted);
  min-width: 0;
  padding: 12px;
  border: 1px solid color-mix(in oklab, var(--tone) 30%, var(--border));
  border-top: 3px solid var(--tone);
  border-radius: var(--radius);
  background: var(--surface2);
}

.layer-card.tone-up {
  --tone: var(--up);
}

.layer-card.tone-down {
  --tone: var(--down);
}

.layer-card.tone-warn {
  --tone: var(--warn);
}

.layer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.layer-head span {
  color: var(--muted);
  font-size: 10.5px;
}

.layer-head strong {
  color: var(--tone);
  font-size: 14px;
}

.metrics {
  display: grid;
  gap: 5px;
  margin-top: 10px;
}

.metrics div,
.detail-block dl div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.metrics span,
.detail-block dt {
  color: var(--muted);
  font-size: 10px;
}

.metrics b,
.detail-block dd {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 620;
}

.layer-card p {
  min-height: 31px;
  margin: 9px 0 0;
  color: var(--fg2);
  font-size: 10px;
  line-height: 1.55;
}

.layer-card small {
  color: var(--muted);
  font-size: 9px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.detail-block {
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.detail-block h3,
.conflicts h3 {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 650;
}

.detail-block dl {
  display: grid;
  gap: 6px;
  margin: 0;
}

.detail-block dd {
  margin: 0;
}

.conflicts {
  margin-top: 10px;
  padding: 11px 12px;
  border: 1px solid color-mix(in oklab, var(--warn) 30%, var(--border));
  border-radius: var(--radius);
  background: color-mix(in oklab, var(--warn) 7%, transparent);
  display: grid;
  gap: 5px;
}

.conflicts span {
  color: var(--fg2);
  font-size: 10.5px;
  line-height: 1.5;
}

.quality {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px dashed var(--border);
  color: var(--muted);
  font-size: 10px;
}

.quality summary {
  cursor: pointer;
}

.quality div {
  display: grid;
  gap: 4px;
  margin-top: 7px;
  line-height: 1.5;
}

.up {
  color: var(--up);
}

.down {
  color: var(--down);
}

@media (max-width: 980px) {
  .hero {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .layer-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .fact-strip {
    grid-template-columns: 1fr;
  }

  .panel-head {
    align-items: flex-start;
  }
}
</style>
