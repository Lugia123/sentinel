import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 前端 :5173 → 后端 :8787,/api 走代理(dev 免跨域)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8787' },
  },
})
