<script setup lang="ts">
/**
 * Application shell.
 *
 * The login page renders outside the chrome, so a signed-out visitor never sees a
 * navigation rail full of pages they cannot open. Everything else gets the
 * prototype's structure: sticky rail, sticky topbar, scrolling content column.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppRail from './components/AppRail.vue'
import AppTopbar from './components/AppTopbar.vue'
import { useAppearance } from './stores/appearance'

const route = useRoute()
const appearance = useAppearance()

const isPublic = computed(() => route.meta.public === true)

appearance.apply()
</script>

<template>
  <RouterView v-if="isPublic" />
  <div v-else class="app" :class="{ 'app--collapsed': appearance.sidebarCollapsed }">
    <AppRail />
    <div
      v-if="appearance.mobileNavOpen"
      class="app__scrim"
      aria-hidden="true"
      @click="appearance.closeMobileNav()"
    />
    <div class="app__main">
      <AppTopbar />
      <main
        class="app__content"
        :class="{ 'app__content--fill': route.meta.fillViewport === true }"
      >
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app {
  display: grid;
  grid-template-columns: var(--rail-w) minmax(0, 1fr);
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
}

.app--collapsed {
  grid-template-columns: var(--rail-w-collapsed) minmax(0, 1fr);
}

.app__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.app__content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding: 20px;
}

@media (min-width: 1081px) and (min-height: 680px) {
  .app__content--fill {
    overflow: hidden;
  }
}

.app__scrim {
  position: fixed;
  inset: 0;
  z-index: 35;
  background: rgba(0, 0, 0, 0.5);
}

@media (max-width: 900px) {
  .app,
  .app--collapsed {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
