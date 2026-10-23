import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `base: './'` keeps the build usable when the API serves it from any path.
// The dev server proxies /api so `npm run dev` talks to `readproof serve`.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
