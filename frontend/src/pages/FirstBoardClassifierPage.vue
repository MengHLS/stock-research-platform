<script setup lang="ts">
import AppIcon from '../components/AppIcon'
import FirstBoardDailyEvents from '../components/FirstBoardDailyEvents.vue'
import {
  SHORT_PATH_OPTIONS,
  TREND_OPTIONS,
  positionScopeLabel,
} from '../market/first-board-classifier'
import { useFirstBoardClassifierPage } from '../market/useFirstBoardClassifierPage'

const {
  catalog,
  catalogFailure,
  catalogLoading,
  position,
  trend,
  shortPath,
  result,
  classifyFailure,
  classifying,
  stockCode,
  eventDate,
  events,
  eventsFailure,
  eventsLoading,
  selectedCode,
  selectedGroup,
  failureText,
  classesFor,
  positionBandLabel,
  loadCatalog,
  classify,
  loadEvents,
} = useFirstBoardClassifierPage()
</script>

<template>
  <div class="classifier-page">
    <section class="hero">
      <div class="hero__copy">
        <span class="eyebrow">FIRST BOARD / BACKGROUND TAXONOMY</span>
        <h1>首板背景分类</h1>
        <p>
          把首板发生前的 60 日位置、趋势方向与短期路径映射为 16 个互斥背景类。 新编号不与原
          G1～G5/R1/U1 混用；旧明细码只作追溯。
        </p>
      </div>
      <div class="hero__facts" aria-label="分类器口径">
        <div><b>16</b><span>互斥明细类</span></div>
        <div><b>7</b><span>背景族</span></div>
        <div><b>T-1</b><span>信息截止</span></div>
        <div><b>0</b><span>未来收益输入</span></div>
      </div>
    </section>

    <div v-if="catalogFailure" class="banner banner--error" role="alert">
      <AppIcon name="alert-triangle" :size="16" />
      <div>
        <strong>{{ failureText(catalogFailure) }}</strong>
        <p v-if="catalogFailure.requestId">请求编号 {{ catalogFailure.requestId }}</p>
      </div>
      <button type="button" class="btn" :disabled="catalogLoading" @click="loadCatalog">
        重试
      </button>
    </div>
    <div v-else-if="catalogLoading && !catalog" class="loading-sheet" aria-live="polite">
      正在读取分类口径…
    </div>

    <div v-if="catalog" class="workspace">
      <aside class="probe">
        <div class="probe__head">
          <span class="eyebrow">CLASSIFY ONE EVENT</span>
          <h2>背景轴试算</h2>
          <p>输入截至 T-1 的已冻结轴值。这里不读取个股行情，也不计算收益。</p>
        </div>

        <form class="probe__form" @submit.prevent="classify">
          <label class="field">
            <span>60 日相对位置 <small>0–100，可留空</small></span>
            <input
              v-model="position"
              type="number"
              inputmode="decimal"
              min="0"
              max="100"
              step="0.01"
              placeholder="例如 62.5"
            />
          </label>
          <label class="field">
            <span>趋势方向</span>
            <select v-model="trend">
              <option v-for="option in TREND_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>短期路径</span>
            <select v-model="shortPath">
              <option
                v-for="option in SHORT_PATH_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </label>
          <button type="submit" class="btn btn--primary" :disabled="classifying">
            <AppIcon name="target" :size="15" />
            {{ classifying ? '分类中…' : '确定背景类' }}
          </button>
        </form>

        <div v-if="classifyFailure" class="probe__error" role="alert">
          <strong>{{ failureText(classifyFailure) }}</strong>
          <span v-if="classifyFailure.requestId"> 请求编号 {{ classifyFailure.requestId }} </span>
        </div>

        <article v-if="result" class="result-card">
          <span class="result-card__code">{{ result.class_code }}</span>
          <h3>{{ result.class_name }}</h3>
          <p class="result-card__group">{{ result.group_code }} · {{ result.group_name }}</p>
          <dl>
            <div>
              <dt>位置</dt>
              <dd>{{ positionBandLabel(result.position_band) }}</dd>
            </div>
            <div>
              <dt>原明细码</dt>
              <dd>{{ result.source_detail_code }}</dd>
            </div>
            <div>
              <dt>输入时点</dt>
              <dd>{{ result.classification_cutoff }}（调用方声明）</dd>
            </div>
          </dl>
          <p class="result-card__note">{{ result.explanation }}</p>
        </article>

        <div class="boundaries">
          <span>位置边界</span>
          <p>
            LOW ≤ {{ catalog.low_position_max_pct }}% ＜ MID ＜ {{ catalog.high_position_min_pct }}%
            ≤ HIGH
          </p>
          <span>分类版本</span>
          <code>{{ catalog.taxonomy_version }}</code>
        </div>
      </aside>

      <main class="taxonomy">
        <FirstBoardDailyEvents />
        <section class="event-search">
          <div class="event-search__head">
            <div>
              <span class="eyebrow">FROZEN EVENT LEDGER</span>
              <h2>查询真实首板事件</h2>
            </div>
            <span>只读冻结账本</span>
          </div>
          <form class="event-search__form" @submit.prevent="loadEvents">
            <label class="field">
              <span>股票代码</span>
              <input
                v-model="stockCode"
                type="text"
                maxlength="9"
                pattern="[0-9]{6}(\.(SH|SZ|BJ))?"
                required
                placeholder="603121 或 603121.SH"
              />
            </label>
            <label class="field">
              <span>首板日期 <small>可留空</small></span>
              <input v-model="eventDate" type="date" />
            </label>
            <button class="btn" type="submit" :disabled="eventsLoading">
              <AppIcon name="search" :size="14" />
              {{ eventsLoading ? '校验并读取中…' : '查询事件' }}
            </button>
          </form>
          <div v-if="eventsFailure" class="probe__error" role="alert">
            <strong>{{ failureText(eventsFailure) }}</strong>
            <span v-if="eventsFailure.requestId">请求编号 {{ eventsFailure.requestId }}</span>
          </div>
          <template v-if="events">
            <p class="event-search__source">
              Dataset {{ events.source.dataset_version_id }} ·
              {{ events.source.event_count.toLocaleString() }} 个事件通过全量映射校验 · 本次找到
              {{ events.total }} 个
            </p>
            <div v-if="events.items.length" class="event-list">
              <article v-for="item in events.items" :key="item.event_id" class="event-row">
                <time>{{ item.event_date }}</time>
                <div>
                  <strong>{{ item.class_code }} · {{ item.class_name }}</strong>
                  <span>
                    {{ item.group_code }} · {{ positionBandLabel(item.position_band) }}
                    <template v-if="item.position_60d_pct !== null">
                      {{ Number(item.position_60d_pct).toFixed(2) }}%
                    </template>
                    · 原 {{ item.source_detail_code }}
                  </span>
                </div>
              </article>
            </div>
            <p v-else class="event-search__empty">冻结账本中没有符合条件的首板事件。</p>
          </template>
        </section>

        <section class="method-strip">
          <div>
            <span class="eyebrow">READING NOTES</span>
            <h2>命名改了什么</h2>
          </div>
          <p>
            新名称写出“位置 + 趋势 +
            短期路径”，不再用“回撤后”“上涨延续”这类容易被读成结果判断的简称。 “整体方向未明确”保留原
            SIDEWAYS 的残差含义。
          </p>
        </section>

        <div class="notes">
          <p v-for="note in catalog.notes" :key="note">{{ note }}</p>
        </div>

        <section class="group-list" aria-label="七组十六个首板背景分类">
          <article
            v-for="group in catalog.groups"
            :key="group.code"
            class="group-card"
            :class="{ 'group-card--selected': selectedGroup === group.code }"
          >
            <header class="group-card__head">
              <div class="group-card__index">
                <span>{{ group.code }}</span>
                <small>{{ group.class_codes.length }} 类</small>
              </div>
              <div>
                <h3>{{ group.name }}</h3>
                <p>{{ group.description }}</p>
              </div>
              <code>{{ group.source_group_code }}</code>
            </header>

            <div class="class-list">
              <div
                v-for="item in classesFor(group.code)"
                :key="item.code"
                class="class-row"
                :class="{ 'class-row--selected': selectedCode === item.code }"
              >
                <span class="class-row__code">{{ item.code }}</span>
                <div class="class-row__name">
                  <strong>{{ item.name }}</strong>
                  <span>{{ item.condition }}</span>
                </div>
                <span class="scope">{{ positionScopeLabel(item.position_scope) }}</span>
                <span class="legacy">{{ item.source_detail_code }}</span>
              </div>
            </div>
          </article>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.classifier-page {
  display: grid;
  gap: 18px;
  max-width: 1500px;
  margin: 0 auto;
}

.hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 28px;
  overflow: hidden;
  padding: 26px 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(
      circle at 88% 18%,
      color-mix(in oklab, var(--brand) 16%, transparent),
      transparent 34%
    ),
    linear-gradient(118deg, var(--surface) 0%, var(--surface2) 62%, var(--surface) 100%);
  box-shadow: var(--shadow);
}

.hero::after {
  position: absolute;
  inset: auto 0 0;
  height: 2px;
  content: '';
  background: linear-gradient(90deg, var(--brand), var(--warn), transparent 84%);
}

.eyebrow {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.16em;
}

h1,
h2,
h3,
p {
  margin: 0;
}

.hero h1 {
  margin-top: 6px;
  font-size: clamp(28px, 4vw, 46px);
  font-weight: 600;
  letter-spacing: -0.03em;
}

.hero__copy p {
  max-width: 720px;
  margin-top: 12px;
  color: var(--fg2);
  font-size: 14px;
  line-height: 1.85;
}

.hero__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(92px, 1fr));
  align-self: center;
  min-width: 220px;
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  background: color-mix(in oklab, var(--bg2) 72%, transparent);
}

.hero__facts div {
  display: grid;
  gap: 1px;
  padding: 14px 16px;
}

.hero__facts div:nth-child(odd) {
  border-right: 1px solid var(--border);
}

.hero__facts div:nth-child(-n + 2) {
  border-bottom: 1px solid var(--border);
}

.hero__facts b {
  color: var(--fg);
  font-family: var(--mono);
  font-size: 24px;
  font-weight: 500;
  white-space: nowrap;
}

.hero__facts span {
  color: var(--muted);
  font-size: 11px;
}

.banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 13px 15px;
  border-radius: var(--radius);
  font-size: 13px;
}

.banner p {
  margin-top: 4px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 11px;
}

.banner .btn {
  margin-left: auto;
}

.banner--error {
  border: 1px solid color-mix(in oklab, var(--up) 34%, transparent);
  background: color-mix(in oklab, var(--up) 10%, transparent);
}

.loading-sheet {
  padding: 48px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  color: var(--muted);
  text-align: center;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(280px, 330px) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.probe {
  position: sticky;
  top: 74px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.probe h2 {
  margin-top: 5px;
  font-size: 20px;
  font-weight: 600;
}

.probe__head > p {
  margin-top: 8px;
  color: var(--fg2);
  font-size: 12px;
  line-height: 1.75;
}

.probe__form {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.field {
  display: grid;
  gap: 6px;
}

.field > span {
  color: var(--fg2);
  font-size: 12px;
}

.field small {
  color: var(--muted);
  font-size: 10px;
}

.field input,
.field select {
  width: 100%;
  min-height: 38px;
  padding: 8px 10px;
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  outline: none;
  background: var(--surface2);
  color: var(--fg);
  font: 12px var(--font);
}

.field input:focus,
.field select:focus {
  border-color: var(--accent);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 36px;
  padding: 7px 12px;
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  font-size: 12px;
  cursor: pointer;
}

.btn--primary {
  border-color: color-mix(in oklab, var(--brand) 62%, var(--border2));
  background: color-mix(in oklab, var(--brand) 18%, var(--surface2));
  color: var(--fg);
}

.btn:hover:not(:disabled) {
  border-color: var(--brand);
  color: var(--fg);
}

.btn:disabled {
  cursor: progress;
  opacity: 0.6;
}

.probe__error {
  display: grid;
  gap: 4px;
  margin-top: 12px;
  padding: 10px;
  border: 1px solid color-mix(in oklab, var(--up) 32%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in oklab, var(--up) 8%, transparent);
  color: var(--up);
  font-size: 12px;
}

.probe__error span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
}

.result-card {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid color-mix(in oklab, var(--accent) 42%, var(--border));
  border-radius: var(--radius);
  background: linear-gradient(
    145deg,
    color-mix(in oklab, var(--accent) 8%, var(--surface2)),
    var(--surface)
  );
}

.result-card__code {
  color: var(--accent);
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.result-card h3 {
  margin-top: 5px;
  font-size: 16px;
  font-weight: 600;
}

.result-card__group {
  margin-top: 4px;
  color: var(--warn);
  font-size: 11px;
}

.result-card dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0 0;
}

.result-card dl div {
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.result-card dt {
  color: var(--muted);
  font-size: 9px;
}

.result-card dd {
  margin: 3px 0 0;
  font-size: 11px;
}

.result-card__note {
  margin-top: 11px;
  color: var(--fg2);
  font-size: 11px;
  line-height: 1.7;
}

.boundaries {
  display: grid;
  gap: 4px;
  margin-top: 15px;
  padding-top: 12px;
  border-top: 1px dashed var(--border2);
  color: var(--muted);
  font-size: 10px;
}

.boundaries p {
  color: var(--fg2);
}

.boundaries code {
  color: var(--accent);
  font-family: var(--mono);
}

.taxonomy {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.event-search {
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.event-search__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.event-search__head h2 {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 600;
}

.event-search__head > span {
  color: var(--muted);
  font-size: 10px;
}

.event-search__form {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(150px, 1fr) auto;
  gap: 12px;
  align-items: end;
  margin-top: 12px;
}

.event-search__form .btn {
  min-height: 38px;
}

.event-search__source {
  margin-top: 12px;
  color: var(--muted);
  font-size: 10px;
}

.event-list {
  max-height: 300px;
  overflow: auto;
  margin-top: 8px;
  border-top: 1px solid var(--border);
}

.event-row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--grid);
}

.event-row time {
  color: var(--accent);
  font-family: var(--mono);
  font-size: 11px;
}

.event-row div {
  display: grid;
  gap: 3px;
}

.event-row strong {
  font-size: 12px;
  font-weight: 500;
}

.event-row span,
.event-search__empty {
  color: var(--muted);
  font-size: 10px;
}

.event-search__empty {
  padding: 18px 0 2px;
}

.method-strip {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
  gap: 24px;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.method-strip h2 {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 600;
}

.method-strip p {
  color: var(--fg2);
  font-size: 12px;
  line-height: 1.8;
}

.notes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px 18px;
  padding: 0 2px;
}

.notes p {
  position: relative;
  padding-left: 12px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.65;
}

.notes p::before {
  position: absolute;
  top: 0.66em;
  left: 0;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--warn);
  content: '';
}

.group-list {
  display: grid;
  gap: 12px;
}

.group-card {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  transition:
    border-color var(--duration) var(--ease),
    transform var(--duration) var(--ease);
}

.group-card--selected {
  border-color: color-mix(in oklab, var(--accent) 55%, var(--border));
  transform: translateX(3px);
}

.group-card__head {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr) auto;
  gap: 15px;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(90deg, var(--surface2), var(--surface));
}

.group-card__index {
  display: grid;
  gap: 2px;
}

.group-card__index span {
  color: var(--brand);
  font-family: var(--mono);
  font-size: 13px;
}

.group-card__index small {
  color: var(--muted);
  font-size: 10px;
}

.group-card__head h3 {
  font-size: 15px;
  font-weight: 600;
}

.group-card__head p {
  margin-top: 3px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}

.group-card__head > code,
.legacy {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 10px;
}

.class-row {
  display: grid;
  grid-template-columns: 70px minmax(0, 1fr) 92px 58px;
  gap: 12px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--grid);
  transition: background var(--duration) var(--ease);
}

.class-row:last-child {
  border-bottom: 0;
}

.class-row:hover,
.class-row--selected {
  background: color-mix(in oklab, var(--accent) 7%, transparent);
}

.class-row--selected {
  box-shadow: inset 3px 0 0 var(--accent);
}

.class-row__code {
  color: var(--accent);
  font-family: var(--mono);
  font-size: 11px;
}

.class-row__name {
  display: grid;
  gap: 2px;
}

.class-row__name strong {
  color: var(--fg);
  font-size: 12px;
  font-weight: 500;
}

.class-row__name span {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
}

.scope {
  justify-self: start;
  padding: 2px 7px;
  border: 1px solid var(--border2);
  border-radius: 999px;
  color: var(--fg2);
  font-size: 9px;
}

.legacy {
  text-align: right;
}

@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: minmax(0, 1fr);
  }

  .probe {
    position: static;
  }

  .probe__form {
    grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
    align-items: end;
  }

  .probe__form .btn {
    min-height: 38px;
  }
}

@media (max-width: 760px) {
  .hero {
    grid-template-columns: minmax(0, 1fr);
    padding: 20px;
  }

  .hero__facts {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    min-width: 0;
  }

  .hero__facts div:nth-child(n) {
    padding: 12px 8px;
    border-right: 1px solid var(--border);
    border-bottom: 0;
  }

  .hero__facts div:last-child {
    border-right: 0;
  }

  .hero__facts b {
    font-size: 20px;
  }

  .probe__form,
  .event-search__form,
  .notes,
  .method-strip {
    grid-template-columns: minmax(0, 1fr);
  }

  .group-card__head {
    grid-template-columns: 76px minmax(0, 1fr);
  }

  .group-card__head > code {
    display: none;
  }

  .class-row {
    grid-template-columns: 62px minmax(0, 1fr) auto;
    gap: 8px;
    padding: 10px 12px;
  }

  .scope {
    grid-column: 2;
    justify-self: start;
  }

  .legacy {
    grid-column: 3;
    grid-row: 1;
  }
}
</style>
