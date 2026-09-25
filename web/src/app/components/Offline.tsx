import { useSyncExternalStore } from 'react'
import { t } from '../../i18n.ts'

const subscribe = (fn: () => void) => {
  window.addEventListener('online', fn)
  window.addEventListener('offline', fn)
  return () => {
    window.removeEventListener('online', fn)
    window.removeEventListener('offline', fn)
  }
}

/** What the browser believes about the network. `false` is reliable; `true`
 *  only means there is a network, not that Cappy is reachable. */
export const useOnline = () => useSyncExternalStore(subscribe, () => navigator.onLine)

/** A bar above the dock while offline (U-11): what is on screen stays readable,
 *  anything that moves money or sends something waits. */
export function OfflineBar() {
  if (useOnline()) return null
  return (
    <div
      role="status"
      // Above the dock, clear of every screen's back button and header.
      className="fixed inset-x-4 z-[45] mx-auto max-w-[420px] rounded-[14px] bg-[var(--ink)] px-4 py-2.5 text-center text-[0.8125rem] font-semibold text-[var(--page)] shadow-[var(--shadow-float)]"
      style={{ bottom: 'calc(var(--dock-h) + var(--footer-h, 0px) + 12px)' }}
    >
      {t('You are offline. What you see may be out of date; paying, booking and sending wait until you are back.')}
    </div>
  )
}
