import { defineStore } from 'pinia'
import { ref } from 'vue'

import { THEME_ATTRIBUTE, type ThemeName } from '../styles/tokens'

const STORAGE_KEY = 'research.theme'
/** Sidebar collapse is a session preference, not persisted (matches the prototype). */
const SIDEBAR_KEY = 'research.sidebar'

function initialTheme(): ThemeName {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  // The prototype defaults to dark; honour the OS only when it explicitly asks
  // for light, so the expected first paint stays the reviewed one.
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export const useAppearance = defineStore('appearance', () => {
  const theme = ref<ThemeName>(initialTheme())
  const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_KEY) === 'collapsed')
  const mobileNavOpen = ref(false)

  function apply() {
    document.documentElement.setAttribute(THEME_ATTRIBUTE, theme.value)
  }

  function setTheme(next: ThemeName) {
    theme.value = next
    localStorage.setItem(STORAGE_KEY, next)
    apply()
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed.value ? 'collapsed' : 'expanded')
  }

  function openMobileNav() {
    mobileNavOpen.value = true
  }

  function closeMobileNav() {
    mobileNavOpen.value = false
  }

  return {
    theme,
    sidebarCollapsed,
    mobileNavOpen,
    apply,
    setTheme,
    toggleTheme,
    toggleSidebar,
    openMobileNav,
    closeMobileNav,
  }
})
