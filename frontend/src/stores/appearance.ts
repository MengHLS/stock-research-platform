import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppearance = defineStore('appearance', () => {
  const dark = ref(localStorage.getItem('research.theme') !== 'light')
  function apply() {
    document.documentElement.classList.toggle('dark', dark.value)
  }
  function toggle() {
    dark.value = !dark.value
    localStorage.setItem('research.theme', dark.value ? 'dark' : 'light')
    apply()
  }
  return { dark, apply, toggle }
})
