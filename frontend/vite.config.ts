import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // A preview tool may assign a free port via PORT; 5173 otherwise.
    port: Number(process.env.PORT) || 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
