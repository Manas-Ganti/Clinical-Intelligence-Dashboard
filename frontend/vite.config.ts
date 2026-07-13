import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev the API runs on a separate port; proxy backend paths so the browser
// makes same-origin requests (no CORS dance). Override the target with
// VITE_API_URL when the API lives elsewhere (e.g. in docker-compose).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Every backend path needs an entry: an unproxied path silently falls
    // through to Vite's SPA fallback, which answers 200 with index.html — so
    // fetch().ok is true and only .json() fails, surfacing as "couldn't load"
    // rather than a connection error. /findings, /encounters, /alerts, /imaging
    // and /query were missing, which broke every detail panel under `npm run dev`.
    proxy: {
      '/patients': 'http://localhost:8000',
      '/encounters': 'http://localhost:8000',
      '/findings': 'http://localhost:8000',
      '/imaging': 'http://localhost:8000',
      '/alerts': 'http://localhost:8000',
      '/query': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
