import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
      '/upload': 'http://localhost:8000',
      '/download': 'http://localhost:8000',
      '/cancel': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
