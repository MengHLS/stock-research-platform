<script setup lang="ts">
import { useFirstBoardDaily } from '../market/useFirstBoardDaily'

const { date, data, failure, loading, load } = useFirstBoardDaily()
const statusLabel = {
  NOT_REFRESHED: '尚未入库',
  EMPTY: '当日首板事件为零',
  COMPLETE: '特征完整',
  PARTIAL: '部分事件信息不足或组合不支持',
}
const qualityLabel = {
  COMPLETE: '完整',
  PARTIAL: '部分缺失',
  INSUFFICIENT: '信息不足',
}
function reasonLabel(reason: string) {
  return reason
    .split(';')
    .map((code) => {
      const known: Record<string, string> = {
        MISSING_DAILY_BAR: '历史日线缺失',
        MISSING_OR_UNSAFE_ADJUSTMENT_FACTOR: '复权因子缺失或未通过校验',
        TREND_WINDOW_INCOMPLETE: '趋势历史窗口不完整',
        FLAT_60D_RANGE: '60 日价格区间无波动',
        UNSUPPORTED_AXIS_COMBINATION: '背景轴组合不在现有分类口径内',
        INSUFFICIENT_CALENDAR: '交易日历不足',
      }
      if (known[code]) return known[code]
      const gap = code.match(/^(\d+)D_PRICE_OR_FACTOR_GAP$/)
      if (gap) return `${gap[1]} 日窗口存在行情或复权缺口`
      const history = code.match(/^INSUFFICIENT_(\d+)D_HISTORY$/)
      return history ? `不足 ${history[1]} 个交易日历史` : code
    })
    .join('；')
}
</script>

<template>
  <section class="daily-events">
    <header>
      <div>
        <span class="eyebrow">PERSISTED DAILY EVENTS</span>
        <h2>已入库的每日首板分类</h2>
      </div>
      <span>截至 T-1 的行情 · 收盘后确认事件</span>
    </header>
    <form @submit.prevent="load()">
      <label>
        <span>交易日（留空查看最近已入库日期）</span>
        <input v-model="date" type="date" />
      </label>
      <button type="submit" :disabled="loading">{{ loading ? '读取中…' : '读取分类' }}</button>
    </form>
    <div v-if="failure" class="failure" role="alert">
      <p>{{ failure.message }}</p>
      <p v-if="failure.requestId">请求编号 {{ failure.requestId }}</p>
      <button type="button" @click="load()">重试</button>
    </div>
    <p v-if="loading" aria-live="polite">正在读取数据库中的分类结果…</p>
    <template v-if="data">
      <p class="summary">
        {{ data.trading_day ?? '暂无日期' }} · {{ statusLabel[data.status] }} ·
        {{ data.total }} 个首板
        <template v-if="data.source_event_count !== null">
          / 来源 {{ data.source_event_count }} 个
        </template>
      </p>
      <p v-if="data.status === 'NOT_REFRESHED'" class="muted">
        该日期尚未分析入库。读取页面不会触发重新计算。
      </p>
      <template v-else>
        <p class="muted">
          DatasetVersion {{ data.dataset_version_id }} · {{ data.feature_version }} · 入库时间
          {{ data.computed_at ? new Date(data.computed_at).toLocaleString() : '—' }}
        </p>
        <p class="muted">
          完整 {{ data.quality_counts?.COMPLETE ?? 0 }} · 部分缺失
          {{ data.quality_counts?.PARTIAL ?? 0 }} · 信息不足
          {{ data.quality_counts?.INSUFFICIENT ?? 0 }} · 不支持组合 {{ data.unsupported_count }}
        </p>
        <div class="distribution" aria-label="分类分布">
          <span v-for="(count, code) in data.class_counts" :key="code">
            {{ code }} · {{ count }}
          </span>
        </div>
        <div v-if="data.items?.length" class="rows">
          <article v-for="item in data.items" :key="item.event_id">
            <code>{{ item.stock_code }}</code>
            <div>
              <strong>
                {{ item.class_code ?? '待核对' }} ·
                {{ item.class_name ?? '不支持的背景轴组合' }}
              </strong>
              <span>
                特征截止 {{ item.feature_cutoff ?? '未知' }} ·
                {{ qualityLabel[item.quality_status] }} · 60 日位置
                {{
                  item.position_60d_pct === null
                    ? '未知'
                    : `${Number(item.position_60d_pct).toFixed(2)}%`
                }}
              </span>
              <small v-if="item.feature_reason" :title="item.feature_reason">
                缺失或校验原因：{{ reasonLabel(item.feature_reason) }}
              </small>
            </div>
          </article>
        </div>
        <nav v-if="data.total > data.limit" aria-label="首板分类分页">
          <button
            :disabled="data.offset === 0"
            @click="load(Math.max(0, data.offset - data.limit), true)"
          >
            上一页
          </button>
          <span>
            {{ data.offset + 1 }}–{{ Math.min(data.offset + data.limit, data.total) }} /
            {{ data.total }}
          </span>
          <button
            :disabled="data.offset + data.limit >= data.total"
            @click="load(data.offset + data.limit, true)"
          >
            下一页
          </button>
        </nav>
      </template>
    </template>
  </section>
</template>

<style scoped>
.daily-events {
  display: grid;
  gap: 12px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}
header,
form,
nav {
  display: flex;
  align-items: end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
h2 {
  margin: 4px 0 0;
  font-size: 18px;
  font-weight: 600;
}
p {
  margin: 0;
  font-size: 12px;
}
.eyebrow,
header > span,
.muted,
label,
nav,
article span,
article small {
  color: var(--muted);
  font-size: 11px;
}
.eyebrow {
  font-family: var(--mono);
  letter-spacing: 0.12em;
}
label {
  display: grid;
  gap: 6px;
  flex: 1;
}
input,
button {
  min-height: 36px;
  padding: 8px 10px;
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg);
  font: inherit;
}
button {
  cursor: pointer;
  font-size: 12px;
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.summary {
  color: var(--accent);
}
.failure {
  color: var(--up);
}
.distribution {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.distribution span {
  padding: 4px 7px;
  background: var(--surface2);
  border-radius: 4px;
  font: 10px var(--mono);
}
.rows {
  max-height: 420px;
  overflow: auto;
}
article {
  display: grid;
  grid-template-columns: 94px minmax(0, 1fr);
  gap: 12px;
  padding: 11px 0;
  border-top: 1px solid var(--border);
}
article code {
  color: var(--accent);
  font-size: 11px;
}
article div {
  display: grid;
  gap: 4px;
}
article strong {
  font-size: 12px;
  font-weight: 500;
}
article small {
  overflow-wrap: anywhere;
}
@media (max-width: 760px) {
  header {
    align-items: start;
  }
  label {
    min-width: 100%;
  }
  article {
    grid-template-columns: minmax(0, 1fr);
    gap: 6px;
  }
}
</style>
