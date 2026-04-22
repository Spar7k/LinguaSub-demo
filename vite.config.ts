import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const host = process.env.TAURI_DEV_HOST
const buildTarget =
  process.env.TAURI_ENV_PLATFORM === 'windows' ? 'chrome105' : 'es2022'

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: 'ws',
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ['**/src-tauri/**', '**/backend/**'],
    },
  },
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: {
    target: buildTarget,
    minify: !process.env.TAURI_ENV_DEBUG ? 'esbuild' : false,
    sourcemap: Boolean(process.env.TAURI_ENV_DEBUG),
  },
})
