<script setup lang="ts">
/**
 * Marketing column shown beside the sign-in form, and reused as the hero of the
 * public about page.
 *
 * Layout and typography follow the Open Design `auth.html` prototype: a 1.12:1
 * split, radial washes behind a masked grid, a 27px headline with one highlighted
 * phrase, and three numbered points. What it crucially does *not* copy is the
 * prototype's fake terminal preview — the panel here is `PlatformStatus`, which
 * renders the live `/health/live` and `/api/v1/market/sources` answers.
 */
import BrandLogo from './BrandLogo.vue'
import PlatformStatus from './PlatformStatus.vue'
import { brand, brandMarkSizes } from '../brand'
import { pitchPoints } from '../product'
</script>

<template>
  <div class="showcase">
    <div class="showcase__brandrow">
      <BrandLogo :size="brandMarkSizes.rail" />
      <span class="showcase__badge">当前邀请制</span>
    </div>

    <div class="showcase__pitch">
      <h2>
        把每一次研究，<br />
        立在<em>证据</em>上。
      </h2>
      <p>
        {{ brand.tagline }}：行情、竞价、模式库与执行记录放在同一个工作台，
        <b>看到来源、显式降级、留下可复核的结论</b>，而不是把指标堆一屏。
      </p>
    </div>

    <ol class="showcase__points">
      <li v-for="(point, index) in pitchPoints" :key="point.title">
        <i aria-hidden="true">{{ index + 1 }}</i>
        <div>
          <b>{{ point.title }}</b>
          {{ point.body }}
        </div>
      </li>
    </ol>

    <PlatformStatus />

    <div class="showcase__foot">
      <RouterLink to="/about">
        平台说明
        <span aria-hidden="true">→</span>
      </RouterLink>
      <span>未登录也能查看系统状态</span>
    </div>
  </div>
</template>

<style scoped>
.showcase {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 26px;
  padding: 34px 40px 30px;
  background:
    radial-gradient(
      900px 520px at 12% -8%,
      color-mix(in oklab, var(--brand) 13%, transparent),
      transparent 62%
    ),
    radial-gradient(
      720px 480px at 98% 105%,
      color-mix(in oklab, var(--accent) 12%, transparent),
      transparent 60%
    ),
    var(--bg2);
  border-right: 1px solid var(--border);
}

/* Masked grid: gives the flat panel texture without competing with the copy. */
.showcase::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.5;
  background-image:
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(60% 60% at 50% 42%, #000 0%, transparent 100%);
}

.showcase > * {
  position: relative;
  z-index: 1;
}

.showcase__brandrow {
  display: flex;
  align-items: center;
  gap: 11px;
}

.showcase__badge {
  margin-left: auto;
  font-size: 10.5px;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid var(--border2);
  color: var(--fg2);
  white-space: nowrap;
}

.showcase__pitch h2 {
  margin: 0 0 10px;
  font-size: 27px;
  line-height: 1.32;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.showcase__pitch h2 em {
  font-style: normal;
  color: var(--brand);
}

.showcase__pitch p {
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--fg2);
  max-width: 46ch;
}

.showcase__pitch b {
  color: var(--fg);
  font-weight: 600;
}

.showcase__points {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 9px;
}

.showcase__points li {
  display: grid;
  grid-template-columns: 22px 1fr;
  gap: 9px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--fg2);
}

.showcase__points i {
  width: 20px;
  height: 20px;
  border-radius: var(--radius-sm);
  display: grid;
  place-items: center;
  font-style: normal;
  font-size: 10px;
  font-family: var(--mono);
  font-weight: 700;
  background: color-mix(in oklab, var(--accent) 16%, var(--surface2));
  color: var(--accent);
  border: 1px solid color-mix(in oklab, var(--accent) 30%, var(--border));
}

.showcase__points b {
  color: var(--fg);
  font-weight: 620;
}

.showcase__foot {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  align-items: center;
  font-size: 10.5px;
  color: var(--fg2);
}

.showcase__foot a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--accent);
}

.showcase__foot a:hover {
  color: var(--fg);
  text-decoration: underline;
}

@media (max-width: 1020px) {
  .showcase {
    border-right: 0;
    border-bottom: 1px solid var(--border);
    padding: 26px 22px;
    gap: 20px;
  }

  .showcase__pitch h2 {
    font-size: 22px;
  }

  .showcase__foot {
    display: none;
  }
}

@media (max-width: 560px) {
  .showcase__badge {
    display: none;
  }
}
</style>
