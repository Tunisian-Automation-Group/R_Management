"""The booking state machine, as data.

    awaiting_payment --authorised--> requested --accept--> accepted --start--> active --complete--> completed
          |                             |                     |   \                  |                (--rate)
          +--payment failed--> payment_failed               cancel  capture declined  dispute (buyer)
          +--expire--> expired          +--decline--> declined       -> payment_failed   -> disputed
                                        +--expire--> expired
    cancel: from awaiting_payment, requested or accepted, by either party, and only
            before the window starts. After that the buyer disputes instead.
    start:  from 30 minutes before the window, by either party.
    dispute: from accepted or active once the window has started, by the buyer. The
            payout is held until support resolves it (docs/runbook.md).

Transitions a person makes name who may make them. The rest are made by the
system: a payment result, the expiry sweep, the auto-completion sweep.

A booking *holds* its window while it is in ``HOLDING``: the exclusion
constraint (ADR 0004) forbids two holding bookings from overlapping on one
listing. Leaving ``HOLDING`` releases the window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cappy_common.errors import Conflict, Forbidden

Status = Literal[
    "awaiting_payment",
    "requested",
    "accepted",
    "active",
    "completed",
    "declined",
    "cancelled",
    "expired",
    "payment_failed",
    "disputed",
]
HOLDING: frozenset[str] = frozenset(
    # A completed or disputed booking used its window (a job can be finished
    # early): the time stays sold. Only bookings that never happened release it.
    {"awaiting_payment", "requested", "accepted", "active", "completed", "disputed"}
)
# Bookings still in flight: what must finish before an account can go.
OPEN: frozenset[str] = frozenset({"awaiting_payment", "requested", "accepted", "active", "disputed"})
FINAL: frozenset[str] = frozenset({"completed", "declined", "cancelled", "expired", "payment_failed"})

Action = Literal["accept", "decline", "start", "complete", "cancel", "dispute"]
SystemAction = Literal[
    "authorised", "authorised_instant", "payment_failed", "expire", "auto_complete", "listing_removed"
]
Role = Literal["requester", "owner", "either"]


@dataclass(frozen=True)
class Transition:
    from_states: frozenset[str]
    to_state: Status
    by: Role


TRANSITIONS: dict[Action, Transition] = {
    "accept": Transition(frozenset({"requested"}), "accepted", "owner"),
    "decline": Transition(frozenset({"requested"}), "declined", "owner"),
    # Either side can mark the handover: whoever is standing at the machine.
    "start": Transition(frozenset({"accepted"}), "active", "either"),
    # The buyer confirms the job is done; the sweep does it if they never do.
    "complete": Transition(frozenset({"active"}), "completed", "requester"),
    "cancel": Transition(frozenset({"awaiting_payment", "requested", "accepted"}), "cancelled", "either"),
    "dispute": Transition(frozenset({"accepted", "active"}), "disputed", "requester"),
}

SYSTEM: dict[SystemAction, tuple[frozenset[str], Status]] = {
    "authorised": (frozenset({"awaiting_payment"}), "requested"),
    # Instant book: the owner said yes in advance, so a held card confirms it.
    "authorised_instant": (frozenset({"awaiting_payment"}), "accepted"),
    # Also after accept: the capture can be declined (the hold was reversed).
    "payment_failed": (frozenset({"awaiting_payment", "accepted"}), "payment_failed"),
    "expire": (frozenset({"awaiting_payment", "requested"}), "expired"),
    "auto_complete": (frozenset({"accepted", "active"}), "completed"),
    # The owner took the listing down: requests nobody accepted are declined.
    # Accepted bookings stand; the owner still owes them.
    "listing_removed": (frozenset({"awaiting_payment", "requested"}), "declined"),
}


def role_of(actor: str, requester_id: str, owner_id: str) -> Role | None:
    if actor == requester_id:
        return "requester"
    if actor == owner_id:
        return "owner"
    return None


def next_status(action: Action, status: str, actor: str, requester_id: str, owner_id: str) -> Status:
    """The status after ``action``, or an error saying exactly why not."""
    t = TRANSITIONS[action]
    role = role_of(actor, requester_id, owner_id)
    if role is None:
        raise Forbidden("this booking is not yours")
    if t.by != "either" and role != t.by:
        raise Forbidden(f"only the {t.by} can {action} a booking")
    if status not in t.from_states:
        raise Conflict(f"cannot {action} a booking that is {status.replace('_', ' ')}")
    return t.to_state


def system_status(action: SystemAction, status: str) -> Status | None:
    """The status a system event moves a booking to, or None when it no longer
    applies (a payment result for a booking already cancelled, say)."""
    from_states, to_state = SYSTEM[action]
    return to_state if status in from_states else None


def check_can_rate(status: str, already_rated: bool, actor: str, requester_id: str) -> None:
    if actor != requester_id:
        raise Forbidden("only the requester can rate a booking")
    if status != "completed":
        raise Conflict(f"cannot rate a booking that is {status.replace('_', ' ')}")
    if already_rated:
        raise Conflict("this booking has already been rated")
