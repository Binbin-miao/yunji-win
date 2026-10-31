import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 产物直接落到仓库的 docs/web/，GitHub Pages 仍以 main 分支 /docs 为源
export default defineConfig({
  base: '/yunji-win/web/',
  plugins: [react()],
  build: {
    outDir: '../docs/web',
    emptyOutDir: true,
  },
})
