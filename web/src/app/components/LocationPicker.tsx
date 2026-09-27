import { useEffect, useRef, useState } from 'react'
import type { City as CityStat } from '../../data/repo.ts'
import { Icon } from './Icon.tsx'
import { Sheet } from './ui.tsx'
import { locale, plural, t } from '../../i18n.ts'

/** "Deutschland" or "Germany", from the platform's own country names. */
const country = (cc: string) => new Intl.DisplayNames([locale()], { type: 'region' }).of(cc) ?? cc

/**
 * Where you are searching from.
 *
 * This was a native <select> laid invisibly over a label. It worked, and it
 * opened the operating system's menu: a grey macOS list with a blue highlight,
 * eight bare city names, and nothing to say which of them has anything in it. A
 * buyer choosing a city is choosing a catchment, so the picker says what is in
 * each one and groups them the way people think about them, by country.
 *
 * A popover under the trigger on a page, a sheet from the bottom on a phone.
 */
export function LocationPicker({
  label,
  current,
  cities,
  onPick,
  districts = [],
  onPickDistrict,
  onPlate = false,
}: {
  /** On the lit plate (Explore's band): a glass capsule in the plate's ink. */
  onPlate?: boolean
  /** What the trigger reads, "Kreuzberg, Berlin". */
  label: string
  /** The metro currently searched. */
  current: string
  cities: CityStat[]
  onPick: (metro: string) => void
  /** Districts, so typing "Kreuz" finds Kreuzberg as well as cities. */
  districts?: { name: string; city: string }[]
  onPickDistrict?: (district: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const wide = useWide()
  const root = useRef<HTMLDivElement>(null)

  // A popover closes on an outside click and on Escape, like every other one.
  useEffect(() => {
    if (!open || !wide) return
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, wide])

  const pick = (metro: string) => {
    onPick(metro)
    setOpen(false)
    setQ('')
  }

  const needle = q.trim().toLowerCase()
  const shown = cities.filter(
    (c) =>
      !needle ||
      c.city.toLowerCase().includes(needle) ||
      country(c.country).toLowerCase().includes(needle),
  )
  const districtHits = needle
    ? districts.filter((d) => d.name.toLowerCase().includes(needle) && d.name !== d.city).slice(0, 8)
    : []
  const byCountry = shown.reduce<Record<string, CityStat[]>>((acc, c) => {
    ;(acc[c.country] ??= []).push(c)
    return acc
  }, {})

  // The field is focused the moment the popover opens, so it must not wear the
  // app's crimson focus ring: on an empty field that reads as an error.
  const list = (
    <div>
      <label className="relative block">
        <Icon
          name="search"
          size={15}
          strokeWidth={2}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-4)]"
        />
        <input
          autoFocus={wide}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('City, district or country')}
          aria-label={t('Filter cities and districts')}
          className="h-10 w-full rounded-[var(--radius-m)] border border-[var(--line)] bg-[var(--surface)] pl-9 pr-3
            text-body outline-none placeholder:text-[var(--ink-4)] focus:border-[var(--ink-3)]
            focus-visible:outline-none"
        />
      </label>

      {districtHits.length > 0 && onPickDistrict && (
        <div className="mt-4">
          <p className="t-label px-1">{t('Districts')}</p>
          <ul className="mt-1.5">
            {districtHits.map((d) => (
              <li key={d.name}>
                <button
                  onClick={() => {
                    onPickDistrict(d.name)
                    setOpen(false)
                    setQ('')
                  }}
                  className="flex w-full items-center gap-3 rounded-[var(--radius-m)] px-3 py-2.5 text-left transition-colors duration-[var(--dur-short)] hover:bg-[var(--sunken)]"
                >
                  <Icon name="pin" size={16} strokeWidth={1.8} className="shrink-0 text-[var(--ink-4)]" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-body font-semibold">{d.name}</span>
                    <span className="t-sm block text-[var(--ink-4)]">{d.city}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {shown.length === 0 && districtHits.length === 0 && (
        <p className="t-sm px-1 py-6 text-center text-[var(--ink-4)]">
          {t('Nothing listed there yet.')}
        </p>
      )}

      {Object.entries(byCountry).map(([cc, group]) => (
        <div key={cc} className="mt-4">
          <p className="t-label px-1">{country(cc)}</p>
          <ul className="mt-1.5">
            {group.map((c) => {
              const here = c.city === current
              return (
                <li key={c.city}>
                  <button
                    onClick={() => pick(c.city)}
                    aria-current={here ? 'true' : undefined}
                    className={`flex w-full items-center gap-3 rounded-[var(--radius-m)] px-3 py-2.5 text-left
                      transition-colors duration-[var(--dur-short)] ${
                        here ? 'bg-[var(--sunken)]' : 'hover:bg-[var(--sunken)]'
                      }`}
                  >
                    <Icon name="pin" size={16} strokeWidth={1.8} className="shrink-0 text-[var(--ink-4)]" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-body font-semibold">{c.city}</span>
                      <span className="t-sm tnum block text-[var(--ink-4)]">
                        {plural(c.listings, '{n} listing', '{n} listings')}
                      </span>
                    </span>
                    {here && (
                      <Icon name="check" size={16} strokeWidth={2.4} className="shrink-0 text-[var(--accent-text)]" />
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )

  return (
    <div ref={root} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={`inline-flex min-h-[44px] max-w-full items-center gap-1.5 rounded-full px-3 text-label font-medium transition-colors duration-[var(--dur-short)] ${
          onPlate
            ? 'glass glass-dark text-[var(--on-field)]'
            : 'text-[var(--ink-2)] hover:bg-[var(--sunken)] hover:text-[var(--ink)]'
        }`}
      >
        <Icon name="pin" size={15} strokeWidth={1.9} className={onPlate ? '' : 'text-[var(--ink-3)]'} />
        <span className="min-w-0 truncate">{label}</span>
        <Icon
          name="chevron-down"
          size={14}
          strokeWidth={2.2}
          className={`${onPlate ? 'opacity-70' : 'text-[var(--ink-4)]'} transition-transform duration-[var(--dur-short)] ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {wide ? (
        open && (
          <div
            role="dialog"
            aria-label={t('Choose a city')}
            className="anim-pop glass-strong absolute right-0 top-[calc(100%+8px)] z-50 max-h-[70vh] w-[320px]
              overflow-y-auto rounded-[var(--radius-l)] p-3 shadow-[var(--glass-shadow-raised)]"
          >
            {list}
          </div>
        )
      ) : (
        <Sheet open={open} onClose={() => setOpen(false)} title={t('Search near')}>
          <div className="pb-4">{list}</div>
        </Sheet>
      )}
    </div>
  )
}

function useWide() {
  const q = '(min-width: 768px)'
  const [wide, setWide] = useState(() => typeof window !== 'undefined' && matchMedia(q).matches)
  useEffect(() => {
    const m = matchMedia(q)
    const on = () => setWide(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return wide
}
