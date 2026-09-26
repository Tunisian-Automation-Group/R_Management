// A listing's photographs (UX-2): a swipe strip with "n / N" on a phone, a
// mosaic on a wide screen, and a full-screen viewer from either. One photo is
// still a photo you can open; none is the designed category plate.
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { CategoryId, Slot } from '../../domain/types.ts'
import { Photo } from './Photo.tsx'
import { Icon } from './Icon.tsx'
import { mediaUrl, type PhotoMeta } from '../../data/repo.ts'
import { sheetOpened } from '../sheets.ts'
import { t } from '../../i18n.ts'

export function Gallery({
  photos,
  meta,
  title,
  slots,
  categoryId,
  overlay,
  style,
}: {
  photos: string[]
  /** Parallel to photos: renditions and colours (U-40). */
  meta?: PhotoMeta[]
  title: string
  slots?: Slot[]
  categoryId: CategoryId
  /** Badges laid over the first photo (the category, when it is free). */
  overlay?: ReactNode
  style?: CSSProperties
}) {
  const [open, setOpen] = useState<number | null>(null)
  const [at, setAt] = useState(0)
  const strip = useRef<HTMLDivElement>(null)
  const alt = (i: number) => (photos.length > 1 ? t('Photo {n} of {total}, {title}', { n: i + 1, total: photos.length, title }) : title)

  if (photos.length === 0) {
    return (
      <Photo alt={title} slots={slots} categoryId={categoryId} aspect={16 / 10} priority className="w-full md:rounded-[var(--sheet-radius)]" style={style}>
        {overlay}
      </Photo>
    )
  }

  const onScroll = () => {
    const el = strip.current
    if (el) setAt(Math.round(el.scrollLeft / Math.max(1, el.clientWidth)))
  }

  return (
    <div className="relative" style={style}>
      {/* Phone: one photo a screen, swiped. */}
      <div
        ref={strip}
        onScroll={onScroll}
        className="no-scrollbar flex snap-x snap-mandatory overflow-x-auto md:hidden"
        aria-label={t('Photos')}
      >
        {photos.map((src, i) => (
          <button key={src + i} type="button" onClick={() => setOpen(i)} className="w-full shrink-0 snap-start" aria-label={t('Open {what}', { what: alt(i) })}>
            <Photo src={src} meta={meta?.[i]} alt={alt(i)} categoryId={categoryId} aspect={4 / 3} priority={i === 0} width={800} sizes="100vw" className="w-full" />
          </button>
        ))}
      </div>
      {photos.length > 1 && (
        <span className="glass glass-dark tnum pointer-events-none absolute bottom-3 right-3 rounded-full px-2.5 py-1 text-label font-semibold md:hidden" aria-hidden="true">
          {at + 1} / {photos.length}
        </span>
      )}

      {/* Wide: a mosaic laid out for the number of photos, so no cell is ever
          empty (V9-6): 1 full, 2 halves, 3 and 5 a large photo with a column or
          a 2×2 beside it, 4 a large photo with three stacked. */}
      {(() => {
        const n = Math.min(photos.length, 5)
        const grid =
          n === 1 ? 'md:grid-cols-1' : n === 2 ? 'md:grid-cols-2' : n === 3 ? 'md:grid-cols-[2fr_1fr] md:grid-rows-2' : n === 4 ? 'md:grid-cols-[2fr_1fr] md:grid-rows-3' : 'md:grid-cols-[2fr_1fr_1fr] md:grid-rows-2'
        const big = n === 3 || n === 5 ? 'md:row-span-2' : n === 4 ? 'md:row-span-3' : ''
        const small = n === 4 ? 2 : 4 / 3
        return (
          <div className={`relative hidden gap-2 overflow-hidden rounded-[var(--sheet-radius)] md:grid ${grid}`}>
            {photos.slice(0, n).map((src, i) => (
              <button
                key={src + i}
                type="button"
                onClick={() => setOpen(i)}
                aria-label={t('Open {what}', { what: alt(i) })}
                className={`press-soft block w-full overflow-hidden ${i === 0 ? big : ''}`}
              >
                <Photo
                  src={src}
                  meta={meta?.[i]}
                  alt={alt(i)}
                  categoryId={categoryId}
                  aspect={n === 1 ? 16 / 10 : i === 0 || n === 2 ? 4 / 3 : small}
                  priority={i === 0}
                  width={i === 0 || n === 2 ? 1100 : 400}
                  sizes={i === 0 || n === 2 ? '(min-width: 768px) 60vw, 100vw' : '20vw'}
                  className="h-full w-full"
                />
              </button>
            ))}
            {photos.length > 1 && (
              <button type="button" onClick={() => setOpen(0)} className="glass glass-strong absolute bottom-4 right-4 rounded-[var(--radius-s)] px-3.5 py-2 text-label font-semibold">
                {t('Show all {n} photos', { n: photos.length })}
              </button>
            )}
          </div>
        )
      })()}
      {overlay}
      {open !== null && <Viewer photos={photos} alt={alt} start={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

/** Full screen, one photo at a time, pinch-zoomable; arrows, swipe or keys.
 *  A modal <dialog> on the top layer (UX-49): nothing on the page, not the
 *  sticky price bar nor the back button, can paint over it, and the page
 *  behind is inert. Black in both themes; APG carousel roles. */
function Viewer({ photos, alt, start, onClose }: { photos: string[]; alt: (i: number) => string; start: number; onClose: () => void }) {
  const [i, setI] = useState(start)
  const box = useRef<HTMLDialogElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  const go = (d: number) => setI((n) => (n + d + photos.length) % photos.length)
  useEffect(() => {
    const dialog = box.current
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog?.showModal()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') go(1)
      if (e.key === 'ArrowLeft') go(-1)
    }
    document.addEventListener('keydown', onKey)
    const unstack = sheetOpened(() => close.current())
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      unstack()
      document.body.style.overflow = prev
      dialog?.close()
      opener?.focus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const touch = useRef<number | null>(null)
  const chip = 'absolute grid h-11 w-11 place-items-center rounded-full bg-[var(--gallery-chip)] text-[var(--on-gallery)]'
  return (
    <dialog
      ref={box}
      aria-roledescription={t('carousel')}
      aria-label={t('Photos')}
      // Escape closes it (the dialog's own cancel), as the close button does.
      onCancel={(e) => {
        e.preventDefault()
        close.current()
      }}
      className="gallery-dialog anim-fade fixed inset-0 m-0 h-full max-h-none w-full max-w-none bg-[var(--gallery-bg)] p-0 text-[var(--on-gallery)]"
      onTouchStart={(e) => (touch.current = e.touches.length === 1 ? e.touches[0].clientX : null)}
      onTouchEnd={(e) => {
        if (touch.current === null) return
        const dx = e.changedTouches[0].clientX - touch.current
        if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1)
      }}
    >
      <div
        role="group"
        aria-roledescription={t('slide')}
        aria-label={photos.length > 1 ? t('{n} of {total}', { n: i + 1, total: photos.length }) : alt(i)}
        className="flex h-full w-full items-center justify-center"
      >
        <img src={mediaUrl(photos[i])} alt={alt(i)} className="gallery-full max-h-full max-w-full object-contain" style={{ touchAction: 'pinch-zoom' }} />
      </div>
      <button type="button" autoFocus onClick={onClose} aria-label={t('Close')} className={`${chip} right-4`} style={{ top: 'calc(var(--safe-top) + 12px)' }}>
        <Icon name="close" size={18} strokeWidth={2.2} />
      </button>
      {photos.length > 1 && (
        <>
          <button type="button" onClick={() => go(-1)} aria-label={t('Previous photo')} className={`${chip} left-4 top-1/2 -translate-y-1/2`}>
            <Icon name="chevron-left" size={18} strokeWidth={2.2} />
          </button>
          <button type="button" onClick={() => go(1)} aria-label={t('Next photo')} className={`${chip} right-4 top-1/2 -translate-y-1/2`}>
            <Icon name="chevron-right" size={18} strokeWidth={2.2} />
          </button>
          <span
            className="tnum absolute left-1/2 -translate-x-1/2 rounded-full bg-[var(--gallery-chip)] px-3 py-1 text-label font-semibold text-[var(--on-gallery)]"
            style={{ bottom: 'calc(env(safe-area-inset-bottom, 0px) + 24px)' }}
            aria-live="polite"
          >
            {i + 1} / {photos.length}
          </span>
        </>
      )}
    </dialog>
  )
}
