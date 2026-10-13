import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: loadEnv(mode, process.cwd(), '').SATLINK_BACKEND_ORIGIN || 'http://127.0.0.1:8001',
        changeOrigin: false,
        ws: true,
      },
    },
  },
}))
