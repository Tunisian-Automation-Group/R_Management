"""The register of personal data (D-11): every table that holds a person's id,
what account deletion does to it, and whether the data export includes it.

``tests/test_privacy.py`` walks every service's tables and fails when a table
with a person-id column is missing here, when a table said to be deleted or
exported is not touched by the code named for it, or when something kept has
no reason. A new table with a person in it cannot ship unconsidered.
Retention periods and legal bases: docs/retention.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Deletion = Literal["delete", "redact", "keep"]


@dataclass(frozen=True)
class Entry:
    # How the code refers to the table (its row class, constant or helper), as
    # a regular expression: the test looks for it in the deletion and export code.
    token: str
    deletion: Deletion
    exported: bool
    # Required for "keep", and for anything not exported: why.
    why: str = ""


# Where each service deletes and exports ("module:attribute.path").
DELETION_CODE = {
    "catalog": ("catalog.repository:CatalogRepository.forget",),
    "booking": ("booking.handlers:redact_bookings", "booking.handlers:handlers"),
    "payments": ("payments.handlers:handlers",),
    "notifications": ("notifications.handlers:handlers",),
}
EXPORT_CODE = {
    "catalog": ("catalog.repository:CatalogRepository.export",),
    "booking": ("booking.routes:export_person",),
    "payments": ("payments.routes:export_person",),
    "notifications": ("notifications.routes:export_person",),
}

_SESSIONS = "a pseudonymous id and a timestamp that ends older tokens (P-24); nothing else about the person"
_KEYS = "a stored answer for 24 hours so a retry is safe; it repeats what the export already holds"

REGISTER: dict[str, Entry] = {
    # --- catalog ---
    "catalog.owners": Entry("OwnerRow|find_owner", "redact", True),
    "catalog.listings": Entry("ListingRow", "redact", True),
    "catalog.reviews": Entry("ReviewRow", "redact", True),
    "catalog.saved_listings": Entry("SavedRow", "delete", True),
    "catalog.payable_owners": Entry("PayableOwnerRow", "delete", False, "whether payments can pay them: derived"),
    "catalog.media": Entry("MediaRow", "delete", True),
    "catalog.reports": Entry("ReportRow", "redact", True),
    "catalog.moderation_actions": Entry(
        "ModerationActionRow",
        "keep",
        True,
        "the DSA record of decisions (Art. 17, 24); the actor is staff, the target an id",
    ),
    "catalog.idempotency_keys": Entry("IDEMPOTENCY", "delete", False, _KEYS),
    "catalog.revoked_sessions": Entry("revoked", "keep", False, _SESSIONS),
    # --- booking ---
    "booking.bookings": Entry("BookingRow|all_for", "redact", True),
    "booking.booking_messages": Entry("MessageRow", "redact", True),
    "booking.booking_evidence": Entry("EvidenceRow", "redact", True),
    "booking.blocks": Entry("BlockRow", "delete", True),
    "booking.verified_people": Entry("VerifiedRow", "delete", True),
    "booking.suspended": Entry(
        "SuspendedRow", "keep", True, "a suspension outlives the account, so a new one can be linked (S-17)"
    ),
    "booking.booking_transitions": Entry(
        "TransitionRow",
        "keep",
        False,
        "the audit trail of status changes (who, as an id, and when) that disputes need; the export has each"
        " booking's current status and dates",
    ),
    "booking.idempotency_keys": Entry("IDEMPOTENCY", "delete", False, _KEYS),
    "booking.revoked_sessions": Entry("revoked", "keep", False, _SESSIONS),
    # --- payments ---
    "payments.payments": Entry("PaymentRow", "redact", True),
    "payments.identities": Entry("IdentityRow", "delete", True),
    "payments.connect_accounts": Entry("ConnectAccountRow", "delete", True),
    "payments.invoices": Entry(
        "InvoiceRow",
        "keep",
        True,
        "tax law keeps invoices for the issuer's period (docs/retention.md), then they are purged",
    ),
    "payments.revoked_sessions": Entry("revoked", "keep", False, _SESSIONS),
    # --- notifications ---
    "notifications.devices": Entry("DeviceRow", "delete", True),
    "notifications.inbox": Entry("InboxRow", "delete", True),
    "notifications.notification_prefs": Entry("PrefsRow|prefs_of", "delete", True),
    "notifications.revoked_sessions": Entry("revoked", "keep", False, _SESSIONS),
}
