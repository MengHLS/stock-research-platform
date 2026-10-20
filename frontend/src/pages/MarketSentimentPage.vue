<script setup lang="ts">
import AppIcon from '../components/AppIcon'
import MarketReviewControls from '../components/market/MarketReviewControls.vue'
import MarketSentimentLeaders from '../components/market/MarketSentimentLeaders.vue'
import MarketSentimentTimeline from '../components/market/MarketSentimentTimeline.vue'
import MarketSentimentTrendPanel from '../components/market/MarketSentimentTrendPanel.vue'
import ReviewDrawer from '../components/market/ReviewDrawer.vue'
import StockDetailContent from '../components/market/StockDetailContent.vue'
import { useMarketSentimentPage } from '../market/useMarketSentimentPage'

const {
  context,
  overview,
  contextFailure,
  overviewFailure,
  localDateError,
  loading,
  reloadKey,
  drawerOpen,
  drawerLoading,
  drawerFailure,
  drawerMessage,
  selectedLeader,
  selectedRow,
  peerRows,
  drawer,
  notes,
  maximumWindow,
  windowOptions,
  selectedWindow,
  selectedDate,
  history,
  showInitialLoading,
  drawerTitle,
  drawerMeta,
  noteKey,
  failureText,
  chooseDate,
  chooseWindow,
  goDate,
  resetToLatest,
  closeDrawer,
  openLeader,
  selectStockFromDetail,
  saveNote,
} = useMarketSentimentPage()
</script>

<template>
  <div class="sentiment-page">
    <section v-if="!overview && (context || localDateError)" class="fallback-controls panel">
      <MarketReviewControls
        :context="context"
        :value="context?.requested_date ?? context?.default_date ?? ''"
        :window-value="selectedWindow"
        :window-options="windowOptions"
        :loading="loading"
        :show-window="false"
        @date="chooseDate"
        @previous="goDate(context?.previous_trading_day)"
        @next="goDate(context?.next_trading_day)"
        @latest="resetToLatest"
        @reload="reloadKey += 1"
      />
    </section>

    <section v-if="localDateError" class="banner banner--warn" role="alert">
      {{ localDateError }}
      <button type="button" class="small-button" @click="resetToLatest">查看最近有记录日</button>
    </section>
    <section v-else-if="contextFailure" class="banner banner--error" role="alert">
      <strong>{{ failureText(contextFailure) }}</strong>
      <span v-if="contextFailure.requestId">请求编号 {{ contextFailure.requestId }}</span>
      <button type="button" class="small-button" @click="reloadKey += 1">重试</button>
    </section>
    <section
      v-else-if="context && context.requested_date_known === false"
      class="banner banner--warn"
      role="alert"
    >
      {{ context.requested_date }} 未被交易日数据收录；页面没有自动替换成其他日期。
      <button v-if="context.default_date" type="button" class="small-button" @click="resetToLatest">
        查看 {{ context.default_date }}
      </button>
    </section>
    <section v-else-if="context && !context.default_date" class="banner banner--info">
      源内暂无可用的历史复盘日期。
    </section>

    <div v-if="showInitialLoading" class="loading-panel panel" aria-live="polite">
      正在读取 {{ selectedDate || '最近交易日' }} 的情绪周期数据…
    </div>

    <section v-if="overviewFailure" class="banner banner--error" role="alert">
      <strong>{{ failureText(overviewFailure) }}</strong>
      <span v-if="overviewFailure.requestId">请求编号 {{ overviewFailure.requestId }}</span>
      <button type="button" class="small-button" @click="reloadKey += 1">重新读取情绪周期</button>
    </section>

    <template v-if="overview">
      <MarketSentimentTrendPanel
        :history="history"
        :selected-date="overview.date"
        :window-value="selectedWindow"
        :window-options="windowOptions"
        :window-requested="overview.window_requested"
        :window-actual="overview.window_actual"
        @window="chooseWindow"
        @select="chooseDate"
      >
        <template #controls>
          <MarketReviewControls
            :context="context"
            :value="overview.date"
            :window-value="selectedWindow"
            :window-options="windowOptions"
            :loading="loading"
            :show-window="false"
            @date="chooseDate"
            @previous="goDate(context?.previous_trading_day)"
            @next="goDate(context?.next_trading_day)"
            @latest="resetToLatest"
            @reload="reloadKey += 1"
          />
        </template>
      </MarketSentimentTrendPanel>

      <MarketSentimentTimeline
        :history="history"
        :selected-date="overview.date"
        @select="chooseDate"
      />

      <MarketSentimentLeaders
        :ladder="overview.ladder"
        :date="overview.date"
        @select="openLeader"
      />

      <details v-if="overview.issues.length" class="issues">
        <summary>
          <AppIcon name="alert-triangle" :size="14" />
          {{ overview.issues.length }} 条数据口径与缺失提示
        </summary>
        <ul>
          <li v-for="issue in overview.issues" :key="`${issue.code}-${issue.scope}`">
            <code>{{ issue.code }}</code>
            <span>{{ issue.message }}</span>
            <em>{{ issue.scope }}</em>
          </li>
        </ul>
      </details>
    </template>

    <ReviewDrawer
      ref="drawer"
      :open="drawerOpen"
      :title="drawerTitle"
      :meta="drawerMeta"
      variant="modal"
      modal-size="detail"
      @close="closeDrawer"
    >
      <div v-if="drawerLoading" class="drawer-state">
        正在读取 {{ overview?.date ?? selectedDate }} 的股票记录…
      </div>
      <div v-else-if="drawerFailure" class="drawer-state drawer-state--error" role="alert">
        <span>{{ failureText(drawerFailure) }}</span>
        <span v-if="drawerFailure.requestId" class="request-id">
          请求编号 {{ drawerFailure.requestId }}
        </span>
        <button
          v-if="selectedLeader"
          type="button"
          class="small-button"
          @click="openLeader(selectedLeader)"
        >
          重试股票明细
        </button>
      </div>
      <div v-else-if="drawerMessage" class="drawer-state">{{ drawerMessage }}</div>
      <StockDetailContent
        v-else-if="selectedRow"
        :row="selectedRow"
        :peer-rows="peerRows"
        :window-max="maximumWindow"
        :note="notes[noteKey] ?? ''"
        @select="selectStockFromDetail"
        @save-note="saveNote"
      />
    </ReviewDrawer>
  </div>
</template>

<style scoped>
.sentiment-page {
  --review-pad: 18px;
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sentiment-page :deep(.panel) {
  border-color: color-mix(in oklab, var(--border) 86%, var(--fg) 14%);
  box-shadow:
    0 1px 0 color-mix(in oklab, var(--fg) 3%, transparent),
    0 12px 30px color-mix(in oklab, var(--bg) 72%, transparent);
}

.sentiment-page :deep(.panel-head) {
  min-height: 56px;
  padding: 14px var(--review-pad);
  background: color-mix(in oklab, var(--surface) 96%, var(--fg) 4%);
}

.sentiment-page :deep(.panel-head h2) {
  font-size: 15px;
  font-weight: 680;
  line-height: 1.25;
  letter-spacing: -0.012em;
}

.sentiment-page :deep(.panel-body) {
  padding: var(--review-pad);
}

.sentiment-page :deep(.controls) {
  flex: 0 1 auto;
}

.sentiment-page :deep(.chart-scroll) {
  overscroll-behavior-x: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}

.fallback-controls {
  padding: 9px 11px;
  display: flex;
  justify-content: flex-end;
}

.banner {
  padding: 11px 13px;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  font-size: 12px;
}

.banner span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10.5px;
}

.banner--warn {
  border: 1px solid color-mix(in oklab, var(--warn) 36%, var(--border));
  background: color-mix(in oklab, var(--warn) 10%, transparent);
  color: var(--warn);
}

.banner--error {
  border: 1px solid color-mix(in oklab, var(--up) 36%, var(--border));
  background: color-mix(in oklab, var(--up) 10%, transparent);
  color: var(--up);
}

.banner--info {
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--fg2);
}

.small-button {
  min-height: 30px;
  padding: 4px 9px;
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  background: transparent;
  color: inherit;
  font-size: 11px;
  cursor: pointer;
}

.loading-panel {
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 12px;
}

.drawer-state {
  padding: 26px 12px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}

.drawer-state--error {
  color: var(--up);
}

.request-id {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
  user-select: all;
}

.drawer-state .small-button {
  display: block;
  margin: 10px auto 0;
  color: var(--fg2);
}

.issues {
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--muted);
  font-size: 12px;
}

.issues summary {
  width: fit-content;
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}

.issues ul {
  margin: 8px 0 0;
  padding-left: 20px;
  display: grid;
  gap: 5px;
}

.issues li {
  display: grid;
  grid-template-columns: minmax(140px, auto) minmax(0, 1fr) auto;
  gap: 8px;
}

.issues code,
.issues em {
  color: var(--fg2);
  font-family: var(--mono);
  font-size: 11px;
  font-style: normal;
}

.issues span {
  color: var(--muted);
}

@media (max-width: 760px) {
  .sentiment-page {
    --review-pad: 14px;
    gap: 14px;
  }

  .sentiment-page :deep(.panel-head) {
    min-height: 0;
    padding-block: 12px;
  }

  .sentiment-page :deep(.panel-head h2) {
    font-size: 14px;
  }

  .issues li {
    grid-template-columns: 1fr;
    gap: 2px;
  }
}

@media (min-width: 2200px) {
  .sentiment-page {
    --review-pad: 22px;
  }
}
</style>
