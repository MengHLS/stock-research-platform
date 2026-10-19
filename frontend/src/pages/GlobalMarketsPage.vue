<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon'
import GlobalMarketDetail from '../components/market/GlobalMarketDetail.vue'
import MarketSparkline from '../components/market/MarketSparkline.vue'
import ReviewDrawer from '../components/market/ReviewDrawer.vue'
import { api, callApi } from '../api/client'
import { isAuthNotConfigured, type ApiFailure } from '../api/errors'
import {
  GLOBAL_GROUPS,
  formatMarketTime,
  marketBreadth,
  type GlobalMarketGroup,
  type GlobalMarketItem,
  type GlobalMarketOverview,
} from '../market/global'
import { chartNumber, compareClass, formatNumber, formatSignedPercent } from '../market/review'

const route = useRoute()
const router = useRouter()

const overview = ref<GlobalMarketOverview | null>(null)
const failure = ref<ApiFailure | null>(null)
const loading = ref(false)
const activeGroup = ref<GlobalMarketGroup | 'all'>('all')
const selectedItem = ref<GlobalMarketItem | null>(null)
const reloadKey = ref(0)
let controller: AbortController | null = null

const supportedWindows = [20, 60, 120] as const
const selectedWindow = computed(() => {
  const requested = Number(route.query.window)
  return supportedWindows.includes(requested as (typeof supportedWindows)[number]) ? requested : 60
})
const visibleItems = computed(() =>
  (overview.value?.items ?? []).filter(
    (item) => activeGroup.value === 'all' || item.group === activeGroup.value,
  ),
)
const breadth = computed(() => marketBreadth(overview.value?.items ?? []))
const issueCount = computed(
  () => overview.value?.items.reduce((count, item) => count + itemIssues(item).length, 0) ?? 0,
)
const filterOptions = computed(() => [
  { key: 'all' as const, label: '全部', count: overview.value?.items.length ?? 0 },
  ...GLOBAL_GROUPS.map((group) => ({
    key: group.key,
    label: group.label,
    count: overview.value?.items.filter((item) => item.group === group.key).length ?? 0,
  })),
])

function failureText(value: ApiFailure): string {
  if (isAuthNotConfigured(value)) return '服务端尚未配置认证，无法读取全球市场数据。'
  if (value.kind === 'network') return '无法连接后台服务，请确认 API 已启动或检查网络。'
  return value.message
}

function setWindow(value: number) {
  void router.push({
    path: route.path,
    query: { ...route.query, window: String(value) },
  })
}

function tone(item: GlobalMarketItem) {
  return compareClass(item.quote?.change_pct)
}

function closes(item: GlobalMarketItem) {
  return itemBars(item).map((bar) => chartNumber(bar.close))
}

function itemBars(item: GlobalMarketItem) {
  return item.bars ?? []
}

function itemIssues(item: GlobalMarketItem) {
  return item.issues ?? []
}

function openItem(item: GlobalMarketItem) {
  selectedItem.value = item
}

function closeDetail() {
  selectedItem.value = null
}

async function load() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  failure.value = null
  selectedItem.value = null
  if (overview.value?.window_requested !== selectedWindow.value) overview.value = null

  const result = await callApi(
    (signal) =>
      api.GET('/api/v1/market/global/overview', {
        params: { query: { window: selectedWindow.value } },
        signal,
      }),
    { access: 'read', signal: current.signal },
  )
  if (controller !== current || current.signal.aborted) return
  loading.value = false
  if (result.ok) overview.value = result.data
  else if (result.failure.kind !== 'aborted') failure.value = result.failure
}

watch(() => [selectedWindow.value, reloadKey.value] as const, load, { immediate: true })

onBeforeUnmount(() => {
  controller?.abort()
})
</script>

<template>
  <div class="global-page">
    <section class="hero panel">
      <div class="hero-copy">
        <span class="eyebrow">跨市场观察</span>
        <h1>全球市场一览</h1>
        <p>美股、日韩、中国成长板块与商品放在同一张风险地图里，先看方向，再回到个股。</p>
      </div>
      <dl class="breadth" aria-label="全球市场涨跌统计">
        <div>
          <dt>上涨</dt>
          <dd class="num up">{{ breadth.advancing }}</dd>
        </div>
        <div>
          <dt>下跌</dt>
          <dd class="num down">{{ breadth.declining }}</dd>
        </div>
        <div>
          <dt>平盘</dt>
          <dd class="num flat">{{ breadth.flat }}</dd>
        </div>
        <div>
          <dt>不可用</dt>
          <dd class="num" :class="{ warn: breadth.unavailable }">{{ breadth.unavailable }}</dd>
        </div>
      </dl>
      <div class="hero-actions">
        <div class="window-switch" aria-label="趋势窗口">
          <button
            v-for="windowDays in supportedWindows"
            :key="windowDays"
            type="button"
            :class="{ active: selectedWindow === windowDays }"
            :aria-pressed="selectedWindow === windowDays"
            @click="setWindow(windowDays)"
          >
            {{ windowDays }} 日
          </button>
        </div>
        <button
          type="button"
          class="refresh"
          :disabled="loading"
          aria-label="刷新全球市场数据"
          @click="reloadKey += 1"
        >
          <AppIcon name="refresh" :size="14" />
          {{ loading ? '读取中' : '刷新' }}
        </button>
      </div>
      <p class="hero-time">
        <span class="live-dot" :class="{ pulsing: loading }" />
        {{
          overview?.as_of
            ? `最近报价 ${formatMarketTime(overview.as_of)} · 同步 ${formatMarketTime(overview.last_synced_at)} · 北京时间`
            : '等待报价时间'
        }}
      </p>
    </section>

    <section v-if="failure" class="banner banner--error" role="alert">
      <strong>{{ failureText(failure) }}</strong>
      <span v-if="failure.requestId">请求编号 {{ failure.requestId }}</span>
      <button type="button" class="banner-button" @click="reloadKey += 1">重试</button>
    </section>
    <section v-else-if="overview?.stale" class="banner banner--warn" role="status">
      <strong>外网刷新失败，当前显示最近成功同步的本地快照。</strong>
      <span>{{ formatMarketTime(overview.last_synced_at) }}</span>
      <button type="button" class="banner-button" @click="reloadKey += 1">重试更新</button>
    </section>

    <div v-if="loading && !overview" class="loading-grid" aria-live="polite">
      <div v-for="index in 6" :key="index" class="skeleton">
        <span />
        <strong />
        <i />
      </div>
    </div>

    <template v-if="overview">
      <nav class="filters" aria-label="市场分组">
        <button
          v-for="option in filterOptions"
          :key="option.key"
          type="button"
          :class="{ active: activeGroup === option.key }"
          :aria-pressed="activeGroup === option.key"
          @click="activeGroup = option.key"
        >
          {{ option.label }}
          <span class="num">{{ option.count }}</span>
        </button>
        <span v-if="issueCount" class="issue-note">
          <AppIcon name="alert-triangle" :size="13" />
          {{ issueCount }} 项部分可用
        </span>
      </nav>

      <div class="market-grid">
        <article
          v-for="(item, index) in visibleItems"
          :key="item.key"
          class="market-card"
          :class="[`market-card--${item.group}`, { partial: item.assessment !== 'available' }]"
          :style="{ '--stagger': `${index * 45}ms` }"
          role="button"
          tabindex="0"
          :aria-label="`${item.name} 打开日 K 线`"
          @click="openItem(item)"
          @keydown.enter.prevent="openItem(item)"
          @keydown.space.prevent="openItem(item)"
        >
          <header class="card-head">
            <span class="identity">
              <b>{{ item.name }}</b>
              <code>{{ item.symbol }}</code>
            </span>
            <span class="venue">{{ item.market }} · {{ item.currency }}</span>
          </header>

          <div class="price-row">
            <strong class="num" :class="tone(item)">
              {{ formatNumber(item.quote?.price, item.precision) }}
            </strong>
            <span class="num" :class="tone(item)">
              {{ formatSignedPercent(item.quote?.change_pct) }}
            </span>
          </div>
          <span class="unit">{{ item.unit }} · 较前收</span>

          <MarketSparkline
            v-if="itemBars(item).length"
            :values="closes(item)"
            :height="56"
            :label="`${item.name}最近 ${itemBars(item).length} 个交易日走势`"
            :color="`var(--${tone(item)})`"
          />
          <span v-else class="spark-empty">趋势数据暂不可用</span>

          <dl class="session-kv">
            <div>
              <dt>开盘</dt>
              <dd class="num">{{ formatNumber(item.quote?.open, item.precision) }}</dd>
            </div>
            <div>
              <dt>最高</dt>
              <dd class="num">{{ formatNumber(item.quote?.high, item.precision) }}</dd>
            </div>
            <div>
              <dt>最低</dt>
              <dd class="num">{{ formatNumber(item.quote?.low, item.precision) }}</dd>
            </div>
          </dl>

          <footer class="card-foot">
            <span>{{ formatMarketTime(item.quote?.quote_time) }}</span>
            <span v-if="itemIssues(item).length" class="partial-label">部分可用</span>
            <span v-else>{{ itemBars(item).length }} 日趋势 ›</span>
          </footer>
          <p v-if="itemIssues(item).length" class="card-issue">
            {{ itemIssues(item)[0]?.message }}
          </p>
        </article>
      </div>

      <footer class="source-note">
        <AppIcon name="info" :size="14" />
        <span>{{ overview.methodology }}</span>
      </footer>
    </template>

    <ReviewDrawer
      :open="selectedItem !== null"
      :title="selectedItem?.name ?? '市场详情'"
      :meta="
        selectedItem
          ? `${selectedItem.symbol} · ${selectedItem.market} · ${selectedItem.currency}`
          : ''
      "
      variant="modal"
      modal-size="chart"
      @close="closeDetail"
    >
      <GlobalMarketDetail v-if="selectedItem" :item="selectedItem" />
    </ReviewDrawer>
  </div>
</template>

<style scoped>
.global-page {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel,
.market-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.hero {
  position: relative;
  overflow: hidden;
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(280px, 1.5fr) minmax(280px, 0.9fr) auto;
  align-items: center;
  gap: 22px 28px;
  background:
    radial-gradient(
      circle at 8% 0,
      color-mix(in oklab, var(--brand) 16%, transparent),
      transparent 34%
    ),
    radial-gradient(
      circle at 74% 110%,
      color-mix(in oklab, var(--accent) 10%, transparent),
      transparent 38%
    ),
    var(--surface);
}

.hero::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.26;
  background-image:
    linear-gradient(var(--border) 1px, transparent 1px),
    linear-gradient(90deg, var(--border) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(90deg, transparent 28%, black 78%, transparent);
}

.hero-copy,
.breadth,
.hero-actions,
.hero-time {
  position: relative;
  z-index: 1;
}

.eyebrow {
  color: var(--brand);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.hero h1 {
  margin: 5px 0 7px;
  font-size: clamp(24px, 2.2vw, 36px);
  line-height: 1.1;
  letter-spacing: -0.04em;
}

.hero-copy p {
  max-width: 560px;
  margin: 0;
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.7;
}

.breadth {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(54px, 1fr));
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: color-mix(in oklab, var(--surface2) 82%, transparent);
}

.breadth div {
  padding: 10px 8px;
  text-align: center;
}

.breadth div + div {
  border-left: 1px solid var(--border);
}

.breadth dt {
  color: var(--muted);
  font-size: 9.5px;
}

.breadth dd {
  margin: 1px 0 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.window-switch {
  padding: 3px;
  display: flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface2);
}

.window-switch button,
.refresh,
.filters button,
.banner-button {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}

.window-switch button {
  padding: 5px 7px;
  font-family: var(--mono);
  font-size: 10px;
}

.window-switch button.active {
  background: var(--surface3);
  color: var(--fg);
  box-shadow: inset 0 0 0 1px var(--border2);
}

.refresh {
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--surface2);
  color: var(--fg2);
  font-size: 11px;
}

.refresh:disabled {
  opacity: 0.45;
  cursor: wait;
}

.hero-time {
  grid-column: 1 / -1;
  margin: -8px 0 0;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: var(--mono);
  font-size: 10px;
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--down);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--down) 14%, transparent);
}

.live-dot.pulsing {
  animation: pulse-dot 900ms ease-in-out infinite alternate;
}

.banner {
  padding: 11px 14px;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  font-size: 12px;
}

.banner--error {
  border: 1px solid color-mix(in oklab, var(--up) 36%, var(--border));
  background: color-mix(in oklab, var(--up) 9%, transparent);
  color: var(--up);
}

.banner--warn {
  border: 1px solid color-mix(in oklab, var(--warn) 36%, var(--border));
  background: color-mix(in oklab, var(--warn) 9%, transparent);
  color: var(--warn);
}

.banner span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
}

.banner-button {
  min-height: 30px;
  margin-left: auto;
  padding: 3px 9px;
  border: 1px solid currentColor;
  color: inherit;
  font-size: 11px;
}

.loading-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.skeleton {
  min-height: 218px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  display: grid;
  align-content: start;
  gap: 14px;
}

.skeleton span,
.skeleton strong,
.skeleton i {
  display: block;
  border-radius: 6px;
  background: linear-gradient(
    90deg,
    var(--surface2),
    color-mix(in oklab, var(--surface3) 70%, var(--surface2)),
    var(--surface2)
  );
  background-size: 200% 100%;
  animation: shimmer 1.2s linear infinite;
}

.skeleton span {
  width: 44%;
  height: 12px;
}

.skeleton strong {
  width: 64%;
  height: 34px;
}

.skeleton i {
  width: 100%;
  height: 72px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.filters button {
  min-height: 31px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
}

.filters button span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
}

.filters button.active {
  border-color: color-mix(in oklab, var(--brand) 52%, var(--border));
  background: color-mix(in oklab, var(--brand) 10%, var(--surface));
  color: var(--fg);
}

.issue-note {
  margin-left: auto;
  color: var(--warn);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.market-card {
  --group-color: var(--accent);
  position: relative;
  min-width: 0;
  overflow: hidden;
  padding: 12px 13px 11px;
  background:
    linear-gradient(
      145deg,
      color-mix(in oklab, var(--group-color) 5%, transparent),
      transparent 44%
    ),
    var(--surface);
  color: var(--fg);
  text-align: left;
  cursor: pointer;
  animation: reveal 380ms var(--ease) both;
  animation-delay: var(--stagger);
  transition:
    border-color var(--duration),
    transform var(--duration),
    box-shadow var(--duration);
}

.market-card--asia {
  --group-color: var(--warn);
}

.market-card--cn {
  --group-color: var(--brand);
}

.market-card--commodity {
  --group-color: var(--brand2);
}

.market-card:hover {
  border-color: color-mix(in oklab, var(--group-color) 45%, var(--border2));
  transform: translateY(-2px);
  box-shadow:
    0 1px 0 color-mix(in oklab, var(--fg) 4%, transparent),
    0 16px 34px color-mix(in oklab, var(--bg) 74%, transparent);
}

.market-card:focus-visible {
  outline: 2px solid color-mix(in oklab, var(--group-color) 74%, white);
  outline-offset: 2px;
}

.market-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--group-color);
  opacity: 0.72;
}

.market-card.partial {
  border-style: dashed;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.identity {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.identity b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.identity code,
.venue {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
}

.venue {
  flex: 0 0 auto;
  padding: 2px 5px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: color-mix(in oklab, var(--surface2) 70%, transparent);
}

.price-row {
  margin-top: 10px;
  display: flex;
  align-items: baseline;
  gap: 9px;
}

.price-row strong {
  font-size: clamp(19px, 1.5vw, 24px);
  line-height: 1.05;
  letter-spacing: -0.035em;
}

.price-row span {
  font-size: 11.5px;
  font-weight: 650;
}

.unit {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 9.5px;
}

.market-card > :deep(.spark-host) {
  margin-top: 9px;
}

.spark-empty {
  min-height: 56px;
  margin-top: 9px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 10px;
}

.session-kv {
  margin: 9px 0 0;
  padding: 7px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  display: grid;
  grid-template-columns: repeat(3, 1fr);
}

.session-kv div {
  display: grid;
  gap: 1px;
}

.session-kv div + div {
  padding-left: 8px;
  border-left: 1px solid var(--border);
}

.session-kv dt {
  color: var(--muted);
  font-size: 8.5px;
}

.session-kv dd {
  margin: 0;
  color: var(--fg2);
  font-family: var(--mono);
  font-size: 10px;
}

.card-foot {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 8.5px;
}

.partial-label {
  color: var(--warn);
  font-family: var(--font);
  font-weight: 650;
}

.card-issue {
  margin: 6px 0 0;
  color: color-mix(in oklab, var(--warn) 74%, var(--muted));
  font-size: 9.5px;
  line-height: 1.5;
}

.warn {
  color: var(--warn);
}

.source-note {
  padding: 9px 2px 0;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.6;
}

@keyframes shimmer {
  to {
    background-position: -200% 0;
  }
}

@keyframes reveal {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse-dot {
  from {
    opacity: 0.4;
  }
  to {
    opacity: 1;
  }
}

@media (max-width: 1600px) {
  .market-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 1180px) {
  .hero {
    grid-template-columns: minmax(0, 1.4fr) minmax(250px, 0.8fr);
  }

  .hero-actions {
    grid-column: 1 / -1;
    justify-content: flex-end;
  }

  .market-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .market-grid,
  .loading-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .global-page {
    gap: 13px;
  }

  .hero {
    padding: 18px 16px;
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .breadth {
    width: 100%;
  }

  .hero-actions {
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .hero-time {
    grid-column: auto;
    margin-top: -4px;
  }

  .market-grid,
  .loading-grid {
    grid-template-columns: 1fr;
  }

  .issue-note {
    width: 100%;
    margin-left: 0;
  }
}
</style>
