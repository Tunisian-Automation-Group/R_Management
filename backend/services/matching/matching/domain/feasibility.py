"""Port of ``src/domain/feasibility.ts``."""

from __future__ import annotations

from cappy_common.models import AnyListing, AnyRequirement, CamelModel, Dims


class Feasibility(CamelModel):
    feasible: bool
    # 1 while this is rules-based: a rule is certain. Kept in the shape so a
    # probabilistic judgment layer can replace the body without touching callers.
    confidence: float
    reasons: list[str]
    blockers: list[str]


def _num(v: float) -> str:
    """JS prints 120 as "120" and 12.5 as "12.5"; Python floats would say 120.0."""
    return str(int(v)) if float(v).is_integer() else str(v)


def _fits_inside(need: Dims, box: Dims) -> bool:
    """Fits allowing 90-degree rotation: sort both descending, compare pairwise."""
    n = sorted([need.x, need.y, need.z], reverse=True)
    b = sorted([box.x, box.y, box.z], reverse=True)
    return all(v <= b[i] for i, v in enumerate(n))


def assess_feasibility(req: AnyRequirement, listing: AnyListing) -> Feasibility:
    """Can this listing satisfy this request at all, ignoring time and distance?

    Every rule here is exactly computable from declared facts, which is why it is
    rules and not a model. The reasons it returns are shown to the buyer verbatim.
    """
    reasons: list[str] = []
    blockers: list[str] = []

    if not listing.active:
        blockers.append("listing is paused")
    if listing.category != req.category:
        blockers.append("different category")

    if req.mode == "window" and listing.mode == "window":
        if req.hours < listing.min_hours:
            blockers.append(f"minimum booking is {_num(listing.min_hours)} h")
        if req.hours > listing.max_hours:
            blockers.append(f"maximum booking is {_num(listing.max_hours)} h")
    elif req.mode == "batch" and listing.mode == "batch":
        if req.material:
            # A listing that does not describe materials at all cannot promise one.
            if listing.materials and req.material in listing.materials:
                reasons.append(f"{req.material} in stock")
            else:
                blockers.append(f"does not stock {req.material}")
        if req.dims:
            if _fits_inside(req.dims, listing.max_dims):
                d = req.dims
                reasons.append(f"{_num(d.x)}×{_num(d.y)}×{_num(d.z)} mm fits the envelope")
            else:
                blockers.append("part exceeds the build envelope")
        if req.tolerance_mm is not None:
            if listing.tolerance_mm is None:
                blockers.append("does not work to a tolerance")
            elif listing.tolerance_mm <= req.tolerance_mm:
                reasons.append(f"holds ±{_num(listing.tolerance_mm)} mm")
            else:
                blockers.append(f"only holds ±{_num(listing.tolerance_mm)} mm")
    else:
        blockers.append("different kind of booking")

    return Feasibility(feasible=not blockers, confidence=1, reasons=reasons, blockers=blockers)
