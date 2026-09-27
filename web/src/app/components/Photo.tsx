import { createContext, useContext, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { useNav } from '../nav.ts'
import type { CategoryId, Iso, Slot } from '../../domain/types.ts'
import { Plate } from './Cover.tsx'
import { day, time } from '../format.ts'

import { useSession } from '../../data/auth.ts'
import { mediaUrl, useSaveToggle, useSaved, type PhotoMeta } from '../../data/repo.ts'
import { messageOf, useToast } from '../store.tsx'
import { Icon } from './Icon.tsx'
import { t } from '../../i18n.ts'

/** Widths for the browser to choose from (UX-3), where the host can make
 *  them. ponytail: only resizing CDNs that take `w=`; our own media needs the
 *  400/800/1600 renditions from the media service first (U-40). */
function srcSetOf(src: string, meta?: PhotoMeta): string | undefined {
  // Our own uploads: the media service's renditions, <hash>-<w>.webp (U-40).
  if (meta?.widths.length) return meta.widths.map((w) => `${mediaUrl(src.replace(/\.webp$/, `-${w}.webp`))} ${w}w`).join(', ')
  if (!/^https:\/\/images\.unsplash\.com\//.test(src)) return undefined
  const at = (w: number) => `${src.replace(/([?&])w=\d+/, `$1w=${w}`)} ${w}w`
  return [400, 800, 1600].map(at).join(', ')
}

/**
 * Demo photographs that do not show their listing's kind of thing (VD-3):
 * an electrician for a plunge saw, smokestacks for 3D printers, a till for a
 * sander. Checked by eye against every seeded listing's category. These show
 * the designed category plate instead, which is honest about having no photo.
 * ponytail: a denylist of seed photo ids; the fix at the source is category-
 * true photos in backend seed.json, then this set can go.
 */
const MISMATCHED = new Set([
  '1581092918056-0c4c3acd3789', '1621905251189-08b45d6a269e', '1517420704952-d9f39e95b43e',
  '1611273426858-450d8e3c9fce', '1581092160562-40aa08e78837', '1516110833967-0b5716ca1387',
  '1581578731548-c64695cc6952', '1452860606245-08befc0ff44b', '1581094288338-2314dddb7ece',
  '1565043666747-69f6646db940', '1595246140625-573b715d11dc', '1574359411659-15573a27fd0c',
  '1611117775350-ac3950990985', '1556740738-b6a63e27c4df', '1567789884554-0b844b597180',
])
const mismatched = (src: string) => MISMATCHED.has(/photo-([0-9a-f-]+)/.exec(src)?.[1] ?? '')

/**
 * One grid of listings (UX-1): the same photograph never shows twice in it.
 * The first card to show a picture keeps it; any later card with the same
 * picture shows its designed category plate instead, which says honestly that
 * there is no photo of this thing, rather than a second copy of someone else's.
 */
const GridClaims = createContext<Map<string, string> | null>(null)
export function PhotoGrid({ children }: { children: ReactNode }) {
  const claims = useMemo(() => new Map<string, string>(), [])
  return <GridClaims.Provider value={claims}>{children}</GridClaims.Provider>
}

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
  meta,
  children,
  thumb = false,
  claim,
  width,
  sizes,
}: {
  /** A small square in a list: the fallback drawing drops its words. */
  /** The upload's renditions and colour, from the listing detail (U-40). */
  meta?: PhotoMeta
  thumb?: boolean
  /** Inside a PhotoGrid: who is showing this picture (the listing id). */
  claim?: string
  /** The rendered width in CSS px, for the image's intrinsic size (CLS). */
  width?: number
  /** The `sizes` hint for the browser's pick among `srcset` widths. */
  sizes?: string
  src?: string
  alt: string
  /** Drawn when there is no photograph yet. */
  slots?: Slot[]
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
  const claims = useContext(GridClaims)
  let taken = false
  if (claims && src && claim) {
    const holder = claims.get(src)
    if (holder === undefined) claims.set(src, claim)
    else taken = holder !== claim
  }

  if (!src || failed || taken || mismatched(src)) {
    return (
      <span className={`relative block overflow-hidden ${className}`} style={style}>
        <Plate slots={slots} categoryId={categoryId} aspect={aspect} detail={thumb ? 'thumb' : 'hero'} />
        {children}
      </span>
    )
  }

  return (
    <span
      className={`relative block overflow-hidden ${className}`}
      // The photo's own colour while it loads, not a grey box (UX-3); with no
      // stored colour, the lit plate of its category (VD-3).
      style={{ aspectRatio: String(aspect), ...(meta?.color ? { backgroundColor: meta.color } : {}), ...style }}
    >
      {!loaded && !meta?.color && (
        <span aria-hidden="true" className="absolute inset-0">
          <Plate categoryId={categoryId} aspect={aspect} detail={thumb ? 'thumb' : 'hero'} className="h-full w-full" />
        </span>
      )}
      <img
        src={mediaUrl(src)}
        srcSet={srcSetOf(src, meta)}
        sizes={sizes ?? (thumb ? '64px' : '(min-width: 768px) 50vw, 100vw')}
        width={width ?? 800}
        height={Math.round((width ?? 800) / aspect)}
        alt={alt}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={() => setFailed(true)}
        // Fades in over the paper tone instead of popping, so a grid still
        // loading reads as settling rather than broken.
        className={`relative h-full w-full object-cover transition-opacity duration-[var(--dur-long)] ${loaded ? 'opacity-100' : 'opacity-0'}`}
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
  // "From 21:30" today, "From tomorrow 09:00" otherwise: the earliest start
  // anyone could actually book, never a time already out of reach.
  const at = day(start) === t('today') ? time(start) : `${day(start)} ${time(start)}`
  const label = state === 'now' ? t('Free now') : state === 'booked' ? t('Booked {at}', { at }) : t('From {at}', { at })

  return (
    <span
      // The hour tag (VD-9/10): media glass for text, dark enough that white
      // holds 4.5:1 over the palest photo (check:contrast measures it).
      className={`glass-media-text tnum absolute bottom-4 left-4 rounded-full px-3 py-1.5
        text-label font-semibold ${className}`}
      style={{
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
  const session = useSession()
  const saved = useSaved()
  const flip = useSaveToggle()
  const toast = useToast()
  const nav = useNav()
  // While a tap is in flight, show what it asked for; then what the server holds.
  const on =
    flip.isPending && flip.variables.id === id
      ? flip.variables.on
      : Boolean(saved.data?.items.some((v) => v.listing.id === id))
  const toggle = () => {
    if (!session) {
      nav(`/login?next=${encodeURIComponent(location.pathname)}`)
      return
    }
    flip.mutate(
      { id, on: !on },
      {
        onSuccess: () => toast(on ? t('Removed from saved') : t('Saved. Find it under You')),
        onError: (err) => toast(messageOf(err), 'error'),
      },
    )
  }
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={on ? t('Remove {title} from saved', { title }) : t('Save {title}', { title })}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        toggle()
      }}
      // shrink-0 + square: a row that runs out of room at 200 % text must not squash it into a pill (V4-12).
      className={`glass-media glass-lens z-10 grid h-11 w-11 shrink-0 aspect-square cursor-pointer place-items-center rounded-full
        transition-transform duration-[var(--dur-snappy)] ease-[var(--spring-bouncy)] active:scale-90 ${className}`}
    >
      <Icon
        name="heart"
        size={17}
        strokeWidth={2}
        className={on ? 'fill-[var(--accent-bright)] text-[var(--accent-bright)]' : 'text-[var(--on-field)]'}
      />
    </button>
  )
}
