import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev the API runs on a separate port; proxy backend paths so the browser
// makes same-origin requests (no CORS dance). Override the target with
// VITE_API_URL when the API lives elsewhere (e.g. in docker-compose).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/patients': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
