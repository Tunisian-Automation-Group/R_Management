import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LanguageSwitch } from '../components/AppShell.tsx'
import { Icon, type IconName } from '../components/Icon.tsx'
import { Button } from '../components/ui.tsx'
import { setDevice } from '../device.ts'
import { t } from '../../i18n.ts'
import { formatMoney } from '../../domain/money.ts'

/** What people rent here, as examples (UX-30): the product shown, not live
 *  listings, which are for members (GOAL 13). */
const EXAMPLES: { icon: IconName; what: string; price: number }[] = [
  { icon: 'drill', what: 'Plunge saw', price: 400 },
  { icon: 'truck', what: 'Cargo van', price: 2500 },
  { icon: 'camera', what: 'Photo studio', price: 4000 },
  { icon: 'printer', what: '3D printer', price: 600 },
]

const VALUES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: 'search',
    title: 'Book by the hour',
    body: 'A workshop for an afternoon, a van for a move, a 3D printer for one job. From people nearby.',
  },
  {
    icon: 'wallet',
    title: 'Earn from your own gear',
    body: 'List a tool, a room or a vehicle for the hours you do not need it. You choose who books, and you are paid after.',
  },
  {
    icon: 'shield',
    title: 'Safe by design',
    body: 'Everyone is a verified member, payments stay in Cappy, and both sides leave reviews.',
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
          <p className="t-h2 leading-none">
            Cappy
          </p>
          <div className="rounded-full bg-[var(--surface)]">
            <LanguageSwitch />
          </div>
        </header>

        <main id="main" className="flex flex-1 flex-col justify-center py-10 md:grid md:grid-cols-2 md:items-center md:gap-16">
          <div>
            <h1 className="t-display text-balance" style={{ fontSize: 'clamp(40px, 9vw, 72px)', lineHeight: 1.02 }}>
              {t('Rent tools, vans and workshops near you.')}
            </h1>
            <p className="t-body mt-4 max-w-[40ch] text-[var(--on-field-dim)]">
              {t('Book by the hour from people close by, and earn from your own gear when you are not using it.')}
            </p>
            <ul className="no-scrollbar -mx-6 mt-7 flex gap-2.5 overflow-x-auto px-6 md:mx-0 md:flex-wrap md:px-0" aria-label={t('For example')}>
              {EXAMPLES.map((e) => (
                <li key={e.what} className="glass glass-dark flex shrink-0 items-center gap-2.5 rounded-[var(--radius-m)] px-3.5 py-2.5">
                  <Icon name={e.icon} size={18} strokeWidth={1.8} />
                  <span className="text-label font-semibold">{t(e.what)}</span>
                  <span className="t-figure text-label text-[var(--on-field-dim)]">
                    {t('{price} / h', { price: formatMoney(e.price, 'EUR') })}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <ul className="mt-10 space-y-6 md:mt-0">
            {VALUES.map((v) => (
              <li key={v.title} className="flex gap-4">
                <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--on-field)] text-[var(--field)]">
                  <Icon name={v.icon} size={17} strokeWidth={2} />
                </span>
                <div>
                  <h2 className="text-body-l font-semibold">{t(v.title)}</h2>
                  <p className="t-sm mt-1 text-[var(--on-field-dim)]">{t(v.body)}</p>
                </div>
              </li>
            ))}
          </ul>
        </main>

        <div className="flex flex-col gap-3 md:mx-auto md:w-[360px]">
          {/* On the green plate the primary is ivory, not crimson (UX-30, F-6). */}
          <Button size="lg" block variant="onplate" onClick={() => nav('/login?mode=up', { replace: true })}>
            {t('Create an account')}
          </Button>
          <button
            type="button"
            onClick={() => nav('/login', { replace: true })}
            className="min-h-[48px] rounded-[var(--radius-capsule)] border border-[var(--on-field-dim)] px-4 text-body font-semibold"
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
