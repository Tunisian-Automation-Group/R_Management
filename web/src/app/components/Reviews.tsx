import { useState } from 'react'
import type { Review } from '../../domain/types.ts'
import { summarise, type ReviewSummary } from '../../domain/reviews.ts'
import { ReportButton } from './Report.tsx'
import { Avatar, Button } from './ui.tsx'
import { Icon } from './Icon.tsx'
import { ago } from '../format.ts'
import { plural, t } from '../../i18n.ts'
import { oneDecimal } from './ui.tsx'

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
  summary,
  ownerFirstName,
  ownerJobs = 0,
}: {
  reviews: Review[]
  /** The server's summary over every review, when the list is only a page. */
  summary?: ReviewSummary
  ownerFirstName: string
  /** Bookings the owner has done on any listing: "new here" only when none. */
  ownerJobs?: number
}) {
  const [all, setAll] = useState(false)
  // With every review in hand, count from them, so the tag totals always match
  // the reviews shown underneath. The server's summary covers a partial page.
  const s = summary && reviews.length < summary.count ? summary : summarise(reviews)

  if (s.count === 0) {
    return (
      <div className="rounded-[var(--radius-card)] border border-dashed border-[var(--line-strong)] p-5">
        <p className="text-body font-semibold">{t('No reviews of this listing yet')}</p>
        <p className="t-sm mt-1 text-[var(--ink-3)]">
          {ownerJobs > 0
            ? t(
                ownerJobs === 1
                  ? '{name} has {n} booking behind them on other listings. Whoever books this one first writes its first review.'
                  : '{name} has {n} bookings behind them on other listings. Whoever books this one first writes its first review.',
                { name: ownerFirstName, n: ownerJobs },
              )
            : t('{name} is new here. Whoever books first gets to write the first one.', { name: ownerFirstName })}
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
            <span className="t-figure text-headline leading-none">{oneDecimal(s.average!)}</span>
            <StarRow value={s.average!} size={15} />
          </p>
          <p className="t-sm tnum mt-1.5 text-[var(--ink-3)]">
            {plural(s.count, '{n} review', '{n} reviews')}
            {s.onTimeShare != null && ` · ${t('{pct}% ready on time', { pct: Math.round(s.onTimeShare * 100) })}`}
          </p>
        </div>
        {s.topTags.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label={t('Mentioned most')}>
            {s.topTags.map((tag) => (
              <li
                key={tag.tag}
                className="tnum rounded-full bg-[var(--surface)] px-3 py-1.5 text-label font-medium text-[var(--ink-2)]"
              >
                {t(tag.tag)} <span className="text-[var(--ink-4)]">{tag.n}</span>
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
                <p className="text-body font-semibold">{r.author}</p>
                <p className="t-sm text-[var(--ink-4)]">{ago(r.at)}</p>
              </div>
              <span className="flex items-center gap-2">
                <StarRow value={r.rating} />
                <span className="sr-only">{t('{n} out of 5', { n: r.rating })}</span>
              </span>
              <ReportButton targetType="review" targetId={r.id} compact />
            </div>
            {r.text && <p className="t-body mt-3 max-w-[64ch] text-[var(--ink-2)]">{r.text}</p>}
            {(r.tags.length > 0 || !r.onTime) && (
              <p className="t-sm mt-2.5 text-[var(--ink-4)]">
                {[...r.tags, ...(r.onTime ? [] : ['Ran late'])].map((tag) => t(tag)).join(' · ')}
              </p>
            )}
          </li>
        ))}
      </ul>

      {reviews.length > 3 && !all && (
        <Button variant="secondary" onClick={() => setAll(true)}>
          {t('Show all {n} reviews', { n: reviews.length })}
        </Button>
      )}
      {/* EU consumer law (Omnibus): say how reviews are checked. */}
      <p className="t-sm mt-4 text-[var(--ink-4)]">
        {t('Reviews come only from completed bookings on Cappy, written by the person who booked. We do not edit them or pay for them.')}
      </p>
    </div>
  )
}
