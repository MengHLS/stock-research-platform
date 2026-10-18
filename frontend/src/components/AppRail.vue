<script setup lang="ts">
/**
 * Left navigation rail.
 *
 * Behaviour taken from the prototype: grouped entries, 236px expanded / 64px
 * collapsed, and planned entries shown but not navigable. A planned entry is
 * disabled rather than hidden so the roadmap stays visible without pretending the
 * route works; `aria-disabled` (not `disabled`) keeps it discoverable to screen
 * readers.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppIcon from './AppIcon'
import { navGroups, type NavItem } from '../navigation'
import { useAppearance } from '../stores/appearance'

const appearance = useAppearance()
const route = useRoute()

const collapsed = computed(() => appearance.sidebarCollapsed)

function isActive(item: NavItem): boolean {
  return route.path === item.path || route.path.startsWith(`${item.path}/`)
}

function onSelect(item: NavItem) {
  if (!item.implemented) return
  appearance.closeMobileNav()
}
</script>

<template>
  <aside
    class="rail"
    :class="{ 'rail--collapsed': collapsed, 'rail--open': appearance.mobileNavOpen }"
    aria-label="主导航"
  >
    <div class="rail__brand">
      <span class="rail__mark" aria-hidden="true">研</span>
      <span v-if="!collapsed" class="rail__brand-text">
        研究工作台
        <small>Research Platform</small>
      </span>
    </div>

    <nav class="rail__nav">
      <div v-for="group in navGroups" :key="group.title" class="rail__group">
        <p v-if="!collapsed" class="rail__group-title">{{ group.title }}</p>
        <RouterLink
          v-for="item in group.items"
          :key="item.id"
          :to="item.implemented ? item.path : route.path"
          class="rail__item"
          :class="{
            'rail__item--active': isActive(item),
            'rail__item--planned': !item.implemented,
          }"
          :aria-disabled="item.implemented ? undefined : 'true'"
          :tabindex="item.implemented ? undefined : -1"
          :title="item.implemented ? item.name : `${item.name}（待开发）`"
          @click="onSelect(item)"
        >
          <AppIcon :name="item.icon" :size="18" />
          <span v-if="!collapsed" class="rail__item-label">{{ item.name }}</span>
          <span v-if="!collapsed && !item.implemented" class="rail__badge">待开发</span>
        </RouterLink>
      </div>
    </nav>

    <div class="rail__footer">
      <button
        type="button"
        class="rail__collapse"
        :aria-label="collapsed ? '展开侧栏' : '折叠侧栏'"
        @click="appearance.toggleSidebar()"
      >
        <AppIcon :name="collapsed ? 'panel-left-open' : 'panel-left-close'" :size="18" />
        <span v-if="!collapsed">折叠</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.rail {
  position: sticky;
  top: 0;
  align-self: start;
  height: 100vh;
  overflow: hidden auto;
  width: var(--rail-w);
  background: var(--bg2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 10px;
  z-index: 40;
  transition: width var(--duration) var(--ease);
}

.rail--collapsed {
  width: var(--rail-w-collapsed);
}

.rail__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 8px 14px;
  min-height: 56px;
}

.rail__mark {
  width: 32px;
  height: 32px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: var(--radius);
  background: var(--brand);
  color: #fff;
  font-weight: 650;
  font-size: 15px;
}

.rail__brand-text {
  font-weight: 650;
  font-size: 14px;
  line-height: 1.25;
  white-space: nowrap;
}

.rail__brand-text small {
  display: block;
  font-weight: 400;
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.02em;
}

.rail__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.rail__group + .rail__group {
  margin-top: 10px;
}

.rail__group-title {
  margin: 6px 8px 4px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.rail__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: var(--radius-sm);
  color: var(--fg2);
  font-size: 13px;
  white-space: nowrap;
  transition:
    background var(--duration) var(--ease),
    color var(--duration) var(--ease);
}

.rail__item:hover {
  background: var(--surface2);
  color: var(--fg);
}

.rail__item--active {
  background: color-mix(in oklab, var(--brand) 14%, transparent);
  color: var(--brand);
}

.rail__item--planned {
  opacity: 0.45;
  cursor: not-allowed;
}

.rail__item--planned:hover {
  background: transparent;
  color: var(--fg2);
}

.rail__item-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail__badge {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 999px;
  border: 1px solid var(--border2);
  color: var(--muted);
}

.rail__footer {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.rail__collapse {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: none;
  border: 0;
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
}

.rail__collapse:hover {
  background: var(--surface2);
  color: var(--fg);
}

/* Below this width the rail becomes an overlay drawer toggled from the topbar. */
@media (max-width: 900px) {
  .rail {
    position: fixed;
    inset: 0 auto 0 0;
    transform: translateX(-100%);
    transition: transform var(--duration) var(--ease);
    box-shadow: var(--shadow);
  }

  .rail--open {
    transform: translateX(0);
  }

  .rail--collapsed {
    width: var(--rail-w);
  }
}
</style>
