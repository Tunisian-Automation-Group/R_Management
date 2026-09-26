"""Why a booking was declined or ended, as codes (V8-3).

The English sentence is what is stored and what the catalogues translate (the
app is gettext-style: the English text is the key); the code is what a client
or a mail picks the words by. A reason typed by a person has no code and is
quoted as written.
"""

from __future__ import annotations

# The owner's chips on the decline sheet.
OWNER_REASONS: dict[str, str] = {
    "already_promised": "Already promised it to someone",
    "need_it_myself": "Turns out I need it then",
    "needs_repair": "It needs a repair first",
    "short_notice": "Too short notice for me",
}
# What Cappy itself records.
SYSTEM_REASONS: dict[str, str] = {
    "taken_down": "The listing was taken down by Cappy",
    "owner_removed": "The listing was removed by its owner",
    "suspended": "The account was suspended",
    "parent_cancelled": "The booking it extends was cancelled",
}
REASONS = {**OWNER_REASONS, **SYSTEM_REASONS}
_CODE_OF = {text: code for code, text in REASONS.items()}


def code_of(reason: str | None) -> str | None:
    """The code of a stored reason, or None for a person's own words. Rows
    stored as English sentences before codes existed get theirs too."""
    return _CODE_OF.get((reason or "").strip().rstrip("."))
