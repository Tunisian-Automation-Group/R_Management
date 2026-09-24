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
import { Icon, type IconName } from './Icon.tsx'

/** 160ms for micro-interactions, decelerating. Never linear. */
const TR =
  'transition-[background-color,border-color,color,opacity,transform,box-shadow] duration-[160ms] ease-[cubic-bezier(0.2,0,0,1)]'

/* ------------------------------------------------------------------ Button */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ink' | 'secondary' | 'quiet' | 'danger'
  size?: 'lg' | 'md' | 'sm'
  icon?: IconName
  iconAfter?: IconName
  block?: boolean
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
  ...rest
}: ButtonProps) {
  const variants: Record<string, string> = {
    primary:
      'bg-[var(--accent)] text-[var(--on-accent)] hover:bg-[var(--accent-hover)] active:bg-[var(--accent-active)]',
    ink: 'bg-[var(--field)] text-[var(--on-field)] hover:bg-[var(--field-2)]',
    secondary:
      'bg-transparent text-[var(--ink)] border border-[var(--line-strong)] hover:border-[var(--ink)] hover:bg-[var(--sunken)]',
    quiet: 'bg-transparent text-[var(--ink-2)] hover:bg-[var(--sunken)] hover:text-[var(--ink)]',
    danger:
      'bg-transparent text-[var(--danger)] border border-[var(--line)] hover:border-[var(--danger)] hover:bg-[var(--danger-subtle)]',
  }
  // 44px is the floor for anything you tap. `sm` is only for inline chips that
  // sit inside a larger tap target.
  const sizes: Record<string, string> = {
    lg: 'min-h-[52px] px-7 text-[15px] font-semibold gap-2',
    md: 'min-h-[44px] px-5 text-[14px] font-semibold gap-1.5',
    sm: 'tap min-h-[34px] px-3.5 text-[13px] font-semibold gap-1.5',
  }
  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center rounded-[var(--radius-control)] ${sizes[size]} ${variants[variant]} ${TR}
        disabled:pointer-events-none disabled:opacity-30 ${block ? 'w-full' : ''} ${className}`}
    >
      {icon && <Icon name={icon} size={size === 'lg' ? 19 : 17} strokeWidth={2} />}
      {children}
      {iconAfter && <Icon name={iconAfter} size={size === 'lg' ? 19 : 17} strokeWidth={2} />}
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
        className={`${shared} w-full text-left ${TR} hover:border-[var(--line-strong)]`}
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
      className={`tap inline-flex min-h-[38px] shrink-0 items-center gap-1.5 rounded-[var(--radius-control)] border px-3.5 text-[13.5px] font-medium ${TR}
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
      className={`inline-flex items-center gap-1 text-[12.5px] font-semibold underline decoration-2 underline-offset-[5px] ${tones}`}
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

export function Stars({ value, count }: { value: number | null; count: number }) {
  if (value === null) {
    return <span className="t-sm text-[var(--ink-4)]">New</span>
  }
  return (
    <span className="inline-flex items-center gap-1">
      <Icon name="star" size={12} className="fill-[var(--ink)] text-[var(--ink)]" strokeWidth={0} />
      <span className="tnum text-[13px] font-semibold text-[var(--ink)]">{value.toFixed(1)}</span>
      <span className="tnum text-[13px] text-[var(--ink-4)]">({count})</span>
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
      <label htmlFor={htmlFor} className="mb-2 block text-[13.5px] font-semibold text-[var(--ink-2)]">
        {label}
      </label>
      {children}
      {/* Error sits directly under its own field, never in a summary elsewhere. */}
      {error ? (
        <p role="alert" className="mt-2 flex items-start gap-1.5 text-[13px] text-[var(--danger)]">
          <Icon name="alert" size={14} className="mt-[2px] shrink-0" strokeWidth={2} />
          {error}
        </p>
      ) : hint ? (
        <p className="mt-2 text-[13px] leading-[18px] text-[var(--ink-4)]">{hint}</p>
      ) : null}
    </div>
  )
}

const fieldBase = `w-full min-h-[50px] rounded-[var(--radius-field)] border bg-[var(--surface)] px-3.5 text-[16px] text-[var(--ink)]
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
      {...rest}
      aria-invalid={invalid || undefined}
      className={`${fieldBase} ${fieldTone(invalid)} ${className}`}
    />
  )
}

export function Textarea({
  invalid,
  className = '',
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return (
    <textarea
      {...rest}
      aria-invalid={invalid || undefined}
      className={`${fieldBase} resize-none py-3.5 leading-[23px] ${fieldTone(invalid)} ${className}`}
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

/** Money in, cents out. Keeps the caller from ever holding a float euro. */
export function MoneyInput({
  cents,
  onCents,
  invalid,
  id,
  suffix = '/ hour',
}: {
  cents: number
  onCents: (c: number) => void
  invalid?: boolean
  id?: string
  suffix?: string
}) {
  const [text, setText] = useState(() => (cents / 100).toFixed(2))
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[16px] text-[var(--ink-3)]">
        €
      </span>
      <Input
        id={id}
        inputMode="decimal"
        value={text}
        invalid={invalid}
        className="tnum pl-8 pr-24 text-[17px] font-semibold"
        onChange={(e) => {
          const v = e.target.value.replace(',', '.')
          if (!/^\d*\.?\d{0,2}$/.test(v)) return
          setText(v)
          const n = Number.parseFloat(v)
          onCents(Number.isFinite(n) ? Math.round(n * 100) : 0)
        }}
        onBlur={() => setText(((cents || 0) / 100).toFixed(2))}
      />
      <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[13px] text-[var(--ink-4)]">
        {suffix}
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
        className="pointer-events-none absolute bottom-[-1px] left-0 h-[2px] bg-[var(--ink)] transition-transform duration-[260ms] ease-[cubic-bezier(0.2,0,0,1)]"
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
            className={`tap relative z-[1] min-h-[44px] flex-1 px-3 text-[14px] ${TR}
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

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      // A sheet is modal: keyboard focus must not escape behind it.
      if (e.key === 'Tab' && panel.current) {
        const f = panel.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        )
        if (!f.length) return
        const first = f[0]
        const last = f[f.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.querySelector<HTMLElement>('button, input, [tabindex]')?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div className="anim-fade absolute inset-0 bg-[var(--scrim)]" onClick={onClose} aria-hidden="true" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="anim-sheet glass relative flex max-h-[88dvh] w-full max-w-[540px] flex-col
          rounded-t-[var(--radius-sheet)] shadow-[var(--shadow-sheet)]"
      >
        {/* The grab handle the kit puts on every sheet. Decorative: the sheet is
            dismissed by the close button and by the scrim, not by dragging. */}
        <span
          aria-hidden="true"
          className="mx-auto mt-2.5 h-[5px] w-9 shrink-0 rounded-full bg-[var(--line-strong)] opacity-40"
        />
        <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-5 pb-4 pt-3">
          <h2 id={titleId} className="t-h2 min-w-0">
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-[var(--radius-control)] text-[var(--ink-3)] ${TR} hover:bg-[var(--sunken)] hover:text-[var(--ink)]`}
          >
            <Icon name="close" size={18} strokeWidth={2.2} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-2 pt-5">{children}</div>
        {footer && (
          <div
            className="border-t border-[var(--line)] px-5 pt-4"
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
  tone: 'accent' | 'success' | 'warn' | 'danger'
  title: string
  body?: string
  action?: ReactNode
}) {
  const map = {
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
        <p className={`text-[14.5px] font-semibold ${map.fg}`}>{title}</p>
        {body && <p className="mt-1 text-[13.5px] leading-[19px] text-[var(--ink-2)]">{body}</p>}
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
    <div className="flex items-baseline justify-between gap-5 py-2.5">
      <span className="t-sm min-w-0 text-[var(--ink-3)]">{label}</span>
      {/* Values wrap rather than run off the edge. Some of them are sentences. */}
      <span
        className={`tnum min-w-0 text-right ${strong ? 'text-[18px] font-bold' : 'text-[14.5px] font-medium'} ${color}`}
      >
        {value}
      </span>
    </div>
  )
}

/* ------------------------------------------------------------------ Toast */

export function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 2800)
    return () => clearTimeout(t)
  }, [message, onDone])
  return (
    <div
      role="status"
      aria-live="polite"
      className="anim-pop pointer-events-none fixed inset-x-0 z-[60] flex justify-center px-4"
      style={{ bottom: 'calc(var(--dock-h) + 20px)' }}
    >
      <div className="flex items-center gap-2.5 rounded-[var(--radius-control)] bg-[var(--field)] py-3 pl-3.5 pr-5 text-[14px] font-semibold text-[var(--on-field)]">
        <span className="grid h-5 w-5 place-items-center rounded-[2px] bg-[var(--sky)] text-[var(--field)]">
          {/* The tick draws itself once the toast appears. */}
          <Icon name="check" size={14} strokeWidth={3} className="anim-draw" />
        </span>
        {message}
      </div>
    </div>
  )
}
