import { useEffect, useState } from 'react'
import { accessToken } from '../../data/auth.ts'
import { enablePush, pushPermission } from '../../native.ts'
import { device, setDevice } from '../device.ts'
import { Button, Sheet } from './ui.tsx'
import { t } from '../../i18n.ts'

type Why = 'request' | 'listing'
const listeners = new Set<(why: Why) => void>()

/** After the first booking request or listing: the moment a notification is
 *  obviously worth having (U-4). Asked once per device, only if the OS would. */
export function askForPush(why: Why): void {
  listeners.forEach((fn) => fn(why))
}

export function PushPrime() {
  const [why, setWhy] = useState<Why | null>(null)

  useEffect(() => {
    const on = (w: Why) => {
      if (device().pushAsked) return
      void pushPermission().then((p) => {
        if (p === 'prompt') setWhy(w)
      })
    }
    listeners.add(on)
    return () => void listeners.delete(on)
  }, [])

  const close = () => {
    setDevice({ pushAsked: true })
    setWhy(null)
  }

  return (
    <Sheet
      open={why !== null}
      onClose={close}
      title={t('Get told when it matters')}
      footer={
        <div className="flex flex-col gap-2">
          <Button
            block
            size="lg"
            onClick={() => {
              close()
              void enablePush(accessToken, true)
            }}
          >
            {t('Turn on notifications')}
          </Button>
          <Button block variant="quiet" onClick={close}>
            {t('Not now')}
          </Button>
        </div>
      }
    >
      <p className="t-body text-[var(--ink-2)]">
        {why === 'listing'
          ? t('Requests lapse if you do not answer in time: within 24 hours, or before the booked time starts if that is sooner. A notification means you answer before the request lapses.')
          : t('The owner answers before the request lapses, within 24 hours at most. A notification tells you the moment they do, and when they write to you.')}
      </p>
      <p className="t-sm mt-3 text-[var(--ink-3)]">{t('Only bookings and messages. You can turn it off any time in Settings.')}</p>
    </Sheet>
  )
}
