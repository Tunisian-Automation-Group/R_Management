"""Every notification kind, rendered in every language (V5-16/18/19): the same
placeholders everywhere, no English left in de or fr, French typography, one
full stop at a time. A new text that breaks any of these fails here."""

from __future__ import annotations

import re
from string import Formatter

import pytest
from notifications.texts import PHRASES, TEXTS, render

LANGS = ("en", "de", "fr")
KINDS = sorted(TEXTS["en"])
SUFFIX = re.compile(r"_(en|de|fr)$")


def _fields(template: str) -> set[str]:
    return {f for _, f, _, _ in Formatter().parse(template) if f}


def _params(kind: str) -> dict[str, str]:
    # Neutral values that match no sentence in any language.
    names = {f for lang in LANGS for part in TEXTS[lang][kind] for f in _fields(part)}
    return {n: f"Q{i}q" for i, n in enumerate(sorted(names))}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.?!:\n]", text) if len(s.split()) >= 3]


@pytest.mark.parametrize("kind", KINDS)
def test_every_language_has_the_kind_with_the_same_placeholders(kind):
    base = {lang: {SUFFIX.sub("", f) for part in TEXTS[lang][kind] for f in _fields(part)} for lang in LANGS}
    assert all(kind in TEXTS[lang] for lang in LANGS)
    assert base["de"] == base["en"] == base["fr"], base


@pytest.mark.parametrize("kind", KINDS)
def test_no_english_is_left_and_french_is_typeset(kind):
    params = _params(kind)
    en_subject, _ = render(kind, "en", **params)
    en = " ".join(render(kind, "en", **params))
    for lang in ("de", "fr"):
        subject, _ = render(kind, lang, **params)
        assert subject != en_subject, f"{kind}/{lang}: the subject is the English one"
        text = " ".join(render(kind, lang, **params))
        assert "{" not in text and "}" not in text, f"{kind}/{lang}: a placeholder was not filled"
        for sentence in _sentences(en):
            assert sentence not in text, f"{kind}/{lang} still says, in English: {sentence!r}"
        assert not re.search(r"(?<!\.)\.\.(?!\.)", text), f"{kind}/{lang}: two full stops"
    fr = " ".join(render(kind, "fr", **params))
    bare = re.sub(r"\S*://\S*|\d:\d", "", fr)  # a URL or a time is not punctuation
    for m in re.finditer(r"[:;?!]", bare):
        # A no-break space before ':', a narrow one before ; ? ! (V6-17).
        want = "\u00a0" if m.group() == ":" else "\u202f"
        assert m.start() > 0 and bare[m.start() - 1] == want, f"{kind}/fr: wrong space before {m.group()!r}"


# One word for each side, the same in the app (web/scripts/check-i18n.ts):
# "vermietende / mietende Person"; "le propriétaire" / "la personne locataire".
OFF_TERMS = {
    "de": re.compile(r"mietende[n]? Seite"),
    "fr": re.compile(r"personne propriétaire|qui loue|\b(?:le|au|du|un) locataire\b", re.I),
}


@pytest.mark.parametrize("kind", KINDS)
def test_both_sides_are_named_the_way_the_app_names_them(kind):
    params = _params(kind)
    for lang, off in OFF_TERMS.items():
        text = " ".join(render(kind, lang, **params))
        assert not off.search(text), f"{kind}/{lang}: {off.search(text).group()!r}"


def test_server_words_reach_readers_in_their_language():
    reason = "The listing was taken down by Cappy."
    for lang in ("de", "fr"):
        _, body = render("declined", lang, title="your booking", link="L", _reason=reason)
        assert not any(english in body for english in PHRASES), body
        assert body.count("..") == 0 and body.split("\n\n")[1].endswith("."), "its own line, one full stop"


def test_a_staff_note_reaches_both_sides_as_written():
    # The resolve form says the note goes to both sides with the decision.
    note = "Die Schutzhaube war gerissen; siehe Fotos."
    for lang in LANGS:
        _, body = render(
            "dispute_partial",
            lang,
            title="Saw",
            link="L",
            how_en="",
            how_de="",
            how_fr="",
            _cents=(1000, "EUR"),
            _note=note,
        )
        assert note.split(";")[0] in body, lang
    _, plain = render("dispute_partial", "en", title="Saw", link="L", how_en="", _cents=(1000, "EUR"), _note="")
    assert "team" not in plain, "no empty note line"
    # Items stored before notes existed still render.
    render("dispute_refunded", "en", title="Saw", link="L", how_en="", _cents=(1000, "EUR"))


def test_the_bell_shows_the_staff_note_with_the_outcome():
    # V6-1: the email carried it; the bell (first paragraph only) did not.
    from notifications.texts import summary

    for lang in LANGS:
        _, text = render(
            "dispute_partial",
            lang,
            title="Saw",
            link="L",
            how_en="",
            how_de="",
            how_fr="",
            _cents=(500, "EUR"),
            _note="The fence was bent.",
        )
        bell = summary("dispute_partial", text)
        assert "The fence was bent." in bell and "\n\nL" not in bell, bell


def test_the_bell_shows_why_a_request_was_declined():
    # V7-4: the email ended with the reason; the bell stopped at the first paragraph.
    from notifications.texts import summary

    # V8-3: an owner's chip reads in the renter's language, like our own reasons.
    for lang, word, chip in (
        ("en", "Reason", "It needs a repair first."),
        ("de", "Grund", "Muss erst repariert werden."),
        ("fr", "Motif", "Il faut d’abord le réparer."),
    ):
        _, text = render("declined", lang, title="Saw", link="L", _reason="It needs a repair first")
        bell = summary("declined", text)
        assert word in bell and chip in bell and "\n\nL" not in bell, bell
        _, staff = render("declined", lang, title="Saw", link="L", _reason="The listing was taken down by Cappy")
        assert "Cappy" in summary("declined", staff), staff


def test_peoples_own_words_are_quoted_as_written_in_french():
    # V7-24: staff wrote "No proof either way; a small goodwill refund?", the
    # French mail re-spaced it to "No proof either way ; a small goodwill refund ?".
    note = "No proof either way; a small goodwill refund?"
    _, body = render("dispute_partial", "fr", title="Saw", link="L", how_fr="", _cents=(300, "EUR"), _note=note)
    assert note in body and " :" in body, body
    _, declined = render("declined", "fr", title="Saw", link="L", _reason="Broken: sorry!")
    assert "Broken: sorry!" in declined and "sorry!." not in declined and "Motif :" in declined, declined
    _, ours = render("declined", "fr", title="Saw", link="L", _reason="The listing was taken down by Cappy")
    assert "retirée par Cappy." in ours


def test_the_owner_hears_who_asked_and_the_renter_where_to_go():
    """V7-23: a request names the renter to the owner; the confirmation tells
    the renter where the hand-over is, postal code included."""
    from notifications.handlers import messages

    from cappy_common.events import BOOKING_STATUS_CHANGED, Event

    def change(**data) -> Event:
        return Event(
            id="ev1", type=BOOKING_STATUS_CHANGED, source="booking", occurred_at="2026-10-01T08:00:00Z", data=data
        )

    base = {
        "bookingId": "bk1", "requesterId": "r", "ownerId": "o", "title": "Saw", "amount": 1500,
        "currency": "EUR", "windowStart": "2026-10-03T08:00:00Z", "expiresAt": "2026-10-02T08:00:00Z",
        "renterName": "Rae R.",
    }  # fmt: skip
    ask = change(**base, **{"from": "awaiting_payment", "to": "requested", "by": "r"})
    [(to, _, kind, params)] = messages(ask, "W")
    assert (to, kind) == ("o", "requested")
    for lang in LANGS:
        assert render(kind, lang, **params)[1].startswith("Rae R."), lang
    handover = {"address": "Teststraße 1, Berlin", "postalCode": "12099"}
    ok = change(**base, **{"from": "requested", "to": "accepted", "by": "o", "handover": handover})
    [(to, _, kind, params)] = messages(ok, "W")
    assert (to, kind) == ("r", "accepted")
    for lang in LANGS:
        assert "Teststraße 1, Berlin, 12099" in render(kind, lang, **params)[1], lang
    # A notice stored before (no name, no address) still reads as it did.
    assert render("requested", "de", title="Saw", link="L", _deadline=None)[1].startswith("Jemand")
    assert "in der App" in render("accepted", "de", title="Saw", link="L")[1]


# V8-9: each side is spoken to, never about. Who reads which kind (handlers.py).
OWNER_READS = {
    "dispute_refunded", "dispute_partial", "dispute_owner_paid", "claim_confirmed", "disputed_owner",
    "extension_cancelled_owner", "no_show_owner_owner", "no_show_renter_owner", "requested",
    "requested_extension", "instant_booked", "instant_extended", "paid", "listing_idle", "dispute_offer",
}  # fmt: skip
RENTER_READS = {
    "dispute_refunded_renter", "dispute_partial_renter", "dispute_owner_paid_renter", "claim_confirmed_renter",
    "dispute_offer_renter", "claim_filed", "owner_cancelled", "declined", "declined_system", "accepted",
    "extension_confirmed", "extension_cancelled_renter", "no_show_owner_renter", "no_show_renter_renter",
    "disputed_renter", "expired",
}  # fmt: skip
ABOUT = {
    "owner": {"en": r"\bthe owner\b", "de": r"vermietende[n]? Person", "fr": r"propriétaire"},
    "renter": {"en": r"\bthe renter\b", "de": r"(?<!ver)mietende[n]? Person", "fr": r"locataire"},
}


@pytest.mark.parametrize(
    ("kind", "reader"), [(k, "owner") for k in sorted(OWNER_READS)] + [(k, "renter") for k in sorted(RENTER_READS)]
)
def test_a_reader_is_spoken_to_not_about(kind, reader):
    params = _params(kind)
    for lang in LANGS:
        text = " ".join(render(kind, lang, **params))
        hit = re.search(ABOUT[reader][lang], text, re.I)
        assert not hit, f"{kind}/{lang} tells the {reader} about '{hit.group()}'"


def test_notices_pick_the_readers_words():
    """V8-9 offers to the renter, V8-17 declines nobody made, V8-18 instant
    extensions, V8-12 a signed-out reporter's language."""
    from notifications.handlers import messages, moderation_mail

    from cappy_common.events import BOOKING_STATUS_CHANGED, DISPUTE_OFFER, REPORT_RECEIVED, Event

    def ev(type_, **data) -> Event:
        return Event(id="ev1", type=type_, source="x", occurred_at="2026-10-01T08:00:00Z", data=data)

    offer = {"bookingId": "bk1", "by": "o", "requesterId": "r", "refundAmount": 600, "currency": "EUR"}
    assert messages(ev(DISPUTE_OFFER, to="r", **offer), "W")[0][2] == "dispute_offer_renter"
    assert messages(ev(DISPUTE_OFFER, to="o", **offer), "W")[0][2] == "dispute_offer"
    base = {"bookingId": "bk1", "requesterId": "r", "ownerId": "o", "title": "Saw"}
    declined = messages(ev(BOOKING_STATUS_CHANGED, **base, to="declined", by="system", declineReason="x"), "W")
    assert [m[2] for m in declined] == ["declined_system"]
    assert [m[2] for m in messages(ev(BOOKING_STATUS_CHANGED, **base, to="declined", by="o"), "W")] == ["declined"]
    instant = ev(
        BOOKING_STATUS_CHANGED, **base, to="accepted", by="payments", **{"from": "awaiting_payment"}, extendsId="bk0"
    )
    assert sorted(m[2] for m in messages(instant, "W")) == ["extension_confirmed", "instant_extended"]
    report = ev(REPORT_RECEIVED, reportId="rp1", reporterEmail="a@b.c", reporterLocale="de-DE")
    assert moderation_mail(report, "W")[0][3]["_locale"] == "de-DE"
    assert render("report_received", "de-DE", report="rp1")[0] != render("report_received", "en", report="rp1")[0]
