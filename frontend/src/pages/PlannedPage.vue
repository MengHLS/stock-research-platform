<script setup lang="ts">
/**
 * A page that is planned but not built yet.
 *
 * It exists so the navigation model can stay honest: the route resolves, the page
 * states plainly that the capability is not implemented and which backend module
 * it waits on, instead of showing fake data or a blank panel. The design checklist
 * forbids filling an unimplemented view with sample numbers.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const title = computed(() => (route.meta.title as string | undefined) ?? '待开发页面')
const detail = computed(
  () => (route.meta.pending as string | undefined) ?? '该页面尚未实现，暂不展示模拟数据。',
)
</script>

<template>
  <section class="placeholder">
    <span class="placeholder__eyebrow">PLANNED</span>
    <h2>{{ title }}</h2>
    <p>{{ detail }}</p>
    <p class="placeholder__note">
      原型中已有设计稿；实现前需要对应的后端模块与接口。这里不显示示例数据，避免把未实现的能力当作可用。
    </p>
  </section>
</template>

<style scoped>
.placeholder {
  max-width: 640px;
  margin: 48px auto;
  padding: 32px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

.placeholder__eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.placeholder h2 {
  margin: 10px 0 12px;
  font-size: 20px;
  font-weight: 600;
}

.placeholder p {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.75;
  color: var(--fg2);
}

.placeholder__note {
  color: var(--muted);
  font-size: 12px;
}
</style>
