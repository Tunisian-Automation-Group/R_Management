import type { CapacitorConfig } from '@capacitor/cli'

// The App Store and Google Play shells around the PWA (ADR 0012). The web build
// in dist/ is bundled into each app; build it with VITE_API_URL set to the
// public API (https://<domain>/api), since there is no same-origin /api inside a shell.
const config: CapacitorConfig = {
  appId: 'app.cappy',
  appName: 'Cappy',
  webDir: 'dist',
  plugins: {
    PushNotifications: { presentationOptions: ['badge', 'sound', 'alert'] },
  },
}

export default config
