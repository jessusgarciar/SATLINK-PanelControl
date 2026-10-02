import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: loadEnv(mode, process.cwd(), '').SATLINK_BACKEND_ORIGIN || 'http://127.0.0.1:8000',
        changeOrigin: false,
        ws: true,
      },
    },
  },
}))
