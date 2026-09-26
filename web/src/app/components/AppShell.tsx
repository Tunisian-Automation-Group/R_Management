import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useSession } from '../../data/auth.ts'
import { Icon, type IconName } from './Icon.tsx'
import { useBack } from '../nav.ts'
import { LANGS, lang, locale, setLang, t } from '../../i18n.ts'
import { updateLocale } from '../../data/auth.ts'
import { setAppearance, useAppearance, type Appearance } from '../theme.ts'

type Tab = { to: string; label: string; icon: IconName; badge?: number }

/**
 * One dock for both sides of the market, with listing as a visible action.
 *
 * There is deliberately no find/host mode switch. Vinted, eBay and Depop all
 * keep a single nav with a persistent sell action, which suits someone who
 * borrows and lends in the same week. Airbnb's mode flip earns its place
 * because hosting there is a business with a calendar and a pricing strategy.
 * A neighbour with a drill is not running one, and a mode you can be in
 * without noticing is a mode you get lost in.
 *
 * On a phone it floats as a glass capsule rather than sitting as a ruled bar on
 * the bottom edge. The earlier objection to a capsule was that chrome hovering
 * over the content draws attention to itself, and with an opaque bar that was
 * true. Glass inverts it: the content shows through, so the dock reads as a lens
 * over the page rather than a second surface competing with it.
 *
 * On a desktop it is a top bar, because that is what a website is. The previous
 * left rail was a phone dock turned on its side: it kept the app's furniture at
 * a width where nobody expects app furniture, and it pushed the content into a
 * 760px column with 500px of nothing beside it. Same tabs, same badges, read in
 * the place a browser has trained everyone to look.
 */
// Detail screens own the bottom of a phone for their action bar (UX-13): the
// dock steps aside there and comes back one level up.
const DETAIL = /^\/(listing\/|bookings\/[^/]+|earn\/(new|edit)|inbox\/[^/]+|admin\/)/

export function Dock({ badges }: { badges: Record<string, number> }) {
  const big = useLargeText()
  const detail = DETAIL.test(useLocation().pathname)
  useEffect(() => {
    // The sticky bars, the offline bar and toasts measure from --dock-h.
    document.documentElement.dataset.dock = detail ? 'hidden' : 'shown'
  }, [detail])
  const tabs: Tab[] = [
    { to: '/', label: t('Explore'), icon: 'search' },
    { to: '/bookings', label: t('Bookings'), icon: 'ticket', badge: badges['/bookings'] },
    // Conversations across bookings, unread counted by the server (UX-12).
    { to: '/inbox', label: t('Inbox'), icon: 'chat', badge: badges['/inbox'] },
    { to: '/earn', label: t('Earn'), icon: 'wallet', badge: badges['/earn'] },
    { to: '/profile', label: t('You'), icon: 'user', badge: badges['/notifications'] },
  ]

  return (
    <nav
      aria-label={t('Main')}
      className={`glass fixed z-40 shadow-[var(--glass-shadow-raised)] ${detail ? 'max-md:hidden' : ''}
        max-md:bottom-0 max-md:left-1/2 max-md:w-[calc(100%-32px)] max-md:max-w-[420px]
        max-md:-translate-x-1/2 max-md:rounded-[var(--radius-l)]
        md:inset-x-0 md:top-0 md:h-[var(--header-h)]`}
      style={{ viewTransitionName: 'dock' }}
    >
      <div
        className="mx-auto flex h-[56px] items-stretch px-1
          md:h-full md:max-w-[1180px] md:items-center md:gap-8 md:px-8"
      >
        {/* The wordmark belongs in the header on a website, so Browse drops its
            own masthead above md rather than printing it twice. */}
        <NavLink
          to="/"
          className="t-h2 hidden shrink-0 leading-none md:block"
          style={{ fontSize: 26 }}
        >
          Cappy
        </NavLink>

        <ul className="flex flex-1 items-stretch md:items-center md:gap-1">
          {tabs.slice(0, 2).map((tab) => (
            <TabItem key={tab.to} tab={tab} big={big} />
          ))}

          {/* On a phone, listing something is the supply side's whole job, so it
              stays one tap away in the middle of the dock. On a desktop it is the
              header's primary action and moves to the right, where a website
              puts one. */}
          <li className="flex shrink-0 items-center px-2 md:hidden">
            <NavLink
              to="/earn/new"
              aria-label={t('List capacity you own')}
              className="grid h-[40px] w-[44px] place-items-center rounded-full bg-[var(--accent)] text-[var(--on-accent)]
                shadow-[var(--shadow-float)] transition-colors duration-[var(--dur-short)] hover:bg-[var(--accent-hover)]"
            >
              <Icon name="plus" size={19} strokeWidth={2.4} />
            </NavLink>
          </li>

          {tabs.slice(2).map((tab) => (
            <TabItem key={tab.to} tab={tab} big={big} />
          ))}
        </ul>

        <NavLink
          to="/notifications"
          aria-label={
            badges['/notifications'] ? t('Notifications, {n} unread', { n: badges['/notifications'] }) : t('Notifications')
          }
          className="relative hidden h-10 w-10 shrink-0 place-items-center rounded-full text-[var(--ink-2)] hover:bg-[var(--sunken)] md:grid"
        >
          <Icon name="bell" size={19} strokeWidth={1.8} />
          {badges['/notifications'] ? (
            <span
              aria-hidden="true"
              className="tnum absolute right-1 top-1 grid h-[15px] min-w-[15px] place-items-center rounded-[var(--radius-xs)] bg-[var(--badge)] px-1 text-caption font-bold text-[var(--on-badge)]"
            >
              {badges['/notifications']}
            </span>
          ) : null}
        </NavLink>

        <NavLink
          to="/earn/new"
          className="hidden shrink-0 items-center gap-2 rounded-full bg-[var(--accent)] px-4 py-2.5
            text-body font-semibold text-[var(--on-accent)] shadow-[var(--shadow-float)]
            transition-colors duration-[var(--dur-short)] hover:bg-[var(--accent-hover)] md:inline-flex"
        >
          <Icon name="plus" size={16} strokeWidth={2.4} />
          {t('List capacity')}
        </NavLink>
      </div>
    </nav>
  )
}

/** Large text (200 %, Dynamic Type): four labels do not fit a phone's dock, so
 *  it shows icons and keeps the names for screen readers (V5-28). */
function useLargeText(): boolean {
  const read = () => typeof document !== 'undefined' && parseFloat(getComputedStyle(document.documentElement).fontSize) >= 24
  const [big, setBig] = useState(read)
  useEffect(() => {
    // A 1rem probe: its size follows the root font, so a text-size change after
    // the first render (Dynamic Type, a browser zoom of text) is seen too (V6-7).
    const probe = document.createElement('span')
    probe.setAttribute('aria-hidden', 'true')
    probe.style.cssText = 'position:absolute;visibility:hidden;width:1rem;height:0;pointer-events:none'
    document.body.appendChild(probe)
    const on = () => setBig(read())
    const watch = new ResizeObserver(on)
    watch.observe(probe)
    window.addEventListener('resize', on)
    return () => {
      watch.disconnect()
      window.removeEventListener('resize', on)
      probe.remove()
    }
  }, [])
  return big
}

function TabItem({ tab, big }: { tab: Tab; big: boolean }) {
  return (
    <li className="min-w-0 flex-1 md:flex-none">
      <NavLink
        to={tab.to}
        end={tab.to === '/'}
        className={({ isActive }) =>
          // The label is capped at 14 px and truncates: four labels in a 390 px dock
          // overlapped at 200 % text (V4-12); the link's name stays whole for screen readers.
          `relative flex h-full min-h-[56px] min-w-0 flex-col items-center justify-center gap-[3px] text-[min(0.6562rem,14px)]
           transition-colors duration-[var(--dur-short)]
           md:min-h-0 md:flex-row md:gap-3 md:rounded-full md:px-3.5 md:py-2 md:text-body
           ${
             isActive
               ? 'font-semibold text-[var(--ink)]'
               : 'font-medium text-[var(--ink-4)] hover:text-[var(--ink-2)]'
           }`
        }
      >
        {({ isActive }) => (
          <>
            {/* A capsule has no top edge to rule, so the active tab is marked
                by a lozenge sitting behind the icon instead. */}
            {isActive && (
              <span
                aria-hidden="true"
                className="absolute inset-x-2 inset-y-1.5 -z-10 rounded-[var(--radius-m)] bg-[var(--sunken)]
                  md:inset-0 md:rounded-full"
              />
            )}
            <span className="relative grid h-[21px] w-[21px] place-items-center">
              <Icon name={tab.icon} size={19} strokeWidth={isActive ? 2 : 1.7} />
              {tab.badge ? (
                <span
                  aria-hidden="true"
                  // On the icon's corner, clear of the label beside it on a desktop (V5-29).
                  className="tnum absolute -right-2 -top-1 grid h-[15px] min-w-[15px] place-items-center rounded-[var(--radius-xs)] bg-[var(--badge)] px-1 text-caption font-bold text-[var(--on-badge)] md:-right-1.5 md:-top-2"
                >
                  {tab.badge}
                </span>
              ) : null}
            </span>
            <span className={big ? 'sr-only md:not-sr-only' : 'block max-w-full truncate px-0.5'}>{tab.label}</span>
            {tab.badge ? <span className="sr-only">, {t('{n} needing attention', { n: tab.badge })}</span> : null}
          </>
        )}
      </NavLink>
    </li>
  )
}

/**
 * The frame every screen sits in. It owns the safe-area top and the space
 * reserved at the bottom for the floating dock (`--dock-h`), both of which
 * drift out of sync when screens set them individually. A sticky footer sits
 * above the dock.
 */
export function Screen({
  title,
  sub,
  eyebrow,
  back,
  action,
  children,
  footer,
  hero,
  wide = false,
  tone = 'page',
  docTitle,
}: {
  /** The browser tab's title; defaults to `title` when that is plain text. */
  docTitle?: string
  title?: ReactNode
  sub?: ReactNode
  /** A small ruled label above the title, the section this screen belongs to. */
  eyebrow?: string
  back?: string
  action?: ReactNode
  children: ReactNode
  footer?: ReactNode
  /** Full-bleed content above the title, a cover, a hero number. */
  hero?: ReactNode
  /**
   * A catalogue or a product page, which wants the full 1,120px. Everything else
   * (requests, listings, bookings, a profile) is a column you read down, and at
   * 1,120px its cards and buttons stretched into 1,700px bars with a line of text
   * in the corner. A screen with a buy box is always wide.
   */
  wide?: boolean
  tone?: 'page' | 'surface'
}) {
  const isWide = wide || Boolean(footer)
  const goBack = useBack(back ?? '/')
  const tabTitle = docTitle ?? (typeof title === 'string' ? title : undefined)
  useEffect(() => {
    document.title = tabTitle ? `${tabTitle} · Cappy` : 'Cappy'
  }, [tabTitle])
  // The phone's sticky bar publishes its height as --footer-h, so the offline
  // bar and toasts sit above it instead of on its button (V3-9, V3-18).
  const bar = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = bar.current
    if (!el) return
    const root = document.documentElement.style
    const set = () => root.setProperty('--footer-h', `${el.offsetHeight}px`)
    set()
    const ro = new ResizeObserver(set)
    ro.observe(el)
    return () => {
      ro.disconnect()
      root.removeProperty('--footer-h')
    }
  }, [Boolean(footer)])
  return (
    <div
      className={`anim-screen min-h-dvh ${tone === 'surface' ? 'bg-[var(--surface)]' : ''}`}
      style={{
        paddingTop: 'var(--header-h)',
        paddingBottom: `calc(var(--dock-h) + ${footer ? 96 : 40}px)`,
      }}
    >
      {/* 560px is a phone column. 1120px is a page. The old 760px was neither,
          and on a laptop it left a third of the window empty beside the content. */}
      <div className={`mx-auto w-full max-w-[560px] ${isWide ? 'md:max-w-[1120px]' : 'md:max-w-[760px]'}`}>
        {/* A screen with a footer is a screen with something to buy, which on a
            page is the product-page shape: the thing on the left, the box that
            commits you on the right. The bottom bar is a phone affordance; kept
            on a desktop it just floats over the middle of a very wide column. */}
        <div
          className={
            footer ? 'md:grid md:grid-cols-[minmax(0,1fr)_340px] md:items-start md:gap-12' : ''
          }
        >
          <div className="min-w-0">
            {hero ? (
              // On a page the photo sits in the content column, below the
              // header, with all four corners: flush against the bar it read
              // as clipped, and it started left of the text under it.
              <div className="relative md:px-8 md:pt-6">
                {hero}
                {back && <BackButton onClick={goBack} floating />}
              </div>
            ) : (
              <div style={{ height: 'var(--safe-top)' }} aria-hidden="true" />
            )}

            {(title || back || action) && (
              <header className={`px-5 md:px-8 ${hero ? 'pt-6' : 'pt-4'} pb-3 md:pb-6`}>
                {back && !hero && (
                  <div className="mb-4">
                    <BackButton onClick={goBack} />
                  </div>
                )}
                {eyebrow && <p className="t-label mb-2">{eyebrow}</p>}
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    {title && <h1 className="t-h1 text-balance">{title}</h1>}
                    {sub && <p className="t-body mt-2 max-w-[46ch] text-[var(--ink-3)]">{sub}</p>}
                  </div>
                  {action && <div className="shrink-0 pt-1">{action}</div>}
                </div>
              </header>
            )}

            <main id="main" tabIndex={-1} className="px-5 pt-1 outline-none md:px-8">
              {children}
            </main>
          </div>

          {footer && (
            <aside
              className="sticky hidden md:block"
              style={{ top: 'calc(var(--header-h) + 24px)' }}
            >
              <div className="rounded-[var(--radius-l)] border border-[var(--line)] bg-[var(--surface)] p-5 shadow-[var(--shadow-float)]">
                {footer}
              </div>
            </aside>
          )}
        </div>

        <SiteFooter />
      </div>

      {footer && (
        <div
          ref={bar}
          className="safe-x fixed inset-x-0 z-30 md:hidden"
          style={{
            bottom: `calc(var(--dock-h) + 8px)`,
            paddingBottom: 'var(--safe-bottom-md)',
          }}
        >
          <div
            className="glass-strong mx-auto max-w-[560px] rounded-[var(--radius-l)] px-4 py-3
              shadow-[var(--glass-shadow-raised)]"
          >
            {footer}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Desktop only. A phone has the dock at the bottom of every screen and nothing
 * below it, so a footer there is just more to scroll past. A page that ends
 * without one reads as an app someone stretched, which is the whole complaint.
 */
function SiteFooter() {
  const session = useSession()
  const staff = session?.staff ?? false
  const groups: { title: string; links: { label: string; to: string }[] }[] = [
    {
      title: t('Buy capacity'),
      links: [
        { label: t('Explore what is free'), to: '/' },
        { label: t('Your bookings'), to: '/bookings' },
      ],
    },
    {
      title: t('Sell capacity'),
      links: [
        { label: t('List something'), to: '/earn/new' },
        { label: t('Your listings'), to: '/earn' },
      ],
    },
    {
      title: t('Account'),
      links: [
        { label: t('Profile'), to: '/profile' },
        { label: t('How Cappy works'), to: '/help/how' },
        { label: t('Help'), to: '/help' },
      ],
    },
  ]

  return (
    <footer className="mt-24 hidden border-t border-[var(--line)] px-8 pb-16 pt-12 md:block">
      <div className="flex flex-wrap items-start justify-between gap-12">
        <div className="max-w-[30ch]">
          <p className="t-h2">Cappy</p>
          <p className="t-sm mt-2 text-[var(--ink-3)]">
            {t('Buy the hours, not the thing. One capacity network: making, moving and the kit to do it with.')}
          </p>
          <div className="mt-5">
            <LanguageSwitch />
          </div>
        </div>
        {/* Signed out, the product is not there to link to (GOAL 13). */}
        {(session ? groups : []).map((g) => (
          <nav key={g.title} aria-label={g.title}>
            <p className="t-label">{g.title}</p>
            <ul className="mt-3 space-y-2">
              {g.links.map((l) => (
                <li key={l.label}>
                  <NavLink
                    to={l.to}
                    className="text-body text-[var(--ink-2)] transition-opacity duration-[var(--dur-short)] hover:opacity-60"
                  >
                    {l.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <nav aria-label={t('Legal')} className="t-sm mt-12 flex flex-wrap gap-x-6 gap-y-2 border-t border-[var(--line)] pt-6 text-[var(--ink-4)]">
        <NavLink to="/legal/impressum" className="hover:text-[var(--ink-2)]">Impressum</NavLink>
        <NavLink to="/legal/privacy" className="hover:text-[var(--ink-2)]">{t('Privacy')}</NavLink>
        <NavLink to="/legal/terms" className="hover:text-[var(--ink-2)]">{t('Terms')}</NavLink>
        <NavLink to="/legal/withdrawal" className="hover:text-[var(--ink-2)]">{t('Withdrawal')}</NavLink>
        <NavLink to="/legal/ranking" className="hover:text-[var(--ink-2)]">{t('Ranking')}</NavLink>
        <NavLink to="/legal/report" className="hover:text-[var(--ink-2)]">{t('Report content')}</NavLink>
        <NavLink to="/legal/accessibility" className="hover:text-[var(--ink-2)]">{t('Accessibility')}</NavLink>
        <NavLink to="/account/delete" className="hover:text-[var(--ink-2)]">{t('Delete your account')}</NavLink>
        {staff && <NavLink to="/admin" className="hover:text-[var(--ink-2)]">{t('Staff')}</NavLink>}
      </nav>
    </footer>
  )
}

function BackButton({ onClick, floating }: { onClick: () => void; floating?: boolean }) {
  return (
    <button
      onClick={onClick}
      aria-label={t('Back')}
      className={`grid h-10 w-10 place-items-center rounded-full transition-all duration-[var(--dur-short)]
        ${
          floating
            ? 'glass glass-dark absolute left-4 z-10 hover:brightness-110 md:left-12 md:mt-6'
            : '-ml-2.5 text-[var(--ink)] hover:bg-[var(--sunken)]'
        }`}
      style={floating ? { top: 'calc(var(--safe-top) + 12px)' } : undefined}
    >
      <Icon name="chevron-left" size={20} strokeWidth={2.2} />
    </button>
  )
}

/** English, Deutsch or Français. Remounts the app in the new language, and
 *  tells Cognito (the `locale` attribute) so emails follow. */
export function LanguageSwitch() {
  const current = lang()
  const options = LANGS
  return (
    <div role="group" aria-label={t('Language')} className="inline-flex max-w-full flex-wrap rounded-[var(--radius-l)] border border-[var(--line)] p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          lang={o.value}
          aria-pressed={current === o.value}
          onClick={() => {
            // The language, then the full locale it gives with the device's region (en-US, fr-CA).
            void setLang(o.value).then(() => updateLocale(locale()))
          }}
          className={`rounded-full px-3 py-1.5 text-label font-semibold transition-colors duration-[var(--dur-short)] ${
            current === o.value ? 'bg-[var(--field)] text-[var(--on-field)]' : 'text-[var(--ink-3)] hover:text-[var(--ink)]'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** System, Light or Dark (UX-36), stored on this device. */
export function AppearanceSwitch() {
  const current = useAppearance()
  const options: { value: Appearance; label: string }[] = [
    { value: 'system', label: t('System') },
    { value: 'light', label: t('Light') },
    { value: 'dark', label: t('Dark') },
  ]
  return (
    <div role="group" aria-label={t('Appearance')} className="inline-flex max-w-full flex-wrap rounded-[var(--radius-l)] border border-[var(--line)] p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={current === o.value}
          onClick={() => setAppearance(o.value)}
          className={`rounded-full px-3 py-1.5 text-label font-semibold transition-colors duration-[var(--dur-short)] ${
            current === o.value ? 'bg-[var(--field)] text-[var(--on-field)]' : 'text-[var(--ink-3)] hover:text-[var(--ink)]'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** A section heading with a rule above it, and room for a figure on the right. */
export function SectionHead({
  title,
  aside,
  className = '',
}: {
  title: ReactNode
  aside?: ReactNode
  className?: string
}) {
  return (
    <div
      className={`flex items-baseline justify-between gap-4 border-t border-[var(--ink)] pb-3 pt-3 ${className}`}
    >
      <h2 className="t-h3 min-w-0">{title}</h2>
      {aside && <span className="tnum shrink-0 text-label text-[var(--ink-4)]">{aside}</span>}
    </div>
  )
}
