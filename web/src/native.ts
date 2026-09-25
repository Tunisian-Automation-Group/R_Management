// The App Store and Google Play shells (Capacitor, ADR 0012). Everything here
// is a no-op on the web; plugins are imported only inside a shell.
import { Capacitor } from '@capacitor/core'
import { closeTopSheet } from './app/sheets.ts'

export const isNative = Capacitor.isNativePlatform()
export const platform = Capacitor.getPlatform() as 'web' | 'ios' | 'android'

const API: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api'
const DEVICE_KEY = 'cappy.push.token.v1'

/** The platform's app storage (not a web view's localStorage). */
export const nativeStore = {
  async get(key: string): Promise<string | null> {
    const { Preferences } = await import('@capacitor/preferences')
    return (await Preferences.get({ key })).value
  },
  async set(key: string, value: string): Promise<void> {
    const { Preferences } = await import('@capacitor/preferences')
    await Preferences.set({ key, value })
  },
  async remove(key: string): Promise<void> {
    const { Preferences } = await import('@capacitor/preferences')
    await Preferences.remove({ key })
  },
}

/** Go to a path inside the app, as a tap on a link would. */
function open(link: string | undefined): void {
  if (!link) return
  let path = link
  try {
    const u = new URL(link, window.location.origin)
    path = u.pathname + u.search
  } catch {
    // A bare path already.
  }
  window.history.pushState(null, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

let wired = false

/** Deep links (Universal Links, App Links) and notification taps open inside the app. */
/** iOS Dynamic Type (U-27): WKWebView ignores the reader's text size, so the
 *  root follows it: `-apple-system-body` is 17px at the default "Large",
 *  and every type size is in rem. Android's WebView scales text by itself. */
function followDynamicType(): void {
  const probe = document.createElement('span')
  probe.style.font = '-apple-system-body'
  document.body.appendChild(probe)
  const px = parseFloat(getComputedStyle(probe).fontSize)
  probe.remove()
  if (px) document.documentElement.style.fontSize = `${(px / 17) * 100}%`
}

export async function wireNative(): Promise<void> {
  if (!isNative || wired) return
  wired = true
  const platform = (window as unknown as { Capacitor?: { getPlatform?: () => string } }).Capacitor?.getPlatform?.()
  if (platform === 'ios') {
    followDynamicType()
    // The reader changes it in Settings while the app is in the background.
    document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && followDynamicType())
  }
  const { App } = await import('@capacitor/app')
  await App.addListener('appUrlOpen', (e) => open(e.url))
  // Android back (U-5): the top sheet, then the previous screen, then out of
  // the app to the home screen (minimised, not killed, as native apps do).
  await App.addListener('backButton', ({ canGoBack }) => {
    if (closeTopSheet()) return
    if (canGoBack && window.location.pathname !== '/') window.history.back()
    else void App.minimizeApp()
  })
  const { PushNotifications } = await import('@capacitor/push-notifications')
  await PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
    const data = action.notification.data as { link?: string } | undefined
    open(data?.link)
  })
}

export type PushPermission = 'granted' | 'denied' | 'prompt' | 'unavailable'

/** What the OS says about notifications for this app, without asking. */
export async function pushPermission(): Promise<PushPermission> {
  if (!isNative) return 'unavailable'
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')
    const { receive } = await PushNotifications.checkPermissions()
    return receive === 'granted' ? 'granted' : receive === 'denied' ? 'denied' : 'prompt'
  } catch {
    return 'unavailable'
  }
}

let registered = false

/** Tell the server where to push. Asks the OS only when `ask` is set, which
 *  happens after a moment that makes the reason obvious (U-4), never at sign-in. */
export async function enablePush(accessToken: () => Promise<string | null>, ask = false): Promise<PushPermission> {
  if (!isNative) return 'unavailable'
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')
    let perm = await pushPermission()
    if (perm === 'prompt' && ask) {
      const { receive } = await PushNotifications.requestPermissions()
      perm = receive === 'granted' ? 'granted' : 'denied'
    }
    if (perm !== 'granted' || registered) return perm
    registered = true
    await PushNotifications.addListener('registration', async ({ value }) => {
      const access = await accessToken()
      if (!access) return
      await fetch(`${API}/notifications/devices`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access}` },
        body: JSON.stringify({ platform, token: value }),
      })
      await nativeStore.set(DEVICE_KEY, value)
    })
    await PushNotifications.register()
    return perm
  } catch {
    // Push is a convenience; email still arrives.
    return 'unavailable'
  }
}

/** iOS opens the app's own page in Settings from this URL (Capacitor hands
 *  non-web schemes to the OS). Android has no such URL without a plugin, so the
 *  screen names the path instead. */
export const canOpenSettings = platform === 'ios'
export function openAppSettings(): void {
  if (canOpenSettings) window.location.href = 'app-settings:'
}

/** Before sign-out: this device stops getting this person's notifications. */
export async function pushSignedOut(access: string): Promise<void> {
  if (!isNative) return
  try {
    const token = await nativeStore.get(DEVICE_KEY)
    if (!token) return
    await fetch(`${API}/notifications/devices/${encodeURIComponent(token)}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${access}` },
    })
    await nativeStore.remove(DEVICE_KEY)
  } catch {
    // Offline: the server forgets the device when a push to it fails.
  }
}

/** A file handed to the share sheet (the data export), where downloads don't exist. */
export async function shareFile(name: string, text: string): Promise<boolean> {
  if (!isNative) return false
  const { Filesystem, Directory, Encoding } = await import('@capacitor/filesystem')
  const { Share } = await import('@capacitor/share')
  const written = await Filesystem.writeFile({ path: name, data: text, directory: Directory.Cache, encoding: Encoding.UTF8 })
  await Share.share({ title: name, url: written.uri })
  return true
}
