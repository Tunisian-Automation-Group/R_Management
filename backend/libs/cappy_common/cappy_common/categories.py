"""Port of ``src/domain/categories.ts``: the nine categories and their three groups.

Lives in the shared library rather than in the matching service because the
catalog needs it too, to refuse a "window" listing filed under "fabrication".
"""

from __future__ import annotations

from .jsmath import js_round, plus_to_fixed
from .models import BookingMode, CamelModel, CategoryGroup, CategoryId


class CategoryMeta(CamelModel):
    id: CategoryId
    label: str
    group: CategoryGroup
    mode: BookingMode
    # Icon key resolved in the app layer.
    icon: str
    # Second line on the browse row. Concrete, not a slogan.
    blurb: str
    # Window categories: the durations people actually book.
    quick_hours: list[float] | None = None
    # Batch categories: the unit a buyer counts in.
    unit_noun: str | None = None


class GroupMeta(CamelModel):
    id: CategoryGroup
    label: str
    # What this part of the chain is for, in the buyer's words.
    blurb: str


GROUPS: list[GroupMeta] = [
    GroupMeta(id="make", label="Make", blurb="Turn a drawing, a file or a spec into parts"),
    GroupMeta(id="move", label="Move", blurb="Get it across Europe, and hold it on the way"),
    GroupMeta(id="equip", label="Equip", blurb="Borrow the machine instead of buying it"),
]


def _c(**kw) -> CategoryMeta:
    return CategoryMeta(**kw)


CATEGORIES: list[CategoryMeta] = [
    # ------------------------------------------------------------------- make
    _c(
        id="fabrication",
        label="Fabrication",
        group="make",
        mode="batch",
        icon="mill",
        blurb="Milling, turning, laser, sheet metal and moulding",
        unit_noun="parts",
    ),
    _c(
        id="additive",
        label="3D printing",
        group="make",
        mode="batch",
        icon="printer",
        blurb="FDM, resin and SLS, from one prototype to a short run",
        unit_noun="parts",
    ),
    _c(
        id="finishing",
        label="Finishing",
        group="make",
        mode="batch",
        icon="spray",
        blurb="Anodising, powder coating, plating and heat treatment",
        unit_noun="parts",
    ),
    _c(
        id="print",
        label="Print & signage",
        group="make",
        mode="batch",
        icon="press",
        blurb="Large format, garments, labels and engraving",
        unit_noun="pieces",
    ),
    # ------------------------------------------------------------------- move
    _c(
        id="freight",
        label="Freight",
        group="move",
        mode="batch",
        icon="truck",
        blurb="Van, pallet and groupage space on runs already going",
        unit_noun="pallets",
    ),
    _c(
        id="warehousing",
        label="Warehousing",
        group="move",
        mode="window",
        icon="pallet",
        blurb="Pallet, cold and bonded space by the day",
        quick_hours=[24, 168, 720],
    ),
    # ------------------------------------------------------------------ equip
    _c(
        id="workshop",
        label="Workshop & tools",
        group="equip",
        mode="window",
        icon="drill",
        blurb="Benches, saws, welders and extraction",
        quick_hours=[2, 4, 8],
    ),
    _c(
        id="events",
        label="Event & AV",
        group="equip",
        mode="window",
        icon="speaker",
        blurb="PA, lighting and stage rigs between gigs",
        quick_hours=[8, 24, 48],
    ),
    _c(
        id="creator",
        label="Creator kit",
        group="equip",
        mode="window",
        icon="camera",
        blurb="Bodies, glass, studios and treated rooms",
        quick_hours=[8, 24, 72],
    ),
]

_BY_ID = {c.id: c for c in CATEGORIES}
GROUP_IDS: tuple[str, ...] = tuple(g.id for g in GROUPS)


def category(id: str) -> CategoryMeta:
    found = _BY_ID.get(id)
    if not found:
        raise KeyError(f"unknown category: {id}")
    return found


def categories_in(group: str) -> list[CategoryMeta]:
    return [c for c in CATEGORIES if c.group == group]


def mode_of(category_id: str) -> BookingMode | None:
    """The booking mode a category is sold in, or None for an unknown category."""
    found = _BY_ID.get(category_id)
    return found.mode if found else None


def duration_label(hours: float) -> str:
    """Hours phrased the way people say them, not as a raw number."""
    if hours < 1:
        return f"{js_round(hours * 60)} min"
    if hours < 24:
        return f"{plus_to_fixed(hours, 1)} {'hour' if hours == 1 else 'hours'}"
    days = hours / 24
    if days < 7:
        return f"{plus_to_fixed(days, 1 if days % 1 else 0)} {'day' if days == 1 else 'days'}"
    weeks = days / 7
    return f"{plus_to_fixed(weeks, 1 if weeks % 1 else 0)} {'week' if weeks == 1 else 'weeks'}"
