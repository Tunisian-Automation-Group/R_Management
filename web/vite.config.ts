import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import pkg from './package.json' with { type: 'json' }
import type { Plugin } from 'vite'

// Where the backend gateway is during development. The dev server proxies
// /api there, so the app is same-origin with its API on localhost and on a
// phone hitting the LAN address alike, and no CORS is involved.
const backend = process.env.VITE_API_PROXY ?? 'http://localhost:8000'
// /media too: listing photos are served by the backend at the same origin.
const proxy = {
  '/api': { target: backend, changeOrigin: true },
  '/media': { target: backend, changeOrigin: true },
}

/**
 * The files that let https://<domain>/listing/… open in the store apps instead
 * of the browser (Universal Links, App Links). Written at build time from
 * VITE_APPLE_TEAM_ID and VITE_ANDROID_SHA256 (the release signing certificate,
 * colon-separated hex); unset, they carry placeholders and verify nothing.
 */
function appLinks(): Plugin {
  let env: Record<string, string> = {}
  return {
    name: 'cappy-app-links',
    configResolved(config) {
      env = config.env
    },
    generateBundle() {
      const team = env.VITE_APPLE_TEAM_ID || 'TEAMID'
      const sha = env.VITE_ANDROID_SHA256 || '00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00'
      const apple = {
        applinks: {
          details: [
            {
              appIDs: [`${team}.app.cappy`],
              components: [{ '/': '/listing/*' }, { '/': '/bookings/*' }, { '/': '/earn*' }],
            },
          ],
        },
      }
      const android = [
        {
          relation: ['delegate_permission/common.handle_all_urls'],
          target: { namespace: 'android_app', package_name: 'app.cappy', sha256_cert_fingerprints: [sha] },
        },
      ]
      // No extension on Apple's file: it is fetched by that exact path, as application/json.
      this.emitFile({ type: 'asset', fileName: '.well-known/apple-app-site-association', source: JSON.stringify(apple) })
      this.emitFile({ type: 'asset', fileName: '.well-known/assetlinks.json', source: JSON.stringify(android) })
    },
  }
}

export default defineConfig({
  // The build's version, sent to the API so an app too old for it can be told to update.
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  plugins: [
    react(),
    tailwind(),
    appLinks(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['apple-touch-icon.png'],
      workbox: {
        // The app shell is cached; the API is not. A navigation to /api/...
        // (someone opening a JSON URL) must not be answered with index.html.
        navigateFallbackDenylist: [/^\/api\//, /^\/\.well-known\//, /^\/docs/, /^\/openapi\.json$/],
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
