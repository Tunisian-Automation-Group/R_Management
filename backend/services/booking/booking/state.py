"""The booking state machine, as data.

    requested --accept--> accepted --start--> active --complete--> completed --rate-->
        |                     |
        +--decline--> declined +--cancel--> cancelled   (cancel also from requested)

Every transition names who may make it. The requester is the person who asked;
the owner is the person whose listing it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cappy_common.errors import Conflict, Forbidden
from cappy_common.models import BookingStatus

Action = Literal["accept", "decline", "start", "complete", "cancel"]
Role = Literal["requester", "owner", "either"]


@dataclass(frozen=True)
class Transition:
    from_states: frozenset[str]
    to_state: BookingStatus
    by: Role


TRANSITIONS: dict[Action, Transition] = {
    "accept": Transition(frozenset({"requested"}), "accepted", "owner"),
    "decline": Transition(frozenset({"requested"}), "declined", "owner"),
    "start": Transition(frozenset({"accepted"}), "active", "requester"),
    "complete": Transition(frozenset({"active"}), "completed", "requester"),
    "cancel": Transition(frozenset({"requested", "accepted"}), "cancelled", "either"),
}


def role_of(actor: str, requester_id: str, owner_id: str) -> Role | None:
    if actor == requester_id:
        return "requester"
    if actor == owner_id:
        return "owner"
    return None


def next_status(action: Action, status: str, actor: str, requester_id: str, owner_id: str) -> BookingStatus:
    """The status after ``action``, or an error saying exactly why not."""
    t = TRANSITIONS[action]
    role = role_of(actor, requester_id, owner_id)
    if role is None:
        raise Forbidden("this booking is not yours")
    if t.by != "either" and role != t.by:
        raise Forbidden(f"only the {t.by} can {action} a booking")
    if status not in t.from_states:
        raise Conflict(f"cannot {action} a booking that is {status}")
    return t.to_state


def check_can_rate(status: str, already_rated: bool, actor: str, requester_id: str) -> None:
    if actor != requester_id:
        raise Forbidden("only the requester can rate a booking")
    if status != "completed":
        raise Conflict(f"cannot rate a booking that is {status}")
    if already_rated:
        raise Conflict("this booking has already been rated")
