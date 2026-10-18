<script setup lang="ts">
/**
 * Brand lockup: the plinth mark plus the product name.
 *
 * `full` shows the mark with 磐石 / QUANT LAB stacked beside it; `mark` shows the
 * square only, which is what the collapsed rail has room for.
 *
 * The mark is a rounded square filled with the brand colour — the treatment the
 * prototype used, and the one that stays legible at 28px where a bare three-line
 * glyph would dissolve.
 *
 * The glyph is drawn by `AppIcon` rather than inline `v-html`, so the brand mark
 * and every navigation icon share one SVG renderer and one lint posture (the
 * `vue/no-v-html` rule stays meaningful for templates that do bind user data).
 */
import { computed } from 'vue'

import { brand, type LogoVariant } from '../brand'
import AppIcon from './AppIcon'

const props = withDefaults(
  defineProps<{
    mode?: 'full' | 'mark'
    size?: number
    variant?: LogoVariant
  }>(),
  { mode: 'full', size: 32, variant: 'plinth' },
)

// The glyph fills most of the tile: at 0.62 the three stacked courses were too
// thin to read once the tile dropped to 28px in the collapsed rail.
const glyphSize = computed(() => Math.round(props.size * 0.72))
</script>

<template>
  <span
    class="brand-logo"
    :class="{ 'brand-logo--mark-only': mode === 'mark' }"
    :role="mode === 'mark' ? 'img' : undefined"
    :aria-label="mode === 'mark' ? brand.name : undefined"
  >
    <span
      class="brand-logo__mark"
      :style="{ width: `${size}px`, height: `${size}px` }"
      aria-hidden="true"
    >
      <AppIcon :name="variant" :size="glyphSize" />
    </span>
    <span v-if="mode === 'full'" class="brand-logo__text">
      <span class="brand-logo__name">{{ brand.name }}</span>
      <span class="brand-logo__latin">{{ brand.latin }}</span>
    </span>
  </span>
</template>

<style scoped>
.brand-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-logo__mark {
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--brand);
  color: #fff;
}

.brand-logo__text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.brand-logo__name {
  font-size: 14px;
  font-weight: 650;
  letter-spacing: 0.06em;
  line-height: 1.2;
  color: var(--fg);
  white-space: nowrap;
}

.brand-logo__latin {
  font-size: 9px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
  line-height: 1.2;
  white-space: nowrap;
}
</style>
