import {
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react'
import { Link } from 'react-router-dom'
import { useNav } from '../nav.ts'
import { Icon, type IconName } from './Icon.tsx'
import { anySheetOpen, sheetOpened } from '../sheets.ts'
import { locale, t } from '../../i18n.ts'
import { currencySymbol, minorPerMajor } from '../../domain/money.ts'

/** The short motion token for micro-interactions, decelerating. Never linear. */
const TR =
  'transition-[background-color,border-color,color,opacity,transform,box-shadow] duration-[var(--dur-short)] ease-[var(--ease-standard)]'

/* ------------------------------------------------------------------ Button */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ink' | 'secondary' | 'quiet' | 'danger' | 'onplate'
  size?: 'lg' | 'md' | 'sm'
  icon?: IconName
  iconAfter?: IconName
  block?: boolean
  /** Navigation: renders a real link (opens in a new tab, shows its address). */
  to?: string
}

/**
 * Rectangles, not pills. A 3px radius is the whole concession, and it is the
 * same on every control so the shape carries no meaning of its own. The
 * primary is crimson and a screen gets one of them.
 */
export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  iconAfter,
  block,
  className = '',
  children,
  to,
  ...rest
}: ButtonProps) {
  const variants: Record<string, string> = {
    primary:
      'bg-[var(--accent)] text-[var(--on-accent)] hover:bg-[var(--accent-hover)] active:bg-[var(--accent-active)]',
    ink: 'bg-[var(--field)] text-[var(--on-field)] hover:bg-[var(--field-2)]',
    // The primary on a green plate: ivory, so crimson never sits on green.
    onplate: 'bg-[var(--on-field)] text-[var(--field)] hover:opacity-90',
    secondary:
      'bg-transparent text-[var(--ink)] border border-[var(--line-strong)] hover:border-[var(--ink)] hover:bg-[var(--sunken)]',
    quiet: 'bg-transparent text-[var(--ink-2)] hover:bg-[var(--sunken)] hover:text-[var(--ink)]',
    danger:
      'bg-transparent text-[var(--danger)] border border-[var(--line)] hover:border-[var(--danger)] hover:bg-[var(--danger-subtle)]',
  }
  // 44px is the floor for anything you tap. `sm` is only for inline chips that
  // sit inside a larger tap target.
  const sizes: Record<string, string> = {
    lg: 'min-h-[52px] px-7 text-body font-semibold gap-2',
    md: 'min-h-[48px] px-5 text-body font-semibold gap-1.5',
    sm: 'min-h-[44px] px-4 text-label font-semibold gap-1.5',
  }
  const cls = `press inline-flex items-center justify-center rounded-[var(--radius-capsule)] ${sizes[size]} ${variants[variant]} ${TR}
        disabled:pointer-events-none disabled:border-transparent disabled:bg-[var(--disabled-bg)] disabled:text-[var(--ink-4)] disabled:shadow-none ${block ? 'w-full' : ''} ${className}`
  const inner = (
    <>
      {icon && <Icon name={icon} size={size === 'lg' ? 19 : 17} strokeWidth={2} />}
      {children}
      {iconAfter && <Icon name={iconAfter} size={size === 'lg' ? 19 : 17} strokeWidth={2} />}
    </>
  )
  if (to) {
    return (
      <Link to={to} className={cls} aria-label={rest['aria-label']}>
        {inner}
      </Link>
    )
  }
  return (
    <button {...rest} className={cls}>
      {inner}
    </button>
  )
}

/* -------------------------------------------------------------------- Card */

export function Card({
  children,
  className = '',
  onClick,
  as,
  ariaLabel,
}: {
  children: ReactNode
  className?: string
  onClick?: () => void
  as?: 'article' | 'div'
  ariaLabel?: string
}) {
  // A block held by a hairline. There are no drop shadows in this system, so a
  // card is defined by its rule and its padding.
  const shared = `rounded-[var(--radius-card)] border border-[var(--line)] bg-[var(--surface)] ${className}`
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={ariaLabel}
        className={`press-soft ${shared} w-full text-left ${TR} hover:border-[var(--line-strong)]`}
      >
        {children}
      </button>
    )
  }
  const Tag = as ?? 'div'
  return <Tag className={shared}>{children}</Tag>
}

/* ------------------------------------------------------------------- Chips */

export function Chip({
  selected,
  children,
  onClick,
  ariaLabel,
}: {
  selected?: boolean
  children: ReactNode
  onClick: () => void
  ariaLabel?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      aria-label={ariaLabel}
      className={`press inline-flex min-h-[44px] min-w-[44px] max-w-full shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-capsule)] border px-3.5 py-1 text-left text-label font-medium ${TR}
        ${
          selected
            ? 'border-[var(--field)] bg-[var(--field)] font-semibold text-[var(--on-field)]'
            : 'border-[var(--line)] bg-transparent text-[var(--ink-2)] hover:border-[var(--ink-4)] hover:text-[var(--ink)]'
        }`}
    >
      {children}
    </button>
  )
}

export function Pill({
  children,
  tone = 'neutral',
  icon,
}: {
  children: ReactNode
  tone?: 'neutral' | 'accent' | 'success' | 'warn' | 'danger'
  icon?: IconName
}) {
  // A status word with a rule under it, not a coloured lozenge.
  const tones = {
    neutral: 'text-[var(--ink-4)] decoration-[var(--line-strong)]',
    accent: 'text-[var(--accent-text)] decoration-[var(--accent-muted)]',
    success: 'text-[var(--success-text)] decoration-[var(--success)]/40',
    warn: 'text-[var(--warn)] decoration-[var(--warn)]/40',
    danger: 'text-[var(--danger)] decoration-[var(--danger)]/40',
  }[tone]
  return (
    <span
      className={`inline-flex items-center gap-1 text-label font-semibold underline decoration-2 underline-offset-[5px] ${tones}`}
    >
      {icon && <Icon name={icon} size={13} strokeWidth={2.2} />}
      {children}
    </span>
  )
}

/* ------------------------------------------------------------------ Avatar */

export function Avatar({
  initials,
  size = 40,
  business,
}: {
  initials: string
  size?: number
  business?: boolean
}) {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size, fontSize: size * 0.34 }}
      className={`grid shrink-0 place-items-center rounded-[var(--radius-control)] font-semibold leading-none tracking-[0.02em] ${
        business
          ? 'bg-[var(--field)] text-[var(--on-field)]'
          : 'bg-[var(--sunken)] text-[var(--ink-2)]'
      }`}
    >
      {initials}
    </span>
  )
}

/* ------------------------------------------------------------------- Stars */

/** 4.7 in English, 4,7 in German. */
export const oneDecimal = (n: number) =>
  n.toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })

export function Stars({ value, count }: { value: number | null | undefined; count: number }) {
  if (value == null) {
    return <span className="t-sm text-[var(--ink-4)]">{t('New')}</span>
  }
  return (
    <span className="inline-flex items-center gap-1">
      <Icon name="star" size={12} className="fill-[var(--ink)] text-[var(--ink)]" strokeWidth={0} />
      <span className="tnum text-label font-semibold text-[var(--ink)]">{oneDecimal(value)}</span>
      <span className="tnum text-label text-[var(--ink-4)]">({count})</span>
    </span>
  )
}

/* ------------------------------------------------------------- Live marker */

/** "Free now": the one thing on screen that moves without being touched. */
export function LiveDot({ size = 8 }: { size?: number }) {
  return (
    <span className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <span className="pulse-ring absolute inset-0 rounded-full bg-[var(--accent)]" />
      <span className="relative rounded-full bg-[var(--accent)]" style={{ width: size, height: size }} />
    </span>
  )
}

/* ------------------------------------------------------------------- Forms */

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
  htmlFor?: string
}) {
  return (
    <div>
      {/* Label above the input: never a placeholder standing in for a label. */}
      <label htmlFor={htmlFor} className="mb-2 block text-label font-semibold text-[var(--ink-2)]">
        {label}
      </label>
      {children}
      {/* Error sits directly under its own field, never in a summary elsewhere. */}
      {error ? (
        <p id={htmlFor && `${htmlFor}-msg`} role="alert" className="mt-2 flex items-start gap-1.5 text-label text-[var(--danger)]">
          <Icon name="alert" size={14} className="mt-[2px] shrink-0" strokeWidth={2} />
          {error}
        </p>
      ) : hint ? (
        <p id={htmlFor && `${htmlFor}-msg`} className="mt-2 text-label leading-[1.125rem] text-[var(--ink-4)]">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

const fieldBase = `w-full min-h-[50px] rounded-[var(--radius-field)] border bg-[var(--surface)] px-3.5 text-body-l text-[var(--ink)]
  placeholder:text-[var(--ink-4)] ${TR}`
const fieldTone = (invalid?: boolean) =>
  invalid
    ? 'border-[var(--danger)]'
    : 'border-[var(--line-strong)] hover:border-[var(--ink-4)] focus:border-[var(--ink)]'

export function Input({
  invalid,
  className = '',
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      // The field's error or hint (Field gives it `<id>-msg`) is read with it.
      aria-describedby={rest.id ? `${rest.id}-msg` : undefined}
      {...rest}
      aria-invalid={invalid || undefined}
      className={`${fieldBase} ${fieldTone(invalid)} ${className}`}
    />
  )
}

/** A labelled checkbox with an optional line of explanation under the label. */
export function Check({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: ReactNode
  hint?: ReactNode
}) {
  return (
    <label className="flex items-start gap-3 rounded-[var(--radius-control)] border border-[var(--line)] p-4">
      <input
        type="checkbox"
        className="mt-1 h-5 w-5 shrink-0 accent-[var(--ink)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-body font-semibold text-[var(--ink)]">{label}</span>
        {hint && <span className="t-sm block text-[var(--ink-3)]">{hint}</span>}
      </span>
    </label>
  )
}

export function Textarea({
  invalid,
  className = '',
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return (
    <textarea
      aria-describedby={rest.id ? `${rest.id}-msg` : undefined}
      {...rest}
      aria-invalid={invalid || undefined}
      className={`${fieldBase} resize-none py-3.5 leading-[1.4375rem] ${fieldTone(invalid)} ${className}`}
    />
  )
}

export function Select({
  className = '',
  children,
  ...rest
}: InputHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <div className="relative">
      <select
        {...rest}
        className={`${fieldBase} ${fieldTone(false)} appearance-none pr-11 font-medium ${className}`}
      >
        {children}
      </select>
      <Icon
        name="chevron-down"
        size={17}
        strokeWidth={2.2}
        className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[var(--ink-3)]"
      />
    </div>
  )
}

/** Money in, minor units out. Keeps the caller from ever holding a float
 *  amount. The symbol and decimals are the currency's, in the reader's format. */
export function MoneyInput({
  cents,
  onCents,
  invalid,
  id,
  suffix,
  currency,
}: {
  cents: number
  onCents: (c: number) => void
  invalid?: boolean
  id?: string
  suffix?: string
  /** ISO 4217; the listing's market's (M-4). */
  currency?: string
}) {
  const minor = minorPerMajor(currency)
  const digits = Math.round(Math.log10(minor))
  // "4,00" in German, "4.00" in English, as prices show elsewhere. Either separator typed in works.
  const show = (c: number) =>
    new Intl.NumberFormat(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false }).format(
      (c || 0) / minor,
    )
  const [text, setText] = useState(() => show(cents))
  const symbol = currencySymbol(currency)
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-body-l text-[var(--ink-3)]">
        {symbol}
      </span>
      <Input
        id={id}
        inputMode="decimal"
        value={text}
        invalid={invalid}
        className="tnum pr-24 text-body-l font-semibold"
        style={{ paddingLeft: `calc(1.25rem + ${symbol.length}ch)` }}
        onChange={(e) => {
          const raw = e.target.value
          const v = raw.replace(',', '.')
          if (!new RegExp(`^\\d*\\.?\\d{0,${digits}}$`).test(v)) return
          setText(raw)
          const n = Number.parseFloat(v)
          onCents(Number.isFinite(n) ? Math.round(n * minor) : 0)
        }}
        onBlur={() => setText(show(cents))}
      />
      <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-label text-[var(--ink-4)]">
        {suffix ?? t('/ hour')}
      </span>
    </div>
  )
}

/* ------------------------------------------------------------- Segmented */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  const index = Math.max(0, options.findIndex((o) => o.value === value))
  return (
    <div
      role="tablist"
      aria-label={label}
      className="relative flex w-full border-b border-[var(--line)]"
    >
      {/* A rule that travels, the way a tab set should read. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[-1px] left-0 h-[2px] bg-[var(--ink)] transition-transform duration-[var(--dur-medium)] ease-[var(--ease-standard)]"
        style={{
          width: `${100 / options.length}%`,
          transform: `translateX(${index * 100}%)`,
        }}
      />
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.value)}
            className={`tap relative z-[1] min-h-[44px] min-w-0 flex-1 px-1.5 text-body [hyphens:manual] [overflow-wrap:anywhere] ${TR}
              ${on ? 'font-semibold text-[var(--ink)]' : 'font-medium text-[var(--ink-4)] hover:text-[var(--ink-2)]'}`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/* ----------------------------------------------------------------- Sheet */

const WIDE = '(min-width: 768px)'
/** True from the tablet breakpoint up, following resizes. */
function useWide(): boolean {
  const [wide, setWide] = useState(() => typeof matchMedia !== 'undefined' && matchMedia(WIDE).matches)
  useEffect(() => {
    const m = matchMedia(WIDE)
    const on = () => setWide(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return wide
}

export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  const titleId = useId()
  // Callers pass a fresh arrow each render; keep it in a ref so the effect
  // below runs only when the sheet opens, not on every keystroke inside it
  // (which moved focus to the first button and closed the sheet on Space).
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close.current()
      // A sheet is modal: keyboard focus must not escape behind it.
      if (e.key === 'Tab' && panel.current) {
        // Only what can take focus: the grabber is display:none on a dialog.
        const f = [
          ...panel.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
          ),
        ].filter((el) => el.getClientRects().length > 0)
        if (!f.length) return
        const first = f[0]
        const last = f[f.length - 1]
        // Focus outside the sheet (on the page behind, or the body) comes back in (V9-1).
        if (!panel.current.contains(document.activeElement)) {
          e.preventDefault()
          ;(e.shiftKey ? last : first).focus()
        } else if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    // Whatever opened the sheet gets focus back when it closes (V3-20, WCAG 2.4.3).
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.addEventListener('keydown', onKey)
    const unstack = sheetOpened(() => close.current())
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      unstack()
      document.body.style.overflow = prev
      if (opener?.isConnected) opener.focus()
    }
  }, [open])

  // UX-9: the sheet stays mounted while it leaves, so it can slide away rather
  // than vanish; on a phone it drags between a large and a medium height and
  // down to close; from 768 px it is a centred dialog.
  const [mounted, setMounted] = useState(open)
  const [leaving, setLeaving] = useState(false)
  const [detent, setDetent] = useState<'large' | 'medium'>('large')
  const [drag, setDrag] = useState<number | null>(null)
  const from = useRef<{ y: number; t: number } | null>(null)
  const wide = useWide()
  useEffect(() => {
    if (open) {
      setMounted(true)
      setLeaving(false)
      setDetent('large')
    } else setLeaving(true)
  }, [open])
  useEffect(() => {
    if (!leaving) return
    // The exit animation normally ends it; this is the floor if it never fires.
    const timer = setTimeout(() => setMounted(false), 400)
    return () => clearTimeout(timer)
  }, [leaving])

  // The panel mounts a render after `open` flips (UX-9), so focus moves in here,
  // once it exists: the first field if there is one, else the first control (V9-1).
  useEffect(() => {
    if (!open || !mounted || !panel.current) return
    if (panel.current.contains(document.activeElement)) return
    const p = panel.current
    const shown = (sel: string) => [...p.querySelectorAll<HTMLElement>(sel)].find((el) => el.getClientRects().length > 0)
    ;(shown('input:not([type=hidden]), select, textarea') ??
      shown('[data-sheet-body] button:not([disabled]), [data-sheet-body] [href]') ??
      shown('button:not([disabled])'))?.focus()
    // A sheet shorter than the medium height has one height only (V9-20).
    setResizable(p.scrollHeight > window.innerHeight * 0.55)
  }, [open, mounted])
  const [resizable, setResizable] = useState(true)

  if (!mounted) return null

  const onDown = (e: React.PointerEvent) => {
    if (wide || (e.target as HTMLElement).closest('[data-no-drag]')) return
    from.current = { y: e.clientY, t: performance.now() }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }
  const onMove = (e: React.PointerEvent) => {
    if (!from.current) return
    const dy = e.clientY - from.current.y
    // Up is resisted: a sheet can grow one detent, not float off the top.
    setDrag(dy < 0 ? dy / 3 : dy)
  }
  const onUp = (e: React.PointerEvent) => {
    if (!from.current) return
    const dy = e.clientY - from.current.y
    const speed = dy / Math.max(1, performance.now() - from.current.t)
    const height = panel.current?.offsetHeight ?? 600
    from.current = null
    setDrag(null)
    if (dy < -48 && detent === 'medium') setDetent('large')
    else if (dy > height * 0.3 || speed > 0.6) {
      if (detent === 'large' && dy < height * 0.5 && speed <= 0.6) setDetent('medium')
      else onClose()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center md:p-6" style={{ paddingLeft: 'env(safe-area-inset-left, 0px)', paddingRight: 'env(safe-area-inset-right, 0px)' }}>
      <div
        className={`${leaving ? 'anim-scrim-out' : 'anim-fade'} absolute inset-0 bg-[var(--scrim)]`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onAnimationEnd={(e) => {
          if (leaving && e.target === e.currentTarget) setMounted(false)
        }}
        className={`${leaving ? (wide ? 'anim-dialog-out' : 'anim-sheet-out') : wide ? 'anim-dialog' : 'anim-sheet'}
          sheet-pane relative flex w-full max-w-[540px] flex-col bg-[var(--elevated)] shadow-[var(--shadow-sheet)]
          ${
            // At the medium height a sheet floats, inset 8 with every corner
            // rounded; at the large height it meets the edges (VD-12, iOS 26).
            detent === 'medium'
              ? 'max-h-[55dvh] rounded-[var(--sheet-radius)] max-md:mx-2 max-md:mb-2'
              : 'max-h-[88dvh] rounded-t-[var(--sheet-radius)]'
          }
          md:mx-0 md:mb-0 md:max-h-[85dvh] md:rounded-[var(--sheet-radius)]`}
        style={{
          transform: drag ? `translateY(${drag}px)` : undefined,
          transition: drag === null ? 'transform var(--dur-medium) var(--ease-spring-spatial)' : 'none',
        }}
      >
        {/* The grabber: drag it (or the title bar) down to close or to the
            medium height, up to grow; it is also a button, so the height can
            be changed without a gesture. Not on a dialog. */}
        <div onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} className="touch-none md:touch-auto">
        {resizable ? (
          <button
            type="button"
            data-no-drag
            onClick={() => setDetent((d) => (d === 'large' ? 'medium' : 'large'))}
            aria-label={detent === 'large' ? t('Make the sheet smaller') : t('Make the sheet bigger')}
            className="tap mx-auto mt-1 flex h-6 w-16 items-center justify-center md:hidden"
          >
            <span aria-hidden="true" className="h-[5px] w-9 rounded-full bg-[var(--line-strong)] opacity-60" />
          </button>
        ) : (
          <span aria-hidden="true" className="mx-auto mt-1 flex h-6 w-16 items-center justify-center md:hidden">
            <span className="h-[5px] w-9 rounded-full bg-[var(--line-strong)] opacity-60" />
          </span>
        )}
        <div className="flex items-center justify-between gap-3 px-5 pb-2 pt-3 md:pt-5">
          <h2 id={titleId} className="t-title-m min-w-0">
            {title}
          </h2>
          <button
            data-no-drag
            onClick={onClose}
            aria-label={t('Close')}
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[var(--sunken)] text-[var(--ink-2)] ${TR} hover:text-[var(--ink)]`}
          >
            <Icon name="close" size={18} strokeWidth={2.2} />
          </button>
        </div>
        </div>
        <div data-sheet-body className="sheet-body min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-4 pt-3">{children}</div>
        {footer && (
          <div
            className="px-5 pt-3"
            style={{ paddingBottom: 'max(18px, env(safe-area-inset-bottom))' }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------- States & feedback */

/** Skeletons mirror the real layout so nothing jumps when content lands. */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton rounded-[var(--radius-control)] ${className}`} aria-hidden="true" />
}

/** A detail page while it loads: the photo, the title and a few lines, in the
 *  places they will be, so nothing jumps when the page arrives. */
export function DetailSkeleton() {
  return (
    <div className="space-y-4 pt-2" role="status" aria-label={t('Loading')}>
      <Skeleton className="aspect-[4/3] w-full rounded-[var(--radius-m)] md:aspect-[21/9]" />
      <Skeleton className="h-8 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-24 w-full" />
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: IconName
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="anim-rise border-t border-[var(--line)] py-14">
      <Icon name={icon} size={20} className="mb-5 text-[var(--ink-4)]" strokeWidth={1.6} />
      <h2 className="t-h2 mb-2 max-w-[20ch]">{title}</h2>
      <p className="t-body mb-6 max-w-[42ch] text-[var(--ink-3)]">{body}</p>
      {action}
    </div>
  )
}

export function Banner({
  tone,
  title,
  body,
  action,
}: {
  tone: 'accent' | 'success' | 'warn' | 'danger' | 'neutral'
  title: string
  body?: ReactNode
  action?: ReactNode
}) {
  const map = {
    // Reassurance, not a warning (UX-50): calm ink and a shield.
    neutral: { bg: 'border-[var(--line-strong)]', fg: 'text-[var(--ink)]', icon: 'shield' },
    accent: { bg: 'border-[var(--accent)]', fg: 'text-[var(--accent-text)]', icon: 'info' },
    success: { bg: 'border-[var(--success)]', fg: 'text-[var(--success-text)]', icon: 'check' },
    warn: { bg: 'border-[var(--warn)]', fg: 'text-[var(--warn)]', icon: 'info' },
    danger: { bg: 'border-[var(--danger)]', fg: 'text-[var(--danger)]', icon: 'alert' },
  }[tone]
  return (
    <div className={`anim-rise flex gap-3 border-l-2 ${map.bg} bg-[var(--sunken)] py-4 pl-4 pr-4`}>
      <Icon
        name={map.icon as IconName}
        size={18}
        className={`mt-[2px] shrink-0 ${map.fg} ${tone === 'success' ? 'anim-draw' : ''}`}
        strokeWidth={2.4}
      />
      <div className="min-w-0">
        <p className={`text-body font-semibold ${map.fg}`}>{title}</p>
        {body && <div className="mt-1 text-label leading-[1.1875rem] text-[var(--ink-2)]">{body}</div>}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  )
}

export function Row({
  label,
  value,
  strong,
  tone,
}: {
  label: ReactNode
  value: ReactNode
  strong?: boolean
  tone?: 'accent' | 'muted'
}) {
  const color =
    tone === 'accent' ? 'text-[var(--accent-text)]' : tone === 'muted' ? 'text-[var(--ink-4)]' : ''
  return (
    // Label and value side by side, and stacked when the text is large (J-11).
    <div className="flex flex-wrap items-baseline justify-between gap-x-5 gap-y-0.5 py-2.5">
      <span className="t-sm min-w-0 text-[var(--ink-3)]">{label}</span>
      {/* Values wrap rather than run off the edge. Some of them are sentences. */}
      <span
        className={`tnum ml-auto min-w-0 text-right ${strong ? 'text-body-l font-bold' : 'text-body font-medium'} ${color}`}
      >
        {value}
      </span>
    </div>
  )
}

/* ------------------------------------------------------------------ Toast */

export function Toast({ message, tone = 'ok', onDone }: { message: string; tone?: 'ok' | 'error'; onDone: () => void }) {
  // As in Sheet: a fresh onDone each render must not restart the timer.
  const done = useRef(onDone)
  done.current = onDone
  useEffect(() => {
    // An error stays long enough to be read and acted on.
    const t = setTimeout(() => done.current(), tone === 'error' ? 6000 : 2800)
    return () => clearTimeout(t)
  }, [message, tone])
  const [overSheet] = useState(anySheetOpen)
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      aria-live={tone === 'error' ? 'assertive' : 'polite'}
      className="anim-pop safe-x pointer-events-none fixed inset-x-0 z-[60] flex justify-center"
      style={
        overSheet
          ? { top: 'calc(var(--safe-top, 0px) + 12px)' }
          : { bottom: 'calc(var(--dock-h) + var(--footer-h, 0px) + var(--safe-bottom-md) + 20px)' }
      }
    >
      <div className="flex items-center gap-2.5 rounded-[var(--radius-control)] bg-[var(--field)] py-3 pl-3.5 pr-5 text-body font-semibold text-[var(--on-field)]">
        {tone === 'error' ? (
          <span className="grid h-5 w-5 shrink-0 place-items-center rounded-[var(--radius-xs)] bg-[var(--danger)] text-[var(--on-status)]">
            <Icon name="info" size={14} strokeWidth={2.6} />
          </span>
        ) : (
          <span className="grid h-5 w-5 shrink-0 place-items-center rounded-[var(--radius-xs)] bg-[var(--sky)] text-[var(--field)]">
            {/* The tick draws itself once the toast appears. */}
            <Icon name="check" size={14} strokeWidth={3} className="anim-draw" />
          </span>
        )}
        {message}
      </div>
    </div>
  )
}

/** A real link (an address on hover, open in a new tab, announced as a link)
 *  whose plain tap still runs the app's own transition (V9-16). */
export function TapLink({
  to,
  className,
  children,
  prefetch,
  ...rest
}: {
  to: string
  className?: string
  children: ReactNode
  /** Loads the next screen first (for up to 350 ms) so the shared elements have somewhere to land. */
  prefetch?: () => Promise<unknown>
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  const nav = useNav()
  return (
    <a
      {...rest}
      href={to}
      className={className}
      onClick={(e) => {
        rest.onClick?.(e)
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
        e.preventDefault()
        // The hour tag and the photo travel into the listing (VD-16): named on
        // the tapped card only, since a view-transition name must be unique. The
        // card unmounts with the screen, so the names leave with it.
        const tag = e.currentTarget.closest('[data-card]')?.querySelector<HTMLElement>('[data-hour]')
        if (tag) {
          tag.style.viewTransitionName = 'hour'
          if (tag.parentElement) tag.parentElement.style.viewTransitionName = 'hero'
        }
        if (!prefetch) return nav(to)
        void Promise.race([prefetch(), new Promise((ok) => setTimeout(ok, 350))]).finally(() => nav(to))
      }}
    >
      {children}
    </a>
  )
}
