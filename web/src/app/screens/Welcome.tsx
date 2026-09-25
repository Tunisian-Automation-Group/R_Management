import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LanguageSwitch } from '../components/AppShell.tsx'
import { Icon, type IconName } from '../components/Icon.tsx'
import { Button } from '../components/ui.tsx'
import { setDevice } from '../device.ts'
import { t } from '../../i18n.ts'

const VALUES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: 'search',
    title: 'Book the hours, not the thing',
    body: 'A workshop for an afternoon, a van for a move, a 3D printer for a batch: from people and businesses near you.',
  },
  {
    icon: 'wallet',
    title: 'Earn from what stands idle',
    body: 'List a machine, a room or a vehicle for the hours it is free. You approve every booking and are paid after it.',
  },
  {
    icon: 'shield',
    title: 'Members only, for a reason',
    body: 'Listings are people’s own property and addresses. Everyone signs in, payments stay on Cappy, and both sides review each other.',
  },
]

/**
 * The first thing a new device sees (U-2): what Cappy is, in one screen, and
 * the two ways in. No live listings: the product is for members (GOAL 13).
 * Seen once; after that a signed-out device goes straight to sign-in (U-3).
 */
export function Welcome() {
  const nav = useNavigate()
  useEffect(() => {
    document.title = t('Welcome to Cappy')
    setDevice({ welcomeSeen: true })
  }, [])
  return (
    <div className="min-h-dvh bg-[var(--field)] text-[var(--on-field)]">
      <div
        className="mx-auto flex min-h-dvh max-w-[560px] flex-col px-6 md:max-w-[1040px] md:px-10"
        style={{ paddingTop: 'max(20px, env(safe-area-inset-top))', paddingBottom: 'max(24px, env(safe-area-inset-bottom))' }}
      >
        <header className="flex items-center justify-between gap-4">
          <p className="t-h2 leading-none" style={{ fontSize: 28 }}>
            Cappy
          </p>
          <div className="rounded-full bg-[var(--surface)]">
            <LanguageSwitch />
          </div>
        </header>

        <main id="main" className="flex flex-1 flex-col justify-center py-10 md:grid md:grid-cols-2 md:items-center md:gap-16">
          <div>
            <h1 className="t-display text-balance" style={{ fontSize: 'clamp(40px, 9vw, 72px)', lineHeight: 1.02 }}>
              {t('Capacity, shared by the hour.')}
            </h1>
            <p className="t-body mt-4 max-w-[40ch] text-[var(--on-field-dim)]">
              {t('Rent the machines, rooms and vehicles near you when you need them, and earn from yours when you do not.')}
            </p>
          </div>
          <ul className="mt-10 space-y-6 md:mt-0">
            {VALUES.map((v) => (
              <li key={v.title} className="flex gap-4">
                <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--on-field)] text-[var(--field)]">
                  <Icon name={v.icon} size={17} strokeWidth={2} />
                </span>
                <div>
                  <h2 className="text-[1rem] font-semibold">{t(v.title)}</h2>
                  <p className="t-sm mt-1 text-[var(--on-field-dim)]">{t(v.body)}</p>
                </div>
              </li>
            ))}
          </ul>
        </main>

        <div className="flex flex-col gap-3 md:mx-auto md:w-[360px]">
          <Button size="lg" block onClick={() => nav('/login?mode=up', { replace: true })}>
            {t('Create an account')}
          </Button>
          <button
            type="button"
            onClick={() => nav('/login', { replace: true })}
            className="min-h-[48px] rounded-[var(--radius-control)] border border-[var(--on-field-dim)] px-4 text-[0.9375rem] font-semibold"
          >
            {t('I have an account')}
          </button>
        </div>

        <nav aria-label={t('Legal')} className="t-sm mt-6 flex flex-wrap justify-center gap-x-5 gap-y-1 text-[var(--on-field-dim)]">
          <Link to="/legal/impressum">Impressum</Link>
          <Link to="/legal/privacy">{t('Privacy')}</Link>
          <Link to="/legal/terms">{t('Terms')}</Link>
          <Link to="/help">{t('Help')}</Link>
        </nav>
      </div>
    </div>
  )
}
