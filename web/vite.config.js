import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `base: './'` keeps the build usable when the API serves it from any path.
// The output goes inside the Python package so `pip install` carries the app and there
// is only ever one copy of it. The dev server proxies /api to `readproof serve`.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../readproof/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
