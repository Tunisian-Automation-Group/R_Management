import type { CSSProperties, ReactNode } from 'react'
import type { CategoryId, Iso, Slot } from '../../domain/types.ts'
import { category } from '../../domain/categories.ts'

const DAY = 86_400_000

type Props = {
  slots: Slot[]
  categoryId: CategoryId
  /** The window being bought or sold. Its day is inked in the week strip. */
  highlight?: { start: Iso; end: Iso } | null
  /** Width divided by height. */
  aspect?: number
  /** 'thumb' drops the strip and the caption, for a 56px square in a row.
   *  'hero' keeps everything but the category label, because a screen using the
   *  plate as its cover names the category in its own chrome, and the label sits
   *  exactly where a floating back button lands. */
  detail?: 'full' | 'thumb' | 'hero'
  /**
   * Which number the plate leads with. A results list is ranked by fit, so the
   * start times differ down the page and 'time' reads well. The spotlight rail
   * is ranked by soonest, so every item there shares one start time and only
   * 'hours' tells them apart.
   */
  figure?: 'time' | 'hours'
  className?: string
  style?: CSSProperties
  /** Anything laid over the plate. */
  children?: ReactNode
}

const HH = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })

/**
 * A listing has no photograph, and a stock photo of someone else's machine
 * would be a lie. It has something better: the next hour you can
 * actually have. So the plate is a departure board. Aegean field, the opening
 * time set large in ice, the day underneath, and the week along the bottom.
 *
 * The information is the picture. A faint outline of a machine on a
 * pale rectangle was decoration standing in for one, which is why it read as an
 * image that had failed to load.
 */
export function Plate({
  slots,
  categoryId,
  highlight = null,
  aspect = 4 / 3,
  detail = 'full',
  figure = 'time',
  className = '',
  style,
  children,
}: Props) {
  const meta = category(categoryId)
  const thumb = detail === 'thumb'
  const labelled = detail === 'full'

  const day0 = new Date()
  day0.setHours(0, 0, 0, 0)
  const now = Date.now()

  let total = 0
  const week = Array.from({ length: 7 }, (_, i) => {
    const from = day0.getTime() + i * DAY
    const to = from + DAY
    const overlap = (a: number, b: number) =>
      Math.max(0, Math.min(b, to) - Math.max(a, from)) / 3_600_000
    const free = slots.reduce((n, s) => n + overlap(Date.parse(s.start), Date.parse(s.end)), 0)
    total += free
    const taken = highlight
      ? overlap(Date.parse(highlight.start), Date.parse(highlight.end)) > 0
      : false
    // Initial plus date, the way a wall planner labels a column. Shown only when
    // the plate is wide enough to be read as a timetable rather than an index.
    const d = new Date(from)
    const label = `${d.toLocaleDateString('en-GB', { weekday: 'narrow' })}${d.getDate()}`
    return { free, taken, label }
  })
  const peak = Math.max(1, ...week.map((d) => d.free))

  // What the plate announces: the window on offer, or the next one open.
  const next =
    (highlight ? Date.parse(highlight.start) : null) ??
    slots
      .map((s) => Date.parse(s.end) > now ? Math.max(Date.parse(s.start), now) : null)
      .filter((t): t is number => t !== null)
      .sort((a, b) => a - b)[0]

  const openNow = next !== undefined && next <= now + 60_000
  const when = next === undefined ? null : new Date(next)

  // How long it stays free from that moment: the end of the window it sits in.
  const holding = slots
    .map((sl) => ({ a: Date.parse(sl.start), b: Date.parse(sl.end) }))
    .find((sl) => next !== undefined && next >= sl.a - 60_000 && next < sl.b)
  const hoursFree = holding && next !== undefined ? (holding.b - next) / 3_600_000 : 0
  const lead =
    figure === 'hours' && hoursFree >= 1
      ? `${Math.round(hoursFree)}h`
      : when
        ? HH.format(when)
        : null
  const dayWord =
    when === null
      ? null
      : openNow
        ? 'free now'
        : when.toDateString() === new Date().toDateString()
          ? 'today'
          : when.getTime() - day0.getTime() < 2 * DAY
            ? 'tomorrow'
            : when.toLocaleDateString('en-GB', { weekday: 'long' }).toLowerCase()

  return (
    <div
      className={`plate relative isolate overflow-hidden bg-[var(--field)] ${className}`}
      style={{ aspectRatio: String(aspect), ...style }}
      role="img"
      aria-label={
        when
          ? `${meta.label}. Next free ${dayWord} at ${HH.format(when)}. ${Math.round(total)} idle hours this week.`
          : `${meta.label}. Nothing free this week.`
      }
    >
      {/* The field lifts towards the top left, the way a printed ink panel
          catches light, and carries the same lit rim as every glass surface in
          the app so a plate and the dock read as one material family. */}
      <span
        aria-hidden="true"
        className="absolute inset-0 bg-[radial-gradient(120%_90%_at_18%_0%,rgba(255,255,255,0.13),transparent_62%)]"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 rounded-[inherit]"
        style={{
          boxShadow:
            'inset 0 1px 0 rgba(255,255,255,0.16), inset 0 0 0 1px rgba(255,255,255,0.06)',
        }}
      />

      {when ? (
        <div className={`plate-body relative flex h-full flex-col ${thumb ? 'p-2' : 'p-5'}`}>
          <p className={`t-label ${labelled ? '' : 'hidden'}`} style={{ color: 'var(--on-field-dim)' }}>
            {meta.label}
          </p>

          {/* A plate grows its information, not its type.
              Bodoni past about 130px stops being a number: the hairlines thin to
              nothing and the stems read as bare bars, so "11h" became three
              rectangles in an acre of green. The figure is therefore capped, and
              the space a wide plate opens up is given to the week below instead,
              which is the part a buyer actually wants at that size. */}
          <p className="plate-figure mt-auto min-w-0">
            <span
              className="t-plate block"
              style={{
                color: openNow ? 'var(--sky)' : 'var(--on-field)',
                fontSize: thumb
                  ? 15
                  : `clamp(30px, min(${Math.round(104 / Math.max(lead?.length ?? 2, 1))}cqw, 30cqh), 128px)`,
                lineHeight: 0.82,
              }}
            >
              {lead}
            </span>
            {!thumb && (
              <span
                className="plate-caption mt-2 block text-[12px] font-medium tracking-[0.04em]"
                style={{ color: openNow ? 'var(--sky)' : 'var(--on-field-dim)' }}
              >
                {figure === 'hours' && hoursFree >= 1
                  ? openNow
                    ? 'free now'
                    : `from ${HH.format(when)} ${dayWord}`
                  : dayWord}
              </span>
            )}
          </p>

          {/* On a card this is a seven-tick index along the bottom edge: enough
              to say "free around Thursday" at a glance. Past 460px of plate it
              becomes the timetable it was always an abbreviation of, with the
              days named and each bar's height set by the hours actually free.
              Same seven numbers, drawn at a size where they can be read. */}
          {!thumb && (
            <span aria-hidden="true" className="plate-week">
              {week.map((d, i) => (
                <span key={i} className="plate-day">
                  <i
                    style={{
                      background: d.taken
                        ? 'var(--accent-bright)'
                        : d.free > 0
                          ? 'var(--sky)'
                          : 'rgba(244,243,238,0.14)',
                      opacity: d.free > 0 && !d.taken ? 0.4 + 0.6 * (d.free / peak) : 1,
                      ['--h' as string]: `${Math.max(4, Math.round((d.free / peak) * 100))}%`,
                    }}
                  />
                  <b>{d.label}</b>
                </span>
              ))}
            </span>
          )}
        </div>
      ) : (
        <div className={`relative flex h-full items-end ${thumb ? 'p-2' : 'p-4'}`}>
          <p className="text-[13px] font-medium" style={{ color: 'var(--on-field-dim)' }}>
            {thumb ? '' : 'Nothing free this week'}
          </p>
        </div>
      )}

      {children}
    </div>
  )
}

/** Kept so callers that still say `Cover` keep working. */
export const Cover = Plate

/**
 * A window that is open right now, said once. Crimson dot rather than a badge,
 * because a pill floating on the plate is chrome the plate does not need.
 */
export function WhenBadge({
  freeNow,
  text,
  className = '',
}: {
  freeNow: boolean
  text: string
  className?: string
}) {
  if (!freeNow) return null
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[12px] font-semibold text-[var(--accent-text)] ${className}`}
    >
      <span className="relative grid h-[7px] w-[7px] shrink-0 place-items-center">
        <span className="pulse-ring absolute inset-0 rounded-full bg-[var(--accent)]" />
        <span className="relative h-[7px] w-[7px] rounded-full bg-[var(--accent)]" />
      </span>
      {text}
    </span>
  )
}
