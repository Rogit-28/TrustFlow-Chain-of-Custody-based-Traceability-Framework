import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '') // Wait, does TrustDocs API use /api? No, it uses /documents, /auth, /admin directly. Let's fix proxy config:
      },
      '/auth': 'http://127.0.0.1:8100',
      '/documents': 'http://127.0.0.1:8100',
      '/admin': 'http://127.0.0.1:8100',
      '/boardrooms': 'http://127.0.0.1:8100',
      '/ws': {
        target: 'ws://127.0.0.1:8100',
        ws: true
      }
    }
  }
})
