import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Where the backend gateway is during development. The dev server proxies
// /api there, so the app is same-origin with its API on localhost and on a
// phone hitting the LAN address alike, and no CORS is involved.
const backend = process.env.VITE_API_PROXY ?? 'http://localhost:8000'
const proxy = { '/api': { target: backend, changeOrigin: true } }

export default defineConfig({
  plugins: [
    react(),
    tailwind(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['apple-touch-icon.png'],
      workbox: {
        // The app shell is cached; the API is not. A navigation to /api/...
        // (someone opening a JSON URL) must not be answered with index.html.
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/, /^\/openapi\.json$/],
      },
      manifest: {
        name: 'Cappy — rent the hour, not the thing',
        short_name: 'Cappy',
        description: 'Cappy sells the hours your things are idle.',
        start_url: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#ffffff',
        theme_color: '#ffffff',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  server: { proxy },
  preview: { proxy },
})
