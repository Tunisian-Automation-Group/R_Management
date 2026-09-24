import type { Iso, Slot } from '../../domain/types.ts'

type Props = {
  slots: Slot[]
  /** The window being bought or sold, drawn solid. */
  booked?: { start: Iso; end: Iso } | null
  days?: number
  size?: 'sm' | 'md'
  /** 'buy' reads as "time you can take"; 'earn' as "time going to waste". */
  intent?: 'buy' | 'earn'
  showLegend?: boolean
  className?: string
}

const DAY_MS = 86_400_000

/**
 * A week of an asset's time, drawn to scale. Warm grey is time already spoken
 * for, powder blue is idle time nobody is paying for, crimson is a window
 * somebody has taken.
 *
 * Both sides of the market get the same drawing. A buyer reads it as a window
 * they can take and an owner reads it as one going to waste.
 */
export function CapacityBar({
  slots,
  booked,
  days = 7,
  size = 'md',
  intent = 'buy',
  showLegend = false,
  className = '',
}: Props) {
  const start = new Date()
  start.setHours(0, 0, 0, 0)

  const nowPct = ((Date.now() - start.getTime()) / DAY_MS) * 100
  // A listing row carries this as a strip, not a chart; 52px made it the loudest
  // thing in the card.
  const height = size === 'sm' ? 26 : 148

  const columns = Array.from({ length: days }, (_, i) => {
    const from = start.getTime() + i * DAY_MS
    const to = from + DAY_MS

    const band = (a: number, b: number) => {
      const lo = Math.max(a, from)
      const hi = Math.min(b, to)
      if (hi <= lo) return null
      return { top: ((lo - from) / DAY_MS) * 100, height: ((hi - lo) / DAY_MS) * 100 }
    }

    const idle = slots
      .map((s) => band(Date.parse(s.start), Date.parse(s.end)))
      .filter((b): b is { top: number; height: number } => b !== null)

    return {
      date: new Date(from),
      isToday: i === 0,
      idle,
      /** Share of the day that is free, what the compact variant plots. */
      idleShare: idle.reduce((n, b) => n + b.height, 0) / 100,
      sold: booked ? band(Date.parse(booked.start), Date.parse(booked.end)) : null,
    }
  })

  // At this height a true-to-scale five-hour window is a 9px sliver that reads
  // as an underline. The compact variant plots each day against the busiest one
  // so the shape can say "Tuesday is the free day".
  const peak = Math.max(0.0001, ...columns.map((c) => c.idleShare))

  return (
    <div className={className}>
      <div>
        <div className="flex gap-[5px]" style={{ height }}>
          {columns.map((col, i) => (
            <div
              key={i}
              className="relative flex-1 overflow-hidden rounded-[7px] bg-[var(--track)]"
            >
              {size === 'sm'
                ? col.idleShare > 0 && (
                    <div
                      className={`anim-grow absolute inset-x-0 bottom-0 rounded-[7px] ${
                        col.sold ? 'bg-[var(--sold)]' : 'bg-[var(--idle)]'
                      }`}
                      style={{
                        height: `${Math.max(16, (col.idleShare / peak) * 100)}%`,
                        animationDelay: `${i * 35}ms`,
                      }}
                    />
                  )
                : col.idle.map((b, j) => (
                    <div
                      key={j}
                      className="anim-fade absolute inset-x-0 rounded-[6px] bg-[var(--idle)]"
                      style={{ top: `${b.top}%`, height: `${b.height}%`, animationDelay: `${i * 35}ms` }}
                    />
                  ))}
              {size === 'md' && col.sold && (
                <div
                  className="absolute inset-x-0 rounded-[6px] bg-[var(--sold)] ring-2 ring-[var(--surface)]"
                  style={{ top: `${col.sold.top}%`, height: `${col.sold.height}%` }}
                />
              )}
              {/* Where we are in the day, which is why the early gaps have gone. */}
              {size === 'md' && col.isToday && nowPct > 0 && nowPct < 100 && (
                <div
                  className="absolute inset-x-0 h-[2.5px] rounded-full bg-[var(--ink)] opacity-70"
                  style={{ top: `${nowPct}%` }}
                />
              )}
            </div>
          ))}
        </div>

        <div className={`flex gap-[5px] ${size === 'sm' ? 'mt-2' : 'mt-2.5'}`}>
          {columns.map((col, i) => (
            <div
              key={i}
              className={`tnum flex-1 text-center tracking-[0.06em] ${size === 'sm' ? 'text-[10px] leading-[12px]' : 'text-[11px] leading-[14px]'} ${
                col.isToday ? 'font-bold text-[var(--ink)]' : 'font-semibold text-[var(--ink-4)]'
              }`}
            >
              {col.date.toLocaleDateString('en-GB', { weekday: 'narrow' })}
              {size === 'md' && <span className="ml-0.5 opacity-80">{col.date.getDate()}</span>}
            </div>
          ))}
        </div>
      </div>

      {showLegend && (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-[var(--line)] pt-3 text-[12.5px] text-[var(--ink-3)]">
          <Key className="bg-[var(--track)]" label="In use" />
          <Key className="bg-[var(--idle)]" label={intent === 'earn' ? 'Idle, nobody paying' : 'Free to book'} />
          {booked && <Key className="bg-[var(--sold)]" label={intent === 'earn' ? 'Sold' : 'Your booking'} />}
        </div>
      )}
    </div>
  )
}

function Key({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 rounded-[4px] ${className}`} />
      {label}
    </span>
  )
}
