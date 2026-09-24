from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request, Response, UploadFile, status
from fastapi.responses import FileResponse

from cappy_common.app import ApiRouter
from cappy_common.categories import mode_of
from cappy_common.errors import Conflict, Forbidden, Invalid
from cappy_common.events import CATALOG_CHANGED
from cappy_common.models import (
    CamelModel,
    District,
    Listing,
    Outcome,
    Owner,
    Review,
    Slot,
    World,
)
from cappy_common.timeutil import HOUR_MS, ms_from_iso

from . import media
from .repository import CatalogRepository

router = ApiRouter()

# A listing carries the owner's own photographs, by URL: ours (``/media/…``,
# from ``POST /uploads``) or anyone's over http(s). The database never holds
# image bytes.
MAX_PHOTOS = 12


def _photo_url_ok(url: str) -> bool:
    return url.startswith(("https://", "http://")) or bool(media.NAME.match(url.removeprefix("/media/")))


async def get_repo(request: Request) -> AsyncIterator[CatalogRepository]:
    async with request.app.state.db.session() as session:
        async with session.begin():
            yield CatalogRepository(session)


def current_user(request: Request) -> str:
    return request.app.state.current_user(request.headers.get("x-cappy-user"))


async def _changed(request: Request, what: str, **payload) -> None:
    await request.app.state.bus.publish(CATALOG_CHANGED, {"what": what, **payload})


class ListingWithSlots(CamelModel):
    listing: Listing
    slots: list[Slot]


class Me(CamelModel):
    """Who the client is speaking for, and where their searches start. A mobile
    app has no seed to read these from, so the server says."""

    id: str
    home_district: str
    owner: Owner | None = None


class WorldVersion(CamelModel):
    """Which edition of the seed the world was built from. Changes when the
    world is rebuilt; other services compare it with what they last saw."""

    version: str


@router.get("/world", response_model=World)
async def world(repo: CatalogRepository = Depends(get_repo)) -> World:
    return await repo.world()


@router.get("/world/version", response_model=WorldVersion)
async def world_version(repo: CatalogRepository = Depends(get_repo)) -> WorldVersion:
    from .seed import loaded_version

    return WorldVersion(version=await loaded_version(repo) or "unseeded")


@router.get("/me", response_model=Me)
async def me(
    request: Request, repo: CatalogRepository = Depends(get_repo), user: str = Depends(current_user)
) -> Me:
    owner = await repo.find_owner(user)
    home = owner.district if owner else request.app.state.settings.home_district
    return Me(id=user, home_district=home, owner=owner)


@router.get("/districts", response_model=dict[str, District])
async def districts(repo: CatalogRepository = Depends(get_repo)) -> dict[str, District]:
    return await repo.districts()


@router.get("/owners", response_model=list[Owner])
async def owners(repo: CatalogRepository = Depends(get_repo)) -> list[Owner]:
    return await repo.owners()


@router.get("/owners/{owner_id}", response_model=Owner)
async def owner(owner_id: str, repo: CatalogRepository = Depends(get_repo)) -> Owner:
    return await repo.owner(owner_id)


@router.post("/owners/{owner_id}/outcomes", response_model=Owner)
async def record_outcome(
    owner_id: str,
    outcome: Outcome,
    request: Request,
    repo: CatalogRepository = Depends(get_repo),
) -> Owner:
    """Fold a rated booking into the owner's record. The booking service's
    ``booking.rated`` event lands here too (and also writes the review); the
    endpoint exists for a synchronous fallback and for operators."""
    updated = await repo.apply_outcome(owner_id, outcome)
    await _changed(request, "owner", id=owner_id)
    return updated


@router.get("/listings", response_model=list[Listing])
async def listings(owner_id: str | None = None, repo: CatalogRepository = Depends(get_repo)) -> list:
    return await repo.listings(owner_id)


@router.get("/listings/{listing_id}", response_model=Listing)
async def listing(listing_id: str, repo: CatalogRepository = Depends(get_repo)):
    return await repo.listing(listing_id)


@router.get("/listings/{listing_id}/slots", response_model=list[Slot])
async def listing_slots(listing_id: str, repo: CatalogRepository = Depends(get_repo)) -> list[Slot]:
    await repo.listing(listing_id)
    return await repo.slots(listing_id)


@router.get("/listings/{listing_id}/reviews", response_model=list[Review])
async def listing_reviews(listing_id: str, repo: CatalogRepository = Depends(get_repo)) -> list[Review]:
    """Newest first. The matching service adds the summary at
    ``/listings/{id}/reviews/summary``."""
    await repo.listing(listing_id)
    return await repo.reviews(listing_id)


@router.get("/reviews", response_model=list[Review])
async def all_reviews(repo: CatalogRepository = Depends(get_repo)) -> list[Review]:
    return await repo.reviews()


@router.post("/listings", response_model=ListingWithSlots, status_code=status.HTTP_201_CREATED)
async def create_listing(
    body: ListingWithSlots,
    request: Request,
    repo: CatalogRepository = Depends(get_repo),
    user: str = Depends(current_user),
) -> ListingWithSlots:
    l = body.listing
    if l.owner_id != user:
        raise Forbidden("a listing can only be created for the calling owner")
    await repo.owner(user)
    if l.district not in await repo.districts():
        raise Invalid(f"unknown district: {l.district}")
    if mode_of(l.category) != l.mode:
        raise Invalid(f"category {l.category} is booked by {mode_of(l.category)}, not {l.mode}")
    if await repo.has_listing(l.id):
        raise Conflict(f"listing {l.id} already exists")
    if l.rate_per_hour <= 0:
        raise Invalid("ratePerHour must be positive")
    if l.photos is not None:
        if len(l.photos) > MAX_PHOTOS:
            raise Invalid(f"at most {MAX_PHOTOS} photos per listing")
        for url in l.photos:
            if not _photo_url_ok(url):
                raise Invalid("photos must be URLs; upload the image first (POST /uploads) and send its address")

    seen: set[str] = set()
    for s in body.slots:
        if s.listing_id != l.id:
            raise Invalid(f"slot {s.id} belongs to another listing")
        if s.id in seen:
            raise Invalid(f"duplicate slot id {s.id}")
        seen.add(s.id)
        wall = (ms_from_iso(s.end) - ms_from_iso(s.start)) / HOUR_MS
        if wall <= 0:
            raise Invalid(f"slot {s.id} ends before it starts")
        if s.hours_usable > wall + 1e-9 or s.hours_usable <= 0:
            raise Invalid(f"slot {s.id} claims {s.hours_usable} usable hours in a {wall} hour window")

    await repo.add_listing(l, body.slots)
    await _changed(request, "listing", id=l.id)
    return body


@router.post("/listings/{listing_id}/pause", response_model=Listing)
async def pause(
    listing_id: str,
    request: Request,
    repo: CatalogRepository = Depends(get_repo),
    user: str = Depends(current_user),
):
    return await _set_active(listing_id, False, request, repo, user)


@router.post("/listings/{listing_id}/resume", response_model=Listing)
async def resume(
    listing_id: str,
    request: Request,
    repo: CatalogRepository = Depends(get_repo),
    user: str = Depends(current_user),
):
    return await _set_active(listing_id, True, request, repo, user)


async def _set_active(listing_id: str, active: bool, request: Request, repo: CatalogRepository, user: str):
    existing = await repo.listing(listing_id)
    if existing.owner_id != user:
        raise Forbidden("only the owner can pause or resume a listing")
    updated = await repo.set_active(listing_id, active)
    await _changed(request, "listing", id=listing_id)
    return updated


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    listing_id: str,
    request: Request,
    repo: CatalogRepository = Depends(get_repo),
    user: str = Depends(current_user),
) -> Response:
    existing = await repo.listing(listing_id)
    if existing.owner_id != user:
        raise Forbidden("only the owner can remove a listing")
    await repo.remove_listing(listing_id)
    await _changed(request, "listing", id=listing_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- photos ---------------------------------------------------------------------


class Uploaded(CamelModel):
    url: str
    content_type: str
    bytes: int


@router.post("/uploads", response_model=Uploaded, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, request: Request, user: str = Depends(current_user)) -> Uploaded:
    """One photograph in, its URL out. The app shrinks pictures before sending
    (a phone photo is 4 to 12 MB; nobody needs that on a card), so the limit
    here is a backstop, not a budget. The URL goes in ``Listing.photos``."""
    settings = request.app.state.settings
    # Read at most one byte over the limit, so a huge upload is refused without
    # being buffered whole.
    data = await file.read(settings.media_max_bytes + 1)
    name, ctype = media.store(settings.media_dir, data, settings.media_max_bytes)
    return Uploaded(url=f"{settings.media_public_base.rstrip('/')}/media/{name}", content_type=ctype, bytes=len(data))


@router.get("/media/{name}", include_in_schema=False)
async def serve_media(name: str, request: Request) -> FileResponse:
    """Names are content hashes, so a URL never changes meaning: cache forever."""
    path, ctype = media.locate(request.app.state.settings.media_dir, name)
    return FileResponse(path, media_type=ctype, headers={"Cache-Control": "public, max-age=31536000, immutable"})


# --- saved: the heart on every card ---------------------------------------------


@router.get("/saved", response_model=list[str])
async def saved(repo: CatalogRepository = Depends(get_repo), user: str = Depends(current_user)) -> list[str]:
    """Listing ids this person hearted, newest first. A shortlist, not a booking."""
    return await repo.saved(user)


@router.put("/saved/{listing_id}", response_model=list[str])
async def save(
    listing_id: str, repo: CatalogRepository = Depends(get_repo), user: str = Depends(current_user)
) -> list[str]:
    await repo.listing(listing_id)
    return await repo.save(user, listing_id)


@router.delete("/saved/{listing_id}", response_model=list[str])
async def unsave(
    listing_id: str, repo: CatalogRepository = Depends(get_repo), user: str = Depends(current_user)
) -> list[str]:
    return await repo.unsave(user, listing_id)


@router.post("/admin/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset(request: Request, repo: CatalogRepository = Depends(get_repo)) -> Response:
    """Demo only: put the seeded world back exactly as shipped."""
    from .seed import seed_world

    await seed_world(repo, request.app.state.settings.seed_timezone)
    await _changed(request, "reset")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
