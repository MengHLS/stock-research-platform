<script setup lang="ts">
/**
 * Top bar: current page title, connection state, theme switch and account menu.
 *
 * The design checklist requires each page to expose one primary context; this bar
 * carries the page title and the session/api state, while the page body owns the
 * page-specific context (trading day, run id, ...). It must not invent that
 * context here.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from './AppIcon'
import { brand } from '../brand'
import { useAppearance } from '../stores/appearance'
import { useSession } from '../stores/session'

const appearance = useAppearance()
const session = useSession()
const route = useRoute()
const router = useRouter()

const menuOpen = ref(false)

const title = computed(() => (route.meta.title as string | undefined) ?? brand.name)
const subtitle = computed(() => (route.meta.subtitle as string | undefined) ?? '')
const displayName = computed(() => session.user?.display_name || session.user?.email || '未登录')

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

async function signOut() {
  menuOpen.value = false
  await session.logout()
  await router.push({ name: 'login' })
}

onMounted(() => {
  // A click anywhere else closes the account menu; the listener is passive and
  // scoped to this component's lifetime by Vue's unmount.
  document.addEventListener('click', () => (menuOpen.value = false), { once: true })
})
</script>

<template>
  <header class="topbar">
    <button
      type="button"
      class="topbar__menu"
      aria-label="打开导航"
      @click.stop="appearance.openMobileNav()"
    >
      <AppIcon name="menu" :size="20" />
    </button>

    <div class="topbar__title">
      <h1>{{ title }}</h1>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>

    <div class="topbar__actions">
      <span
        v-if="session.isResolving"
        class="topbar__pill topbar__pill--muted"
        title="正在确认登录状态"
      >
        检查会话…
      </span>
      <span v-else-if="session.isAuthenticated" class="topbar__pill topbar__pill--ok">已登录</span>
      <span v-else class="topbar__pill topbar__pill--muted">未登录</span>

      <button
        type="button"
        class="topbar__icon"
        :aria-label="appearance.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
        @click="appearance.toggleTheme()"
      >
        <AppIcon :name="appearance.theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>

      <div class="topbar__account">
        <button
          type="button"
          class="topbar__account-btn"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          @click.stop="toggleMenu"
        >
          <AppIcon name="user" :size="16" />
          <span class="topbar__account-name">{{ displayName }}</span>
          <AppIcon name="chevron-down" :size="14" />
        </button>
        <div v-if="menuOpen" class="topbar__menu-panel" role="menu">
          <p class="topbar__menu-email">{{ session.user?.email ?? '尚未登录' }}</p>
          <button v-if="session.isAuthenticated" type="button" role="menuitem" @click="signOut">
            <AppIcon name="log-out" :size="16" />
            退出登录
          </button>
          <RouterLink v-else to="/login" role="menuitem">
            <AppIcon name="user" :size="16" />
            去登录
          </RouterLink>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 18px;
  background: color-mix(in oklab, var(--bg) 82%, transparent);
  backdrop-filter: blur(12px) saturate(1.2);
  border-bottom: 1px solid var(--border);
}

.topbar__menu {
  display: none;
  background: none;
  border: 0;
  padding: 6px;
  border-radius: var(--radius-sm);
  color: var(--fg2);
  cursor: pointer;
}

.topbar__menu:hover {
  background: var(--surface2);
}

.topbar__title {
  min-width: 0;
}

.topbar__title h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.topbar__title p {
  margin: 0;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.topbar__actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.topbar__pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border2);
  white-space: nowrap;
}

.topbar__pill--ok {
  color: var(--down);
  border-color: color-mix(in oklab, var(--down) 40%, transparent);
}

.topbar__pill--muted {
  color: var(--muted);
}

.topbar__icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg2);
  cursor: pointer;
}

.topbar__icon:hover {
  background: var(--surface2);
  color: var(--fg);
}

.topbar__account {
  position: relative;
}

.topbar__account-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg2);
  font-size: 12px;
  cursor: pointer;
  max-width: 200px;
}

.topbar__account-btn:hover {
  background: var(--surface2);
  color: var(--fg);
}

.topbar__account-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar__menu-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  min-width: 200px;
  padding: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.topbar__menu-email {
  margin: 4px 8px 8px;
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
}

.topbar__menu-panel button,
.topbar__menu-panel a {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px;
  background: none;
  border: 0;
  border-radius: var(--radius-sm);
  color: var(--fg2);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.topbar__menu-panel button:hover,
.topbar__menu-panel a:hover {
  background: var(--surface2);
  color: var(--fg);
}

@media (max-width: 900px) {
  .topbar__menu {
    display: grid;
    place-items: center;
  }

  .topbar__account-name {
    display: none;
  }
}
</style>
