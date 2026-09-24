import { useState, type CSSProperties, type ReactNode } from 'react'
import type { CategoryId, Iso, Slot } from '../../domain/types.ts'
import { Plate } from './Cover.tsx'
import { time } from '../format.ts'
import { useCappy } from '../store.tsx'
import { Icon } from './Icon.tsx'

/**
 * A listing's cover photograph.
 *
 * The plate used to be the picture. That was a defensible idea when a listing
 * had no image to show, and it is the wrong idea now that owners photograph
 * their own kit: a wall of dark panels reading "9h", "7h", "6h", "9h" tells you
 * exactly when four things are free and never once what any of them is. The
 * photograph answers "what", which is the question a buyer asks first.
 *
 * The plate survives as the fallback here, and as the surface for figures that
 * genuinely are the content, like the idle-hours band.
 */
export function Photo({
  src,
  alt,
  slots,
  categoryId,
  aspect = 4 / 3,
  className = '',
  style,
  priority = false,
  children,
}: {
  src?: string
  alt: string
  /** Drawn when there is no photograph yet. */
  slots: Slot[]
  categoryId: CategoryId
  aspect?: number
  className?: string
  style?: CSSProperties
  /** Above the fold: load now rather than when scrolled near. */
  priority?: boolean
  children?: ReactNode
}) {
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)

  if (!src || failed) {
    return (
      <span className={`relative block overflow-hidden ${className}`} style={style}>
        <Plate slots={slots} categoryId={categoryId} aspect={aspect} detail="hero" />
        {children}
      </span>
    )
  }

  return (
    <span
      className={`relative block overflow-hidden bg-[var(--sunken)] ${className}`}
      style={{ aspectRatio: String(aspect), ...style }}
    >
      <img
        src={src}
        alt={alt}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={() => setFailed(true)}
        // Fades in over the paper tone instead of popping, so a grid still
        // loading reads as settling rather than broken.
        className={`h-full w-full object-cover transition-opacity duration-300 ${loaded ? 'opacity-100' : 'opacity-0'}`}
      />
      {/* A photograph is somebody's uncontrolled upload, so anything laid over it
          needs a guaranteed floor to sit on. The scrim only covers the bottom
          third, where the chip goes. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3
          bg-gradient-to-t from-[rgba(24,33,26,0.55)] to-transparent"
      />
      {children}
    </span>
  )
}

/**
 * The one piece of colour discipline in the whole grid, and the product's thesis
 * in about sixty pixels: ice means you can have it right now, white means you can
 * have it later, crimson means this is the window you are booking.
 */
export function WhenChip({
  start,
  state = 'later',
  className = '',
}: {
  start: Iso
  state?: 'now' | 'later' | 'booked'
  className?: string
}) {
  const label =
    state === 'now' ? 'Free now' : state === 'booked' ? `Booked ${time(start)}` : `From ${time(start)}`

  return (
    <span
      className={`glass glass-dark tnum absolute bottom-3 left-3 rounded-full px-2.5 py-1
        text-[12px] font-semibold ${className}`}
      style={{
        // A photograph can be any colour, so the chip carries a darker tint than
        // glass over a known surface needs. At 42% over a pale upload it went
        // olive and the label stopped being legible.
        ['--glass-tint-dark' as string]: 'rgba(20, 30, 19, 0.66)',
        color:
          state === 'now'
            ? 'var(--sky)'
            : state === 'booked'
              ? 'var(--accent-bright)'
              : 'var(--on-field)',
      }}
    >
      {label}
    </span>
  )
}

/**
 * Keep it for later. Buyers compare three printers before booking one, and
 * without a shortlist the only way to come back to something was to search for
 * it again. Sits on the photograph, top right, where every marketplace has
 * taught people to look for it; the click stops at the heart and never opens
 * the card underneath.
 */
export function SaveButton({
  id,
  title,
  className = 'absolute right-3 top-3',
}: {
  id: string
  title: string
  className?: string
}) {
  const { state, send } = useCappy()
  const on = state.saved.includes(id)
  return (
    <span
      role="button"
      tabIndex={0}
      aria-pressed={on}
      aria-label={on ? `Remove ${title} from saved` : `Save ${title}`}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        send({ type: on ? 'LISTING_UNSAVED' : 'LISTING_SAVED', id })
        send({ type: 'TOAST', message: on ? 'Removed from saved' : 'Saved. Find it under You' })
      }}
      onKeyDown={(e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return
        e.preventDefault()
        e.stopPropagation()
        send({ type: on ? 'LISTING_UNSAVED' : 'LISTING_SAVED', id })
      }}
      className={`glass glass-dark grid h-9 w-9 cursor-pointer place-items-center rounded-full
        transition-transform duration-[160ms] active:scale-90 ${className}`}
      style={{ ['--glass-tint-dark' as string]: 'rgba(20, 30, 19, 0.5)' }}
    >
      <Icon
        name="heart"
        size={17}
        strokeWidth={2}
        className={on ? 'fill-[var(--accent-bright)] text-[var(--accent-bright)]' : 'text-[var(--on-field)]'}
      />
    </span>
  )
}
