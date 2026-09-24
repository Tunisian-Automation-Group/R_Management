import { useState } from 'react'
import type { Review } from '../../domain/types.ts'
import { summarise } from '../../domain/reviews.ts'
import { Avatar, Button } from './ui.tsx'
import { Icon } from './Icon.tsx'
import { ago } from '../format.ts'

/** Five stars, filled to the rating. Decorative; the number beside it is the fact. */
export function StarRow({ value, size = 13 }: { value: number; size?: number }) {
  return (
    <span className="inline-flex gap-[2px]" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((n) => (
        <Icon
          key={n}
          name="star"
          size={size}
          strokeWidth={1.4}
          className={n <= Math.round(value) ? 'fill-[var(--ink)] text-[var(--ink)]' : 'text-[var(--line-strong)]'}
        />
      ))}
    </span>
  )
}

/**
 * What previous buyers said, ahead of the rules and the fine print.
 *
 * The ranking already learns from outcomes; this is where a stranger reads them.
 * It leads with the three things a buyer is actually trying to find out: is it
 * good (the average), will it be ready (the on-time share), and what do people
 * keep mentioning (the tags, counted). The sentences come after, three at a time.
 */
export function Reviews({
  reviews,
  ownerFirstName,
}: {
  reviews: Review[]
  ownerFirstName: string
}) {
  const [all, setAll] = useState(false)
  const s = summarise(reviews)

  if (s.count === 0) {
    return (
      <div className="rounded-[var(--radius-card)] border border-dashed border-[var(--line-strong)] p-5">
        <p className="text-[15px] font-semibold">No reviews yet</p>
        <p className="t-sm mt-1 text-[var(--ink-3)]">
          {ownerFirstName} is new here. Whoever books first gets to write the first one.
        </p>
      </div>
    )
  }

  const shown = all ? reviews : reviews.slice(0, 3)

  return (
    <div>
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4 rounded-[var(--radius-card)] bg-[var(--sunken)] p-5">
        <div>
          <p className="tnum flex items-baseline gap-2">
            <span className="t-h1 leading-none">{s.average!.toFixed(1)}</span>
            <StarRow value={s.average!} size={15} />
          </p>
          <p className="t-sm tnum mt-1.5 text-[var(--ink-3)]">
            {s.count} {s.count === 1 ? 'review' : 'reviews'}
            {s.onTimeShare !== null && ` · ${Math.round(s.onTimeShare * 100)}% ready on time`}
          </p>
        </div>
        {s.topTags.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="Mentioned most">
            {s.topTags.map((t) => (
              <li
                key={t.tag}
                className="tnum rounded-full bg-[var(--surface)] px-3 py-1.5 text-[13px] font-medium text-[var(--ink-2)]"
              >
                {t.tag} <span className="text-[var(--ink-4)]">{t.n}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ul className="ruled mt-2">
        {shown.map((r) => (
          <li key={r.id} className="py-5">
            <div className="flex items-center gap-3">
              <Avatar initials={r.initials} size={34} />
              <div className="min-w-0 flex-1">
                <p className="text-[14.5px] font-semibold">{r.author}</p>
                <p className="t-sm text-[var(--ink-4)]">{ago(r.at)}</p>
              </div>
              <span className="flex items-center gap-2">
                <StarRow value={r.rating} />
                <span className="sr-only">{r.rating} out of 5</span>
              </span>
            </div>
            {r.text && <p className="t-body mt-3 max-w-[64ch] text-[var(--ink-2)]">{r.text}</p>}
            {(r.tags.length > 0 || !r.onTime) && (
              <p className="t-sm mt-2.5 text-[var(--ink-4)]">
                {[...r.tags, ...(r.onTime ? [] : ['Ran late'])].join(' · ')}
              </p>
            )}
          </li>
        ))}
      </ul>

      {reviews.length > 3 && !all && (
        <Button variant="secondary" onClick={() => setAll(true)}>
          Show all {reviews.length} reviews
        </Button>
      )}
    </div>
  )
}
