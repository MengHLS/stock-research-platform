<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import AppIcon from '../AppIcon'

const props = defineProps<{
  open: boolean
  title: string
  meta?: string
  variant?: 'drawer' | 'modal'
  modalSize?: 'default' | 'chart' | 'detail'
}>()
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let returnFocus: HTMLElement | null = null
let previousBodyOverflow = ''

const focusableSelector = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function lockBackground() {
  returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  const app = document.getElementById('app')
  app?.setAttribute('inert', '')
  app?.setAttribute('aria-hidden', 'true')
}

function unlockBackground() {
  document.body.style.overflow = previousBodyOverflow
  const app = document.getElementById('app')
  app?.removeAttribute('inert')
  app?.removeAttribute('aria-hidden')
}

function onKeydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab' || !panel.value) return
  const focusable = Array.from(panel.value.querySelectorAll<HTMLElement>(focusableSelector)).filter(
    (element) =>
      element.tabIndex >= 0 &&
      element.getAttribute('aria-hidden') !== 'true' &&
      element.getClientRects().length > 0,
  )
  if (!focusable.length) {
    event.preventDefault()
    panel.value.focus()
    return
  }
  const first = focusable[0]!
  const last = focusable.at(-1)!
  const active = document.activeElement
  if (
    event.shiftKey &&
    (active === first || active === panel.value || !panel.value.contains(active))
  ) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !panel.value.contains(active))) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  async (open) => {
    if (!open) {
      unlockBackground()
      await nextTick()
      if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true })
      returnFocus = null
      return
    }
    lockBackground()
    await nextTick()
    panel.value?.focus()
  },
)

watch(
  () => props.variant,
  async () => {
    if (!props.open) return
    await nextTick()
    panel.value?.focus()
  },
)

defineExpose({
  focusPanel: () => panel.value?.focus({ preventScroll: true }),
})

document.addEventListener('keydown', onKeydown)
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  if (props.open) unlockBackground()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="open" class="drawer-layer" :class="{ 'drawer-layer--modal': variant === 'modal' }">
        <div class="drawer-scrim" @click="emit('close')" />
        <aside
          ref="panel"
          class="drawer-panel"
          :class="[
            `drawer-panel--${variant ?? 'drawer'}`,
            { 'drawer-panel--chart': modalSize === 'chart' },
            { 'drawer-panel--detail': modalSize === 'detail' },
          ]"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          tabindex="-1"
        >
          <header class="drawer-head">
            <div>
              <h2>{{ title }}</h2>
              <p v-if="meta">{{ meta }}</p>
            </div>
            <button type="button" class="close" aria-label="关闭" @click="emit('close')">
              <AppIcon name="x" :size="18" />
            </button>
          </header>
          <div class="drawer-body">
            <slot />
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer-layer {
  position: fixed;
  inset: 0;
  z-index: 80;
}

.drawer-layer--modal {
  display: grid;
  place-items: center;
  padding: 5vh 16px;
}

.drawer-scrim {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.52);
  backdrop-filter: blur(2px);
}

.drawer-panel {
  position: absolute;
  inset: 0 0 0 auto;
  width: min(460px, 94vw);
  display: flex;
  flex-direction: column;
  background: var(--bg2);
  border-left: 1px solid var(--border2);
  box-shadow: -18px 0 42px rgba(0, 0, 0, 0.28);
  outline: none;
}

.drawer-panel--modal {
  position: relative;
  inset: auto;
  width: min(720px, 94vw);
  height: min(680px, 90vh);
  height: min(680px, 90dvh);
  border: 1px solid var(--border2);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.drawer-panel--modal.drawer-panel--chart {
  height: auto;
  max-height: min(720px, 90vh);
  max-height: min(720px, 90dvh);
}

.drawer-panel--modal.drawer-panel--detail {
  width: min(1120px, 95vw);
  height: min(820px, 92vh);
  height: min(820px, 92dvh);
}

.drawer-panel--chart .drawer-body {
  flex: 0 1 auto;
}

.drawer-head {
  display: flex;
  flex-shrink: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 17px 18px;
  border-bottom: 1px solid var(--border);
}

.drawer-head h2 {
  margin: 0;
  font-size: 19px;
  letter-spacing: -0.01em;
}

.drawer-head p {
  margin: 3px 0 0;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 12.5px;
}

.close {
  width: 34px;
  height: 34px;
  flex: none;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  cursor: pointer;
}

.drawer-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: opacity var(--duration) var(--ease);
}

.drawer-enter-active .drawer-panel,
.drawer-leave-active .drawer-panel {
  transition: transform var(--duration) var(--ease);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .drawer-panel,
.drawer-leave-to .drawer-panel {
  transform: translateX(100%);
}

.drawer-enter-from .drawer-panel--modal,
.drawer-leave-to .drawer-panel--modal {
  transform: translateY(8px) scale(0.98);
}

@media (max-width: 620px) {
  .drawer-panel--drawer {
    width: 100%;
  }

  .drawer-layer--modal {
    padding-inline: 10px;
  }

  .close {
    width: 44px;
    height: 44px;
  }
}
</style>
