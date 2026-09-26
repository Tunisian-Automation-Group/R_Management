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

    for lang, word in (("en", "Reason"), ("de", "Grund"), ("fr", "Motif")):
        _, text = render("declined", lang, title="Saw", link="L", _reason="It needs a repair first")
        bell = summary("declined", text)
        assert word in bell and "It needs a repair first." in bell and "\n\nL" not in bell, bell
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
