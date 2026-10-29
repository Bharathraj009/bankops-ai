import { defineConfig } from 'vite'
import { monitoringBoundary, proxy } from './proxy'

// Runtime preview uses exactly the development proxy policy, without build/test plugins.
export default defineConfig({
  plugins: [monitoringBoundary],
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    proxy,
  },
})
