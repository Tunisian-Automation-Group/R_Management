import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useSession } from '../../data/auth.ts'
import { useToast } from '../store.tsx'
import { Icon, type IconName } from './Icon.tsx'
import { useBack, useNav } from '../nav.ts'
import { LANGS, lang, locale, plural, setLang, t, tTab } from '../../i18n.ts'
import { updateLocale } from '../../data/auth.ts'
import { setAppearance, toggleTheme, useAppearance, useDark, type Appearance } from '../theme.ts'

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
 * On a phone it is an opaque bar on the bottom edge, a hairline above it and
 * the home indicator's inset inside it (Material 3's navigation bar, Airbnb,
 * Vinted). It used to float as a glass capsule; content showed through and
 * collided with its labels, which read as broken rather than as a lens.
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
  const path = useLocation().pathname
  const detail = DETAIL.test(path)
  useEffect(() => {
    // The sticky bars, the offline bar and toasts measure from --dock-h.
    document.documentElement.dataset.dock = detail ? 'hidden' : 'shown'
  }, [detail])
  const nav = useRef<HTMLElement>(null)
  useHideOnScroll(nav, detail)
  const tabs: Tab[] = [
    { to: '/', label: t('Explore'), icon: 'search' },
    { to: '/bookings', label: tTab('Bookings'), icon: 'ticket', badge: badges['/bookings'] },
    // Conversations across bookings, unread counted by the server (UX-12).
    { to: '/inbox', label: tTab('Inbox'), icon: 'chat', badge: badges['/inbox'] },
    { to: '/earn', label: t('Earn'), icon: 'wallet', badge: badges['/earn'] },
    // No badge on You: the bell keeps its own count (UX-46).
    { to: '/profile', label: t('You'), icon: 'user' },
  ]

  const active = tabs.findIndex((tab) => (tab.to === '/' ? path === '/' : path.startsWith(tab.to)))

  return (
    <nav
      ref={nav}
      aria-label={t('Main')}
      className={`glass dock fixed z-40 ${detail ? 'max-md:hidden' : ''}
        md:inset-x-0 md:top-0 md:h-[var(--header-h)] md:rounded-none md:shadow-[var(--glass-shadow-raised)]`}
      style={{ viewTransitionName: 'dock' }}
    >
      <div
        className="mx-auto flex h-[var(--dock-bar-h)] items-stretch px-1.5
          md:h-full md:max-w-[1180px] md:items-center md:gap-8 md:px-8"
      >
        {/* The wordmark belongs in the header on a website, so Browse drops its
            own masthead above md rather than printing it twice. */}
        <NavLink
          to="/"
          className="t-h2 wordmark hidden shrink-0 leading-none md:block"
          style={{ fontSize: 26 }}
        >
          Cappy
        </NavLink>

        {/* Five destinations and nothing else, as Material 3's navigation bar
            and the large marketplace apps (Airbnb, Vinted, Instagram) do on a
            phone. Listing something lives on Earn, where the supply side is,
            not as a sixth, louder button in the bar. */}
        <ul className="relative flex flex-1 items-stretch md:items-center md:gap-1">
          {/* The droplet (VD-6): one lit capsule behind the active tab that
              slides between them on the snappy spring. Phone only. */}
          {active >= 0 && (
            <li aria-hidden="true" className="dock-droplet md:hidden" style={{ ['--i' as string]: active }}>
              <span />
            </li>
          )}
          {tabs.map((tab) => (
            <TabItem key={tab.to} tab={tab} big={big} />
          ))}
        </ul>

        <ThemeToggle className="hidden md:grid" />

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

/** One tap, Light → Dark → System (UX-48), said in a toast; tapping again
 *  undoes it. The full setting is the first section of You. */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const dark = useDark()
  const toast = useToast()
  const label = dark ? t('Switch to light mode') : t('Switch to dark mode')
  const names: Record<Appearance, string> = { light: t('Light'), dark: t('Dark'), system: t('System') }
  return (
    <button
      type="button"
      onClick={() => toast(t('Appearance: {mode}', { mode: names[toggleTheme()] }))}
      aria-label={label}
      title={label}
      className={`h-11 w-11 shrink-0 place-items-center rounded-full text-[var(--ink-2)]
        transition-colors duration-[var(--dur-short)] hover:bg-[var(--sunken)] hover:text-[var(--ink)] ${className || 'grid'}`}
    >
      <Icon name={dark ? 'sun' : 'moon'} size={20} strokeWidth={1.8} />
    </button>
  )
}

/** Hide on scroll (UX-46, iOS 26's minimise simplified): after 48 px of
 *  scrolling down, past the first screen, the bar slides away; any scroll up
 *  of 8 px, the top of the page, or focus inside it brings it back. CSS keeps
 *  it in place under reduced motion. */
function useHideOnScroll(nav: RefObject<HTMLElement | null>, detail: boolean) {
  useEffect(() => {
    const el = nav.current
    if (!el || detail) return
    let anchor = scrollY
    let away = false
    const set = (next: boolean) => {
      if (next === away) return
      away = next
      el.dataset.scrolled = next ? 'away' : ''
    }
    const onScroll = () => {
      const y = scrollY
      if (y <= 0) {
        set(false)
        anchor = 0
      } else if (y > anchor) {
        // Going down: hide once 48 px past where the downward run began, and
        // never within the first screen height.
        if (away) anchor = y
        else if (y - anchor >= 48 && y > 64) {
          set(true)
          anchor = y
        }
      } else if (!away) anchor = y
      else if (anchor - y >= 8) {
        set(false)
        anchor = y
      }
    }
    const onFocus = () => set(false)
    addEventListener('scroll', onScroll, { passive: true })
    el.addEventListener('focusin', onFocus)
    return () => {
      removeEventListener('scroll', onScroll)
      el.removeEventListener('focusin', onFocus)
      set(false)
    }
  }, [nav, detail])
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
  const nav = useNav()
  return (
    <li className="min-w-0 flex-1 md:flex-none">
      <NavLink
        to={tab.to}
        end={tab.to === '/'}
        // A plain tap crossfades between tabs (UX-8, V9-3); modified clicks keep
        // the link's own behaviour (new tab, new window).
        onClick={(e) => {
          if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
          e.preventDefault()
          nav(tab.to)
        }}
        className={({ isActive }) =>
          // The label is capped at 14 px and truncates: labels overlapped at 200 %
          // text (V4-12); the link's name stays whole for screen readers.
          `group relative flex h-full min-h-[var(--dock-bar-h)] min-w-0 flex-col items-center justify-center gap-1
           text-[length:var(--dock-label-size)] leading-[var(--dock-label-line)] transition-colors duration-[var(--dur-short)]
           md:min-h-0 md:flex-row md:gap-3 md:rounded-full md:px-3.5 md:py-2 md:text-body
           ${
             isActive
               ? 'font-semibold text-[var(--ink)] md:bg-[var(--dock-active)]'
               : 'font-medium text-[var(--dock-ink)] hover:text-[var(--ink)]'
           }`
        }
      >
        {({ isActive }) => (
          <>
            {/* Material 3's active indicator: a pill behind the icon only, the
                label under it in the strong ink. */}
            <span
              className={`relative grid h-[var(--dock-pill-h)] w-[var(--dock-pill-w)] shrink-0 place-items-center rounded-full transition-colors duration-[var(--dur-short)]
                md:h-auto md:w-auto md:bg-transparent
                ${isActive ? 'text-[var(--dock-active-ink)]' : 'md:group-hover:bg-[var(--sunken)]'}`}
            >
              <span className="relative grid h-[var(--dock-icon)] w-[var(--dock-icon)] place-items-center">
                {/* The filled variant when active (HIG: "prefer filled"). */}
                <Icon name={tab.icon} size={24} strokeWidth={1.75} duotone={isActive} />
                {tab.badge ? (
                  <span
                    aria-hidden="true"
                    // The icon's top-right corner at (−4, −4), ringed in the bar's
                    // colour so it reads as sitting on top, never clipped (cappy-ui §4).
                    className="tnum absolute right-[var(--dock-badge-off)] top-[var(--dock-badge-off)] grid h-[var(--dock-badge)] min-w-[var(--dock-badge)] place-items-center rounded-full bg-[var(--badge)] px-[var(--dock-badge-pad)] text-[length:var(--dock-badge-text)] font-bold leading-none text-[var(--on-badge)]
                      ring-2 ring-[var(--elevated)] md:ring-0"
                  >
                    {tab.badge > 9 ? '9+' : tab.badge}
                  </span>
                ) : null}
              </span>
            </span>
            {/* Never truncated (UX-46): the labels fit at 12 px in EN, DE and FR
                down to 360; at 200 % text the bar shows icons only. */}
            <span className={big ? 'sr-only md:not-sr-only' : 'dock-label block whitespace-nowrap'}>{tab.label}</span>
            {tab.badge ? <span className="sr-only">, {plural(tab.badge, '{n} needs your attention', '{n} need your attention')}</span> : null}
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
        paddingBottom: `calc(var(--dock-h) + ${footer ? 96 : 16}px)`,
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
                <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
                  <div className="min-w-0">
                    {title && <h1 className="t-large-title text-balance">{title}</h1>}
                    {sub && <p className="t-body mt-2 max-w-[46ch] text-[var(--ink-3)]">{sub}</p>}
                  </div>
                  {action && <div className="max-w-full shrink-0 pt-1">{action}</div>}
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
          <p className="t-h2 wordmark">Cappy</p>
          <p className="t-sm mt-2 text-[var(--ink-3)]">
            {t('Buy the hours, not the thing. One capacity network: making, moving and the kit to do it with.')}
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <LanguageSwitch />
            <AppearanceSwitch />
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
            current === o.value ? 'bg-[var(--segment-on)] text-[var(--on-segment)]' : 'text-[var(--ink-3)] hover:text-[var(--ink)]'
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
    { value: 'light', label: t('Light') },
    { value: 'dark', label: t('Dark') },
    { value: 'system', label: t('System') },
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
            current === o.value ? 'bg-[var(--segment-on)] text-[var(--on-segment)]' : 'text-[var(--ink-3)] hover:text-[var(--ink)]'
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
