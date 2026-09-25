// The App Store and Google Play shells (Capacitor, ADR 0012). Everything here
// is a no-op on the web; plugins are imported only inside a shell.
import { Capacitor } from '@capacitor/core'

export const isNative = Capacitor.isNativePlatform()
const platform = Capacitor.getPlatform() as 'ios' | 'android' | 'web'

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
export async function wireNative(): Promise<void> {
  if (!isNative || wired) return
  wired = true
  const { App } = await import('@capacitor/app')
  await App.addListener('appUrlOpen', (e) => open(e.url))
  const { PushNotifications } = await import('@capacitor/push-notifications')
  await PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
    const data = action.notification.data as { link?: string } | undefined
    open(data?.link)
  })
}

/** After sign-in: ask to notify, then tell the server where to push. */
export async function pushSignedIn(accessToken: () => Promise<string | null>): Promise<void> {
  if (!isNative) return
  try {
    const { PushNotifications } = await import('@capacitor/push-notifications')
    const perm = await PushNotifications.requestPermissions()
    if (perm.receive !== 'granted') return
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
  } catch {
    // Push is a convenience; email still arrives.
  }
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
