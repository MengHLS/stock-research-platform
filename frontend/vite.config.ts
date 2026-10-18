import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Dev server. The API target is configurable (`VITE_API_TARGET`) so a local API
 * on another port can be used without editing this file; the default matches
 * `tools/project.py dev`, which serves the API on 8000.
 */
const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': apiTarget,
      '/health': apiTarget,
    },
  },
})
