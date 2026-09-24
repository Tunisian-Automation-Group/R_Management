"""Port of ``src/domain/reviews.ts``. The vocabulary (``REVIEW_TAGS``) lives in
``cappy_common.models`` because the booking service validates against it."""

from __future__ import annotations

from cappy_common.models import REVIEW_TAGS, CamelModel, Review
from cappy_common.timeutil import ms_from_iso

__all__ = ["REVIEW_TAGS", "ReviewSummary", "TagCount", "by_recent", "summarise"]


class TagCount(CamelModel):
    tag: str
    n: int


class ReviewSummary(CamelModel):
    count: int
    # None until there is at least one: "new" is not the same as "bad".
    average: float | None
    # Share of reviews that said it was ready when promised.
    on_time_share: float | None
    # The tags mentioned most, most first, with how many people chose them.
    top_tags: list[TagCount]


def summarise(reviews: list[Review]) -> ReviewSummary:
    if not reviews:
        return ReviewSummary(count=0, average=None, on_time_share=None, top_tags=[])
    counts: dict[str, int] = {}
    for r in reviews:
        for t in r.tags:
            counts[t] = counts.get(t, 0) + 1
    # Ties keep first-seen order, which is what a JS stable sort over a Map does.
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    return ReviewSummary(
        count=len(reviews),
        average=sum(r.rating for r in reviews) / len(reviews),
        on_time_share=sum(1 for r in reviews if r.on_time) / len(reviews),
        top_tags=[TagCount(tag=t, n=n) for t, n in top],
    )


def by_recent(reviews: list[Review]) -> list[Review]:
    """Newest first."""
    return sorted(reviews, key=lambda r: -ms_from_iso(r.at))
