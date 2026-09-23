import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiTarget = process.env.API_TARGET || 'http://127.0.0.1:8000'
const proxy = {
  '/api': {
    target: apiTarget,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ''),
  },
}

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_API_DOCS_URL': JSON.stringify(process.env.VITE_API_DOCS_URL || `${apiTarget}/docs`),
  },
  server: { proxy },
  preview: { proxy },
})
