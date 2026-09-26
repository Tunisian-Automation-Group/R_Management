"""Every table that holds a person is accounted for in deletion and export (D-11)."""

from __future__ import annotations

import importlib
import inspect
import re

import pytest
from notifications.tables import Base as NotificationsBase
from payments.tables import Base as PaymentsBase

from booking.tables import Base as BookingBase
from cappy_common.privacy import DELETION_CODE, EXPORT_CODE, REGISTER
from catalog.tables import Base as CatalogBase

SERVICES = {
    "catalog": CatalogBase.metadata,
    "booking": BookingBase.metadata,
    "payments": PaymentsBase.metadata,
    "notifications": NotificationsBase.metadata,
}
# A column naming a person, by the names this codebase uses for one.
PERSON = re.compile(
    r"(^|_)(owner|user|requester|author|reporter|sender|blocker|blocked|person|actor|recipient)(_id)?$"
    r"|^(by|principal|sub)$"
)
# Tables whose person ids are transient plumbing, pruned on their own.
PLUMBING = {"outbox", "processed_events", "rate_hits"}


def _person_tables() -> set[str]:
    found = set()
    for service, metadata in SERVICES.items():
        for table in metadata.tables.values():
            if table.name in PLUMBING:
                continue
            if table.name == "owners" or any(PERSON.search(c.name) for c in table.columns):
                found.add(f"{service}.{table.name}")
    return found


def _source(ref: str) -> str:
    module, _, path = ref.partition(":")
    obj = importlib.import_module(module)
    for part in path.split("."):
        obj = getattr(obj, part)
    return inspect.getsource(obj)


def test_every_table_holding_a_person_is_in_the_register():
    tables = _person_tables()
    assert tables - set(REGISTER) == set(), "add these to cappy_common/privacy.py"
    assert set(REGISTER) - tables == set(), "the register names tables that no longer exist"


@pytest.mark.parametrize("name", sorted(REGISTER))
def test_the_code_does_what_the_register_says(name):
    entry = REGISTER[name]
    service = name.split(".")[0]
    if entry.deletion == "keep" or not entry.exported:
        assert entry.why, f"{name}: say why it is kept or not exported"
    if entry.deletion != "keep":
        code = "".join(_source(ref) for ref in DELETION_CODE[service])
        assert re.search(entry.token, code), f"{name}: account deletion never touches {entry.token}"
    if entry.exported:
        code = "".join(_source(ref) for ref in EXPORT_CODE[service])
        assert re.search(entry.token, code), f"{name}: the data export leaves out {entry.token}"


def test_every_personal_listing_field_goes_with_the_account():
    """A listing's spec is one JSON column: its personal keys are named in
    LISTING_SPEC and account deletion uses that list."""
    from pydantic.alias_generators import to_camel

    from cappy_common.models import BatchListing, WindowListing
    from cappy_common.privacy import LISTING_SPEC

    looks_personal = re.compile(r"location|postal|address|label|machine|note|phone|email|name")
    fields = {to_camel(f) for m in (WindowListing, BatchListing) for f in m.model_fields}
    personal = {f for f in fields if looks_personal.search(f.lower())} - {"title"}
    assert personal <= set(LISTING_SPEC), f"add to privacy.LISTING_SPEC: {personal - set(LISTING_SPEC)}"
    assert {"location", "postalCode"} <= set(LISTING_SPEC)
    assert "LISTING_SPEC" in _source("catalog.repository:CatalogRepository.forget")
