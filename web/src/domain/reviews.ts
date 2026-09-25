import type { Review } from './types.ts'

/**
 * The things people say about a booking, as a fixed vocabulary. Picked rather
 * than typed, because a tag that twelve buyers chose is a fact about an owner
 * and twelve free-text sentences are not something anyone reads.
 */
export const REVIEW_TAGS = [
  'As described',
  'Ready on time',
  'Clear handover',
  'Quick replies',
  'Great quality',
  'Fair price',
] as const

export type ReviewSummary = {
  count: number
  /** Null until there is at least one, "new" is not the same as "bad". */
  average: number | null
  /** Share of reviews that said it was ready when promised. */
  onTimeShare: number | null
  /** The tags mentioned most, most first, with how many people chose them. */
  topTags: { tag: string; n: number }[]
}

export function summarise(reviews: Review[]): ReviewSummary {
  if (reviews.length === 0) return { count: 0, average: null, onTimeShare: null, topTags: [] }
  const counts = new Map<string, number>()
  for (const r of reviews) for (const t of r.tags) counts.set(t, (counts.get(t) ?? 0) + 1)
  return {
    count: reviews.length,
    average: reviews.reduce((n, r) => n + r.rating, 0) / reviews.length,
    onTimeShare: reviews.filter((r) => r.onTime).length / reviews.length,
    topTags: [...counts]
      .map(([tag, n]) => ({ tag, n }))
      .sort((a, b) => b.n - a.n)
      .slice(0, 3),
  }
}

/** Newest first. */
export const byRecent = (a: Review, b: Review) => Date.parse(b.at) - Date.parse(a.at)
