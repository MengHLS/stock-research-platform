<script setup lang="ts">
/**
 * Public product page: what the platform is, what actually runs today, and what
 * it explicitly cannot do.
 *
 * Reached from the login screen's brand column and readable without a session
 * (route meta `public`), so a prospective user can judge the product before
 * asking for an invitation code.
 *
 * Every claim here is sourced from code in this repository:
 * - capability summaries and their facts: `product.ts` (describes shipped modules);
 * - implementation status and pending work: `navigation.ts`'s `implemented` flag
 *   and each route's `meta.pending`, so the roadmap cannot drift from the rail;
 * - version, exchange phase and data-source state: `PlatformStatus`, which reads
 *   the real `/health/live`, `/api/v1/market/session` and `/api/v1/market/sources`.
 *
 * No sample data, no counters that are not measured, no "coming soon" buttons.
 */
import { computed } from 'vue'

import AppIcon from '../components/AppIcon'
import BrandLogo from '../components/BrandLogo.vue'
import PlatformStatus from '../components/PlatformStatus.vue'
import { brand, brandMarkSizes } from '../brand'
import { navGroups } from '../navigation'
import { boundaries, capabilities } from '../product'
import { useAppearance } from '../stores/appearance'
import { useSession } from '../stores/session'

const appearance = useAppearance()
const session = useSession()

const allItems = computed(() => navGroups.flatMap((group) => group.items))
const liveItems = computed(() => allItems.value.filter((item) => item.implemented))
const plannedItems = computed(() => allItems.value.filter((item) => !item.implemented))

/**
 * The roadmap reads the same `implemented` flag the navigation rail renders, so
 * this page and the rail can never disagree about what is built.
 */
const roadmap = computed(() =>
  navGroups.map((group) => ({
    title: group.title,
    items: group.items.map((item) => ({ name: item.name, done: item.implemented })),
  })),
)
</script>

<template>
  <div class="about">
    <div class="about__glow" aria-hidden="true"></div>

    <header class="about__bar">
      <RouterLink to="/login" class="about__brand" :aria-label="`${brand.name} 登录页`">
        <BrandLogo :size="brandMarkSizes.railCompact" variant="plinth-compact" />
      </RouterLink>

      <div class="about__actions">
        <button
          type="button"
          class="about__icon"
          :aria-label="appearance.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
          @click="appearance.toggleTheme()"
        >
          <AppIcon :name="appearance.theme === 'dark' ? 'sun' : 'moon'" :size="18" />
        </button>
        <RouterLink v-if="session.isAuthenticated" to="/" class="about__cta">
          进入工作台
          <AppIcon name="arrow-right" :size="14" />
        </RouterLink>
        <RouterLink v-else to="/login" class="about__cta">
          登录
          <AppIcon name="arrow-right" :size="14" />
        </RouterLink>
      </div>
    </header>

    <main class="about__main">
      <section class="hero">
        <span class="eyebrow">ABOUT</span>
        <h1>
          先把<em>地基</em>打稳，<br />
          再谈研究。
        </h1>
        <p class="hero__lede">
          {{ brand.description }}。产品名"{{ brand.name }}"取自稳固基座：行情、竞价、模式目录与
          执行记录共用一套身份与服务端边界，页面只展示后端真正能提供的东西。
        </p>
        <div class="hero__meta">
          <span class="tag">{{ brand.latin }}</span>
          <span class="tag tag--ok">
            <AppIcon name="check" :size="12" />
            {{ liveItems.length }} 个入口已实现
          </span>
          <span class="tag">
            <AppIcon name="info" :size="12" />
            {{ plannedItems.length }} 个入口待开发
          </span>
        </div>
      </section>

      <section class="block" aria-labelledby="status-title">
        <div class="block__head">
          <h2 id="status-title">现在就能看到的真实状态</h2>
          <p>下面这些值来自正在运行的本服务，不是截图或示例数据。</p>
        </div>
        <PlatformStatus class="block__console" />
      </section>

      <section class="block" aria-labelledby="cap-title">
        <div class="block__head">
          <h2 id="cap-title">四块能力</h2>
          <p>每一条都对应仓库里已有的模块，不含规划中的功能。</p>
        </div>
        <div class="grid">
          <article v-for="item in capabilities" :key="item.id" class="cap">
            <span class="cap__icon"><AppIcon :name="item.icon" :size="17" /></span>
            <h3>{{ item.title }}</h3>
            <p>{{ item.summary }}</p>
            <ul>
              <li v-for="fact in item.facts" :key="fact">{{ fact }}</li>
            </ul>
          </article>
        </div>
      </section>

      <section class="block" aria-labelledby="roadmap-title">
        <div class="block__head">
          <h2 id="roadmap-title">已实现与待实施</h2>
          <p>
            与左侧导航同一份数据（<code>navigation.ts</code>）：标为待开发的入口在界面上也是
            可见但不可点击，不会假装能用。
          </p>
        </div>
        <div class="roadmap">
          <div v-for="group in roadmap" :key="group.title" class="roadmap__group">
            <h3>{{ group.title }}</h3>
            <ul>
              <li
                v-for="item in group.items"
                :key="item.name"
                :class="{ 'is-planned': !item.done }"
              >
                <AppIcon :name="item.done ? 'check' : 'info'" :size="12" />
                <span>{{ item.name }}</span>
                <em>{{ item.done ? '已实现' : '待开发' }}</em>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section class="block" aria-labelledby="bounds-title">
        <div class="block__head">
          <h2 id="bounds-title">这一版做不到的事</h2>
          <p>写清楚边界，比让访问者自己猜更省事。</p>
        </div>
        <ul class="bounds">
          <li v-for="item in boundaries" :key="item">
            <AppIcon name="x" :size="13" />
            {{ item }}
          </li>
        </ul>
      </section>

      <section class="block block--cta">
        <div>
          <h2>想进去看看？</h2>
          <p>
            本平台当前为邀请制：没有账号时，用管理员发放的邀请码在登录页注册；已有账号直接登录。
          </p>
        </div>
        <div class="block__cta-actions">
          <RouterLink to="/login" class="btn btn--primary">
            {{ session.isAuthenticated ? '进入工作台' : '前往登录' }}
            <AppIcon name="arrow-right" :size="14" />
          </RouterLink>
          <RouterLink v-if="session.isAuthenticated" to="/" class="btn">工程概览</RouterLink>
        </div>
      </section>
    </main>

    <footer class="about__foot">
      <span>{{ brand.name }} · {{ brand.latin }}</span>
      <span>{{ brand.tagline }}</span>
    </footer>
  </div>
</template>

<style scoped>
.about {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: var(--bg);
}

/* One soft wash behind the hero; the rest of the page stays flat so text rules. */
.about__glow {
  position: absolute;
  inset: 0 0 auto;
  height: 460px;
  pointer-events: none;
  background:
    radial-gradient(
      760px 380px at 18% -10%,
      color-mix(in oklab, var(--brand) 12%, transparent),
      transparent 62%
    ),
    radial-gradient(
      620px 340px at 88% 0%,
      color-mix(in oklab, var(--accent) 10%, transparent),
      transparent 60%
    );
}

.about__bar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: 1080px;
  margin: 0 auto;
  padding: 18px 24px;
}

.about__brand {
  display: inline-flex;
}

.about__actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.about__icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg2);
  cursor: pointer;
}

.about__icon:hover {
  background: var(--surface2);
  color: var(--fg);
}

.about__cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--fg2);
  font-size: 12px;
}

.about__cta:hover {
  color: var(--fg);
  border-color: var(--border2);
}

.about__main {
  position: relative;
  z-index: 1;
  max-width: 1080px;
  margin: 0 auto;
  padding: 12px 24px 56px;
  display: grid;
  gap: 44px;
}

.hero {
  max-width: 720px;
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.14em;
  color: var(--fg2);
}

.hero h1 {
  margin: 14px 0 16px;
  font-size: clamp(28px, 3.4vw, 42px);
  line-height: 1.28;
  font-weight: 700;
  letter-spacing: -0.025em;
}

.hero h1 em {
  font-style: normal;
  color: var(--brand);
}

.hero__lede {
  margin: 0;
  font-size: 14px;
  line-height: 1.85;
  color: var(--fg2);
  max-width: 62ch;
}

.hero__meta {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--border2);
  color: var(--fg2);
  font-size: 11px;
}

/* "Implemented" uses the accent, not --down: green means a falling price in this
   product, so it must not also mean "good". The check icon carries the meaning. */
.tag--ok {
  color: var(--accent);
  border-color: color-mix(in oklab, var(--accent) 40%, transparent);
}

.block {
  display: grid;
  gap: 16px;
}

.block__head h2 {
  margin: 0 0 6px;
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.block__head p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--fg2);
  max-width: 66ch;
}

.block__head code {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--fg2);
  background: var(--surface2);
  padding: 1px 5px;
  border-radius: var(--radius-sm);
}

.block__console {
  justify-self: start;
}

/* Two columns, not auto-fit: there are exactly four capabilities, and auto-fit
   stranded the fourth card alone on its own row at desktop width. */
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.cap {
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: grid;
  gap: 8px;
  align-content: start;
}

.cap__icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: var(--radius);
  background: color-mix(in oklab, var(--brand) 14%, transparent);
  color: var(--brand);
}

.cap h3 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 650;
}

.cap p {
  margin: 0;
  font-size: 12px;
  line-height: 1.75;
  color: var(--fg2);
}

.cap ul {
  margin: 2px 0 0;
  padding-left: 16px;
  display: grid;
  gap: 3px;
}

.cap li {
  font-size: 11px;
  line-height: 1.6;
  color: var(--fg2);
}

.roadmap {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 18px;
}

.roadmap__group h3 {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--fg2);
}

.roadmap__group ul,
.bounds {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 5px;
}

.roadmap__group li {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--fg2);
}

.roadmap__group li svg {
  color: var(--accent);
  flex: none;
}

.roadmap__group li em {
  margin-left: auto;
  font-style: normal;
  font-size: 10px;
  color: var(--fg2);
}

/* "待开发"是信息，不是被禁用的控件：用文字色区分，不用 opacity 压低对比度
   （opacity:0.55 合成后约 3.75:1，低于正文要求；--muted 在 surface 上也仅 4.65:1）。 */
.roadmap__group li.is-planned {
  color: var(--fg2);
}

.roadmap__group li.is-planned svg {
  color: var(--fg2);
}

.bounds li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--fg2);
}

.bounds li svg {
  color: var(--fg2);
  flex: none;
  margin-top: 3px;
}

.block--cta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 20px;
  padding: 22px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

.block--cta h2 {
  margin: 0 0 6px;
  font-size: 17px;
  font-weight: 650;
}

.block--cta p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--fg2);
  max-width: 52ch;
}

.block__cta-actions {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 38px;
  padding: 0 16px;
  border-radius: var(--radius);
  border: 1px solid var(--border2);
  background: var(--surface2);
  color: var(--fg2);
  font-size: 12.5px;
}

.btn:hover {
  color: var(--fg);
  background: var(--surface3);
}

.btn--primary {
  border-color: transparent;
  background: linear-gradient(135deg, var(--brand), var(--brand2));
  color: #fff;
  font-weight: 600;
}

.btn--primary:hover {
  color: #fff;
  filter: brightness(1.07);
}

.about__foot {
  position: relative;
  z-index: 1;
  max-width: 1080px;
  margin: 0 auto;
  padding: 20px 24px 32px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--fg2);
}

@media (max-width: 720px) {
  .about__main {
    gap: 34px;
    padding-bottom: 40px;
  }

  .grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .block__console {
    justify-self: stretch;
  }

  .block__cta-actions {
    margin-left: 0;
  }
}
</style>
