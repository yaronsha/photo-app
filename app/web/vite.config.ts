import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/people': 'http://localhost:8000',
      '/search': 'http://localhost:8000',
      '/thumb': 'http://localhost:8000',
      '/photo': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
    },
  },
})
