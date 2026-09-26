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

      {/* Wide: a mosaic, the first photo large. */}
      <div className={`hidden gap-2 md:grid ${photos.length > 1 ? 'md:grid-cols-[2fr_1fr_1fr] md:grid-rows-2' : 'md:grid-cols-1'}`}>
        {photos.slice(0, 5).map((src, i) => (
          <button
            key={src + i}
            type="button"
            onClick={() => setOpen(i)}
            aria-label={t('Open {what}', { what: alt(i) })}
            className={`press-soft block w-full overflow-hidden ${i === 0 ? 'md:row-span-2 rounded-l-[var(--sheet-radius)]' : ''} ${
              photos.length === 1 ? 'rounded-[var(--sheet-radius)]' : ''
            } ${i === 2 ? 'rounded-tr-[var(--sheet-radius)]' : ''} ${i === 4 || (i === 2 && photos.length === 3) ? 'rounded-br-[var(--sheet-radius)]' : ''}`}
          >
            <Photo
              src={src}
              meta={meta?.[i]}
              alt={alt(i)}
              categoryId={categoryId}
              aspect={i === 0 ? (photos.length > 1 ? 4 / 3 : 16 / 10) : 4 / 3}
              priority={i === 0}
              width={i === 0 ? 1100 : 400}
              sizes={i === 0 ? '(min-width: 768px) 60vw, 100vw' : '20vw'}
              className="h-full w-full"
            />
          </button>
        ))}
        {photos.length > 5 && (
          <button type="button" onClick={() => setOpen(0)} className="glass glass-strong absolute bottom-4 right-4 rounded-[var(--radius-s)] px-3.5 py-2 text-label font-semibold">
            {t('Show all {n} photos', { n: photos.length })}
          </button>
        )}
      </div>
      {overlay}
      {open !== null && <Viewer photos={photos} alt={alt} start={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

/** Full screen, one photo at a time, pinch-zoomable; arrows, swipe or keys. */
function Viewer({ photos, alt, start, onClose }: { photos: string[]; alt: (i: number) => string; start: number; onClose: () => void }) {
  const [i, setI] = useState(start)
  const close = useRef(onClose)
  close.current = onClose
  const go = (d: number) => setI((n) => (n + d + photos.length) % photos.length)
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close.current()
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
      opener?.focus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const touch = useRef<number | null>(null)
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={alt(i)}
      className="anim-fade fixed inset-0 z-[70] flex items-center justify-center bg-[var(--inverse)]"
      onTouchStart={(e) => (touch.current = e.touches.length === 1 ? e.touches[0].clientX : null)}
      onTouchEnd={(e) => {
        if (touch.current === null) return
        const dx = e.changedTouches[0].clientX - touch.current
        if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1)
      }}
    >
      <img
        src={mediaUrl(photos[i])}
        alt={alt(i)}
        className="max-h-full max-w-full object-contain"
        style={{ touchAction: 'pinch-zoom' }}
      />
      <button
        type="button"
        autoFocus
        onClick={onClose}
        aria-label={t('Close')}
        className="glass glass-dark absolute right-4 grid h-11 w-11 place-items-center rounded-full"
        style={{ top: 'calc(var(--safe-top) + 12px)' }}
      >
        <Icon name="close" size={18} strokeWidth={2.2} />
      </button>
      {photos.length > 1 && (
        <>
          <button type="button" onClick={() => go(-1)} aria-label={t('Previous photo')} className="glass glass-dark absolute left-4 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full">
            <Icon name="chevron-left" size={18} strokeWidth={2.2} />
          </button>
          <button type="button" onClick={() => go(1)} aria-label={t('Next photo')} className="glass glass-dark absolute right-4 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full">
            <Icon name="chevron-right" size={18} strokeWidth={2.2} />
          </button>
          <span className="glass glass-dark tnum absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-label font-semibold" aria-live="polite">
            {i + 1} / {photos.length}
          </span>
        </>
      )}
    </div>
  )
}
