import type { Listing, Match, Owner, Slot } from '../../domain/types.ts'
import { isWindow, rating } from '../../domain/types.ts'
import { durationLabel } from '../../domain/categories.ts'
import { formatMoney } from '../../domain/money.ts'
import { Photo } from './Photo.tsx'
import { Stars, TapLink } from './ui.tsx'
import { formatDistance, range } from '../format.ts'
import { t } from '../../i18n.ts'

/**
 * A result row: the owner's photograph, then what it is, then what it costs.
 *
 * Rows stay ruled rather than boxed, because twenty of them should read as one
 * table rather than twenty floating objects. What changed is the leading column:
 * it was a plate printing the hour, which told you when before it told you what.
 */
export function ListingCard({
  listing,
  owner,
  match,
  slots,
  to,
  rank,
}: {
  listing: Listing
  owner: Owner
  match: Match
  slots?: Slot[]
  to: string
  rank?: number
}) {
  const stars = rating(owner)

  return (
    <TapLink
      to={to}
      className="group flex w-full items-stretch gap-4 py-5 text-left transition-opacity duration-[var(--dur-short)] hover:opacity-70"
    >
      <Photo
        src={listing.photos?.[0]}
        alt={listing.title}
        slots={slots}
        categoryId={listing.category}
        aspect={1}
        claim={listing.id}
        width={128}
        sizes="(min-width: 768px) 128px, 96px"
        className="w-[96px] shrink-0 rounded-[var(--radius-plate)] md:w-[128px]"
      />

      <span className="flex min-w-0 flex-1 flex-col justify-between py-0.5">
        <span className="min-w-0">
          <span className="flex items-baseline justify-between gap-3">
            <span className="t-h4 min-w-0 [overflow-wrap:anywhere]">{listing.title}</span>
            <span className="tnum shrink-0 text-body-l font-semibold">
              {formatMoney(match.quote.total, match.quote.currency)}
            </span>
          </span>
          <span className="t-sm mt-1 block [overflow-wrap:anywhere] text-[var(--ink-3)]">
            {owner.name}, {listing.district}
          </span>
        </span>

        <span className="mt-3 block">
          <span className="tnum block text-label font-medium text-[var(--ink)]">
            {range(match.start, match.end)}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="tnum text-label text-[var(--ink-4)]">
              {formatDistance(match.distanceKm)}
            </span>
            <span className="tnum text-label text-[var(--ink-4)]">
              {isWindow(listing)
                ? durationLabel(match.quote.hours)
                : t('{duration} incl. setup', { duration: durationLabel(match.quote.hours) })}
            </span>
            {/* The owner's record over all their jobs, not this listing's reviews: labelled so. */}
            <span className="inline-flex flex-wrap items-baseline gap-1" title={t("The owner's rating across all their jobs")}>
              <span className="text-label text-[var(--ink-4)]">{t('Host')}</span>
              <Stars value={stars} count={owner.jobsDone} />
            </span>
            {rank === 0 && (
              <span className="text-label font-semibold text-[var(--accent-text)]">
                {t('Best match')}
              </span>
            )}
          </span>
        </span>
      </span>
    </TapLink>
  )
}
