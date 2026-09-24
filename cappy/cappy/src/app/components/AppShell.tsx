import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { Icon, type IconName } from './Icon.tsx'
import { useBack } from '../nav.ts'

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
export function Dock({ badges }: { badges: Record<string, number> }) {
  const tabs: Tab[] = [
    { to: '/', label: 'Explore', icon: 'search' },
    { to: '/bookings', label: 'Bookings', icon: 'ticket', badge: badges['/bookings'] },
    { to: '/earn', label: 'Earn', icon: 'wallet', badge: badges['/earn'] },
    { to: '/profile', label: 'You', icon: 'user' },
  ]

  return (
    <nav
      aria-label="Main"
      className="glass fixed z-40 shadow-[var(--glass-shadow-raised)]
        max-md:bottom-0 max-md:left-1/2 max-md:w-[calc(100%-32px)] max-md:max-w-[420px]
        max-md:-translate-x-1/2 max-md:rounded-[28px]
        md:inset-x-0 md:top-0 md:h-[var(--header-h)]"
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
          {tabs.slice(0, 2).map((t) => (
            <TabItem key={t.to} tab={t} />
          ))}

          {/* On a phone, listing something is the supply side's whole job, so it
              stays one tap away in the middle of the dock. On a desktop it is the
              header's primary action and moves to the right, where a website
              puts one. */}
          <li className="flex shrink-0 items-center px-2 md:hidden">
            <NavLink
              to="/earn/new"
              aria-label="List capacity you own"
              className="grid h-[40px] w-[44px] place-items-center rounded-full bg-[var(--accent)] text-[var(--on-accent)]
                shadow-[var(--shadow-float)] transition-colors duration-[160ms] hover:bg-[var(--accent-hover)]"
            >
              <Icon name="plus" size={19} strokeWidth={2.4} />
            </NavLink>
          </li>

          {tabs.slice(2).map((t) => (
            <TabItem key={t.to} tab={t} />
          ))}
        </ul>

        <NavLink
          to="/earn/new"
          className="hidden shrink-0 items-center gap-2 rounded-full bg-[var(--accent)] px-4 py-2.5
            text-[14px] font-semibold text-[var(--on-accent)] shadow-[var(--shadow-float)]
            transition-colors duration-[160ms] hover:bg-[var(--accent-hover)] md:inline-flex"
        >
          <Icon name="plus" size={16} strokeWidth={2.4} />
          List capacity
        </NavLink>
      </div>
    </nav>
  )
}

function TabItem({ tab }: { tab: Tab }) {
  return (
    <li className="min-w-0 flex-1 md:flex-none">
      <NavLink
        to={tab.to}
        end={tab.to === '/'}
        className={({ isActive }) =>
          `relative flex h-full min-h-[56px] flex-col items-center justify-center gap-[3px] text-[10.5px]
           transition-colors duration-[160ms]
           md:min-h-0 md:flex-row md:gap-2 md:rounded-full md:px-3.5 md:py-2 md:text-[14px]
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
                className="absolute inset-x-2 inset-y-1.5 -z-10 rounded-[16px] bg-[var(--sunken)]
                  md:inset-0 md:rounded-full"
              />
            )}
            <span className="relative grid h-[21px] w-[21px] place-items-center">
              <Icon name={tab.icon} size={19} strokeWidth={isActive ? 2 : 1.7} />
              {tab.badge ? (
                <span
                  aria-hidden="true"
                  className="tnum absolute -right-2 -top-1 grid h-[15px] min-w-[15px] place-items-center rounded-[2px] bg-[var(--accent)] px-1 text-[9.5px] font-bold text-[var(--on-accent)]"
                >
                  {tab.badge}
                </span>
              ) : null}
            </span>
            {tab.label}
            {tab.badge ? <span className="sr-only">, {tab.badge} needing attention</span> : null}
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
}: {
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
              <div className="relative">
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

            <main className="px-5 pt-1 md:px-8">{children}</main>
          </div>

          {footer && (
            <aside
              className="sticky hidden md:block"
              style={{ top: 'calc(var(--header-h) + 24px)' }}
            >
              <div className="rounded-[24px] border border-[var(--line)] bg-[var(--surface)] p-5 shadow-[var(--shadow-float)]">
                {footer}
              </div>
            </aside>
          )}
        </div>

        <SiteFooter />
      </div>

      {footer && (
        <div
          className="fixed inset-x-0 z-30 px-4 md:hidden"
          style={{
            bottom: `calc(var(--dock-h) + 8px)`,
            paddingBottom: 'var(--safe-bottom-md)',
          }}
        >
          <div
            className="glass-strong mx-auto max-w-[560px] rounded-[24px] px-4 py-3
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
  const groups: { title: string; links: { label: string; to: string }[] }[] = [
    {
      title: 'Buy capacity',
      links: [
        { label: 'Explore what is free', to: '/' },
        { label: 'Your bookings', to: '/bookings' },
      ],
    },
    {
      title: 'Sell capacity',
      links: [
        { label: 'List something', to: '/earn/new' },
        { label: 'Your listings', to: '/earn' },
      ],
    },
    {
      title: 'Account',
      links: [
        { label: 'Profile', to: '/profile' },
        { label: 'How Cappy works', to: '/profile' },
      ],
    },
  ]

  return (
    <footer className="mt-24 hidden border-t border-[var(--line)] px-8 pb-16 pt-12 md:block">
      <div className="flex flex-wrap items-start justify-between gap-12">
        <div className="max-w-[30ch]">
          <p className="t-h2">Cappy</p>
          <p className="t-sm mt-2 text-[var(--ink-3)]">
            Buy the hours, not the thing. One capacity network across Europe:
            making, moving and the kit to do it with.
          </p>
        </div>
        {groups.map((g) => (
          <nav key={g.title} aria-label={g.title}>
            <p className="t-label">{g.title}</p>
            <ul className="mt-3 space-y-2">
              {g.links.map((l) => (
                <li key={l.label}>
                  <NavLink
                    to={l.to}
                    className="text-[14px] text-[var(--ink-2)] transition-opacity duration-[160ms] hover:opacity-60"
                  >
                    {l.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <p className="t-sm mt-12 border-t border-[var(--line)] pt-6 text-[var(--ink-4)]">
        A prototype. Owners, machines, prices and availability are realistic
        examples, not real businesses.
      </p>
    </footer>
  )
}

function BackButton({ onClick, floating }: { onClick: () => void; floating?: boolean }) {
  return (
    <button
      onClick={onClick}
      aria-label="Back"
      className={`grid h-10 w-10 place-items-center rounded-full transition-all duration-[160ms]
        ${
          floating
            ? 'glass glass-dark absolute left-4 z-10 hover:brightness-110'
            : '-ml-2.5 text-[var(--ink)] hover:bg-[var(--sunken)]'
        }`}
      style={floating ? { top: 'calc(var(--safe-top) + 12px)' } : undefined}
    >
      <Icon name="chevron-left" size={20} strokeWidth={2.2} />
    </button>
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
      {aside && <span className="tnum shrink-0 text-[13px] text-[var(--ink-4)]">{aside}</span>}
    </div>
  )
}
