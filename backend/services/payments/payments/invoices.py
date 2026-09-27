"""Invoices for the platform fee, issued to owners; credit notes; the
renter's payment receipt.

What is invoiced: Cappy's fee for arranging a booking (15 % of the price,
inside the total), issued to the owner when the payout goes, the fee withheld
from it. The rental itself is the owner's own supply; Cappy invoices it on
nobody's behalf (docs/research/2026-10-invoices.md, "(counsel)").

VAT (§ 3a (2) UStG, Art. 44 and 196 VAT Directive):
- an owner with a VAT ID from another EU state: reverse charge, no VAT shown;
- a business outside the EU (Swiss UID, UK VAT number): not taxable in the
  issuer's country;
- everyone else, including private owners anywhere: the issuer's VAT,
  included in the fee. ponytail: OSS for private owners in other EU states
  and a market -> Issuer map come with counsel (G-B2, M-11).

Invoices never change once issued (GoBD): the issuer is copied onto the row
at issue, the PDF is rendered once and kept with its hash, and a correction
is a credit note with its own number.
"""

# ruff: noqa: E501  (the XML and HTML templates read best one element per line)

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_admin, require_principal
from cappy_common.errors import Conflict, NotFound
from cappy_common.models import CamelModel, Iso
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from . import invoice_doc as docs
from .invoice_doc import COLON, LABELS, TAX, Doc, Party, date_of, lang_of, money, pct
from .tables import CreditNoteRow, InvoiceCounterRow, InvoiceRow, PaymentRow

router = ApiRouter(prefix="/payments")
admin = ApiRouter(prefix="/admin/payments")

# VAT ID prefixes of the EU member states (Greece is EL). Reverse charge
# applies between two of them, never within one.
EU = frozenset("AT BE BG CY CZ DE DK EE EL ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split())


@dataclass(frozen=True)
class Issuer:
    """Who invoices, in which time zone and at what tax: data, so another
    market's entity is settings, not code. Defaults: the German operator.

    ponytail: one issuing entity for every owner today; a market → Issuer map
    (and a template per market's invoice law) when a second entity invoices."""

    # Invoice dates and the numbering year are the issuer's calendar days, not
    # UTC: an invoice issued at 00:30 CEST is dated that day (§ 14 UStG).
    time_zone: str = "Europe/Berlin"
    tax_rate_bps: int = 1900
    tax_label: str = "USt"
    # How long this entity must keep its invoices, counted from the end of the
    # year of issue; then they are deleted (jobs.purge_invoices_once, D-9).
    # Germany: 8 since 2025 (§ 14b (1) UStG, § 147 (3) AO as amended by the
    # BEG IV); Austria 7, Canada 6, most US states 7.
    retention_years: int = 8
    # The issuer's identity, copied onto each invoice at issue.
    name: str = ""
    address: str = ""
    vat_id: str = ""
    tax_number: str = ""
    register: str = ""
    directors: str = ""
    email: str = ""
    country: str = "DE"


GERMANY = Issuer()


def issuer_of(settings) -> Issuer:  # noqa: ANN001
    return Issuer(
        settings.invoice_time_zone,
        settings.invoice_tax_rate_bps,
        settings.invoice_tax_label,
        settings.invoice_retention_years,
        settings.legal_company,
        settings.legal_address,
        settings.legal_vat_id,
        settings.legal_tax_number,
        settings.legal_register,
        settings.legal_directors,
        settings.legal_email,
        settings.legal_country,
    )


def treatment_of(issuer_country: str, recipient_vat_id: str | None) -> tuple[str, str]:
    """(treatment, recipient country) from the recipient's VAT ID: its prefix
    is the member state that issued it (a Swiss UID starts CHE)."""
    vat = (recipient_vat_id or "").replace(" ", "").upper()
    if not vat:
        return "standard", ""
    if vat.startswith("CHE"):
        return ("standard" if issuer_country == "CH" else "not_taxable"), "CH"
    cc = vat[:2]
    country = "GR" if cc == "EL" else cc
    issuer_eu = "EL" if issuer_country == "GR" else issuer_country
    if cc == issuer_eu:
        return "standard", country
    if cc in EU and issuer_eu in EU:
        return "reverse_charge", country
    if cc == "GB":
        return "not_taxable", "GB"
    return "standard", country


async def _next_number(session: AsyncSession, year: int, *, credit: bool) -> str:
    """The next number of the year's series, taken under a row lock, so none
    repeats or is skipped however many payouts run at once. Credit notes are
    their own series (§ 14 (4) Nr. 4: "one or more series")."""
    # ponytail: credit notes count under the negative year in the same
    # counter table; a series column when a third series appears.
    key = -year if credit else year
    counter = await session.get(InvoiceCounterRow, key, with_for_update=True)
    if counter is None:
        from cappy_common.db import insert_or_ignore

        await insert_or_ignore(session, InvoiceCounterRow, year=key, last=0)
        counter = await session.get(InvoiceCounterRow, key, with_for_update=True, populate_existing=True)
    counter.last += 1
    return f"CAP-{year}-G{counter.last:06d}" if credit else f"CAP-{year}-{counter.last:07d}"


async def issue(
    session: AsyncSession,
    *,
    booking_id: str,
    owner_id: str,
    fee_gross: int,
    currency: str,
    about: dict | None = None,
    issuer: Issuer = GERMANY,
    verified_address: str | None = None,
) -> InvoiceRow | None:
    """Once per booking (a redelivered event finds the one already issued).

    ``about`` is the booking event: what the fee was for, when, and who the
    owner is. Copied onto the invoice, which never changes once issued (GoBD).

    The recipient's address (§ 14 (4) Nr. 1 UStG, V4-7): a trader's business
    address; otherwise the address the payout provider verified for the
    owner (``verified_address``, KYC, which Stripe requires of every German
    individual before payouts). An owner is always paid before invoiced, so
    it is there in practice; a small invoice without one is still valid
    under § 33 UStDV (up to €250 gross, no recipient needed)."""
    existing = (
        await session.execute(select(InvoiceRow).where(InvoiceRow.booking_id == booking_id))
    ).scalar_one_or_none()
    if existing is not None or fee_gross <= 0:
        return existing
    now = datetime.now(UTC)
    year = now.astimezone(ZoneInfo(issuer.time_zone)).year
    d = about or {}
    business = d.get("ownerBusiness") or {}
    treatment, recipient_country = treatment_of(issuer.country, business.get("vatId"))
    rate = issuer.tax_rate_bps if treatment == "standard" else 0
    net = round(fee_gross * 10_000 / (10_000 + rate))
    start, end = d.get("windowStart"), d.get("windowEnd")
    row = InvoiceRow(
        number=await _next_number(session, year, credit=False),
        booking_id=booking_id,
        owner_id=owner_id,
        net=net,
        vat_rate_bps=rate,
        vat=fee_gross - net,
        gross=fee_gross,
        currency=currency,
        issued_at=now,
        title=d.get("title"),
        service_start=dt_from_iso(start) if start else None,
        service_end=dt_from_iso(end) if end else None,
        recipient_name=business.get("legalName") or d.get("ownerName"),
        recipient_address=business.get("address") or verified_address,
        recipient_vat_id=business.get("vatId"),
        recipient_country=recipient_country or None,
        tax_treatment=treatment,
        issuer_name=issuer.name or None,
        issuer_address=issuer.address or None,
        issuer_vat_id=issuer.vat_id or None,
        issuer_tax_number=issuer.tax_number or None,
        issuer_register=issuer.register or None,
        issuer_directors=issuer.directors or None,
        issuer_email=issuer.email or None,
        issuer_country=issuer.country or None,
    )
    session.add(row)
    await session.flush()
    return row


async def credit(session: AsyncSession, invoice: InvoiceRow, reason: str, issuer: Issuer) -> CreditNoteRow:
    """Reverse an issued invoice in full (a Stornorechnung). One per invoice:
    a second correction corrects the credit note's replacement, not this."""
    done = (
        await session.execute(select(CreditNoteRow).where(CreditNoteRow.corrects == invoice.number))
    ).scalar_one_or_none()
    if done is not None:
        raise Conflict(f"invoice {invoice.number} is already corrected by {done.number}")
    now = datetime.now(UTC)
    row = CreditNoteRow(
        number=await _next_number(session, now.astimezone(ZoneInfo(issuer.time_zone)).year, credit=True),
        corrects=invoice.number,
        booking_id=invoice.booking_id,
        owner_id=invoice.owner_id,
        net=invoice.net,
        vat_rate_bps=invoice.vat_rate_bps,
        vat=invoice.vat,
        gross=invoice.gross,
        currency=invoice.currency,
        reason=reason,
        issued_at=now,
    )
    session.add(row)
    await session.flush()
    return row


# --- the document, from the frozen rows ---------------------------------------------------


def _seller(r: InvoiceRow, st) -> tuple[Party, str, str, str]:  # noqa: ANN001
    """The issuer as it was at issue; the current settings only for
    invoices issued before 0013 kept it."""
    if r.issuer_name:
        return (
            Party(
                r.issuer_name,
                r.issuer_address or "",
                r.issuer_vat_id or "",
                r.issuer_tax_number or "",
                r.issuer_country or "DE",
            ),
            r.issuer_register or "",
            r.issuer_directors or "",
            r.issuer_email or "",
        )
    return (
        Party(st.legal_company, st.legal_address, st.legal_vat_id, st.legal_tax_number, st.legal_country),
        st.legal_register,
        st.legal_directors,
        st.legal_email,
    )


def _line(r: InvoiceRow, lang: str) -> str:
    w = LABELS[lang]
    return w["fee"].format(title=r.title) if r.title else w["fee_untitled"]


def _notes(treatment: str, lang: str) -> list[str]:
    w = LABELS[lang]
    return (
        [w["reverse_charge"]]
        if treatment == "reverse_charge"
        else [w["not_taxable"]]
        if treatment == "not_taxable"
        else []
    )


def doc_of(r: InvoiceRow, st, lang: str) -> Doc:  # noqa: ANN001
    seller, register, directors, email = _seller(r, st)
    buyer = Party(
        r.recipient_name or "",
        r.recipient_address or "",
        r.recipient_vat_id or "",
        "",
        r.recipient_country or seller.country,
    )
    return Doc(
        "invoice",
        r.number,
        r.issued_at,
        r.currency,
        seller,
        buyer,
        _line(r, lang),
        r.net,
        r.vat,
        r.gross,
        r.vat_rate_bps,
        treatment=r.tax_treatment or "standard",
        booking_id=r.booking_id,
        service_start=r.service_start,
        service_end=r.service_end,
        seller_register=register,
        seller_directors=directors,
        seller_email=email,
        notes=_notes(r.tax_treatment or "standard", lang),
    )


def credit_doc_of(cn: CreditNoteRow, inv: InvoiceRow, st, lang: str) -> Doc:  # noqa: ANN001
    base = doc_of(inv, st, lang)
    w = LABELS[lang]
    return Doc(
        "credit_note",
        cn.number,
        cn.issued_at,
        cn.currency,
        base.seller,
        base.buyer,
        base.line,
        cn.net,
        cn.vat,
        cn.gross,
        cn.vat_rate_bps,
        treatment=base.treatment,
        booking_id=cn.booking_id,
        service_start=inv.service_start,
        service_end=inv.service_end,
        seller_register=base.seller_register,
        seller_directors=base.seller_directors,
        seller_email=base.seller_email,
        corrects=inv.number,
        corrects_date=inv.issued_at,
        reason=cn.reason,
        notes=[*base.notes, f"{w['reason']}{COLON[lang]} {cn.reason}"],
    )


def _frozen_pdf(row: InvoiceRow | CreditNoteRow, doc: Doc, st, lang: str, locale: str) -> bytes:  # noqa: ANN001
    """Render once, keep for good: the PDF people download is the one that
    was issued, byte for byte, whatever changes later."""
    if row.pdf is None:
        tz = st.invoice_time_zone
        plain = docs.pdf(doc, tz=tz, lang=lang, locale=locale)
        title = f"{LABELS[lang]['invoice' if doc.kind == 'invoice' else 'credit_note']} {doc.number}"
        row.pdf = docs.factur_x(plain, docs.cii_xml(doc, tz), lang=lang, title=title)
        row.pdf_sha256 = hashlib.sha256(row.pdf).hexdigest()
        row.document_lang = lang
    return row.pdf


def _pdf_response(content: bytes, name: str) -> Response:
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"', "Cache-Control": "private, no-store"},
    )


def _xml_response(content: bytes, name: str) -> Response:
    return Response(
        content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{name}.xml"', "Cache-Control": "private, no-store"},
    )


def _locale(request: Request) -> str:
    return (request.headers.get("accept-language") or "").split(",")[0].strip()


# --- the owner's list and documents -----------------------------------------------------


class Invoice(CamelModel):
    number: str
    booking_id: str
    # What the list shows: "Service fee · <listing> · <service day>".
    description: str
    title: str | None = None
    service_start: Iso | None = None
    service_end: Iso | None = None
    net: int
    vat_rate_bps: int
    vat: int
    gross: int
    currency: str
    issued_at: Iso
    tax_treatment: str = "standard"
    # Where the documents are: the Factur-X PDF and its XML (same data).
    pdf_url: str = ""
    xml_url: str = ""
    # A credit note that reverses this invoice, if any.
    corrected_by: str | None = None


def _day(t: datetime, tz: str) -> str:
    return f"{t.astimezone(ZoneInfo(tz)):%d.%m.%Y}"


def _period(r: InvoiceRow, tz: str) -> str:
    """The service date (§ 14 (4) Nr. 6 UStG): the booked window, in the
    issuer's time zone."""
    if r.service_start is None:
        return _day(r.issued_at, tz)
    a, b = _day(r.service_start, tz), _day(r.service_end or r.service_start, tz)
    return a if a == b else f"{a} – {b}"


def _view(r: InvoiceRow, tz: str, corrected_by: str | None = None) -> Invoice:
    base = f"/api/payments/invoices/{r.number}"
    return Invoice(
        number=r.number,
        booking_id=r.booking_id,
        description=" · ".join(x for x in ("Service fee", r.title, _period(r, tz)) if x),
        title=r.title,
        service_start=iso_from_datetime(r.service_start) if r.service_start else None,
        service_end=iso_from_datetime(r.service_end) if r.service_end else None,
        net=r.net,
        vat_rate_bps=r.vat_rate_bps,
        vat=r.vat,
        gross=r.gross,
        currency=r.currency,
        issued_at=iso_from_datetime(r.issued_at),
        tax_treatment=r.tax_treatment or "standard",
        pdf_url=f"{base}.pdf",
        xml_url=f"{base}.xml",
        corrected_by=corrected_by,
    )


@router.get("/invoices", response_model=list[Invoice])
async def my_invoices(
    request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> list[Invoice]:
    tz = request.app.state.settings.invoice_time_zone
    q = select(InvoiceRow).where(InvoiceRow.owner_id == p.sub).order_by(InvoiceRow.issued_at.desc()).limit(500)
    rows = list((await session.execute(q)).scalars())
    notes = {
        c.corrects: c.number
        for c in (
            await session.execute(select(CreditNoteRow).where(CreditNoteRow.corrects.in_([r.number for r in rows])))
        ).scalars()
    }
    return [_view(r, tz, notes.get(r.number)) for r in rows]


async def _mine(session: AsyncSession, number: str, p: Principal) -> InvoiceRow:
    r = await session.get(InvoiceRow, number)
    if r is None or r.owner_id != p.sub:
        raise NotFound("no such invoice")
    return r


@router.get("/invoices/{number}.pdf", include_in_schema=False)
async def invoice_pdf(
    number: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> Response:
    """The invoice as issued: a Factur-X PDF/A-3 (the EN 16931 XML inside)."""
    r = await _mine(session, number, p)
    st = request.app.state.settings
    lang = r.document_lang or lang_of(_locale(request))
    return _pdf_response(_frozen_pdf(r, doc_of(r, st, lang), st, lang, _locale(request)), r.number)


@router.get("/invoices/{number}.xml", include_in_schema=False)
async def invoice_xml(
    number: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> Response:
    """The same invoice as EN 16931 CII XML, for accounting software that
    wants the data alone (the XRechnung/ZUGFeRD standard's syntax)."""
    r = await _mine(session, number, p)
    st = request.app.state.settings
    lang = r.document_lang or lang_of(_locale(request))
    return _xml_response(docs.cii_xml(doc_of(r, st, lang), st.invoice_time_zone), r.number)


@router.get("/credit-notes/{number}.pdf", include_in_schema=False)
async def credit_note_pdf(
    number: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> Response:
    cn = await session.get(CreditNoteRow, number)
    if cn is None or cn.owner_id != p.sub:
        raise NotFound("no such credit note")
    inv = await session.get(InvoiceRow, cn.corrects)
    st = request.app.state.settings
    lang = cn.document_lang or lang_of(_locale(request))
    return _pdf_response(_frozen_pdf(cn, credit_doc_of(cn, inv, st, lang), st, lang, _locale(request)), cn.number)


@router.get("/receipts/{booking_id}.pdf", include_in_schema=False)
async def receipt_pdf(
    booking_id: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> Response:
    """The renter's payment receipt: what was charged, refunded and paid in
    the end, with Cappy's fee inside it. Not a tax invoice: the rental is the
    owner's supply; a business owner invoices it themselves. Rendered fresh
    each time (it states payment facts, not a tax document)."""
    pay = await session.get(PaymentRow, booking_id)
    if pay is None or pay.requester_id != p.sub or not pay.charge_id:
        raise NotFound("no receipt for this booking")
    st = request.app.state.settings
    locale = _locale(request)
    lang = lang_of(locale)
    w = LABELS[lang]
    refunded = pay.refunded_amount or 0
    doc = Doc(
        "receipt",
        booking_id,
        pay.created_at,
        pay.currency,
        Party(st.legal_company, st.legal_address, st.legal_vat_id, st.legal_tax_number, st.legal_country),
        Party(""),
        w["rental"].format(title=pay.title) if pay.title else w["rental_untitled"],
        0,
        0,
        0,
        0,
        booking_id=booking_id,
        seller_register=st.legal_register,
        seller_directors=st.legal_directors,
        seller_email=st.legal_email,
        charged=pay.amount,
        refunded=refunded,
        fee=pay.amount - pay.owner_net,
    )
    return _pdf_response(docs.pdf(doc, tz=st.invoice_time_zone, lang=lang, locale=locale), f"receipt-{booking_id}")


@router.get("/invoices/{number}", response_class=HTMLResponse)
async def invoice_page(
    number: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> HTMLResponse:
    """The invoice as a web page, the same facts as the PDF (§ 14 (4) UStG:
    issuer and recipient with addresses, the issuer's tax number and VAT ID,
    date, number, the service and its date, net, rate, tax and total), in the
    reader's language (``Accept-Language``; German without one), with the
    PDF and XML one click away."""
    r = await _mine(session, number, p)
    st = request.app.state.settings
    tz = st.invoice_time_zone
    locale = _locale(request)
    lang = lang_of(locale)
    w, c = LABELS[lang], COLON[lang]
    doc = doc_of(r, st, lang)
    day = lambda t: date_of(t, tz, lang, locale)  # noqa: E731
    period = (
        day(r.issued_at)
        if r.service_start is None
        else " – ".join(dict.fromkeys((day(r.service_start), day(r.service_end or r.service_start))))
    )
    label = TAX.get(lang, st.invoice_tax_label)
    e = lambda v: html.escape(v or "")  # noqa: E731
    lines = lambda v: "<br>".join(html.escape(x.strip()) for x in (v or "").split(",") if x.strip())  # noqa: E731
    cash = lambda v: money(v, r.currency, lang)  # noqa: E731
    s = doc.seller
    tax_ids = "<br>".join(
        x
        for x in (
            f"{w['vat_id']}{c} {e(s.vat_id)}" if s.vat_id else "",
            f"{w['tax_number']}{c} {e(s.tax_number)}" if s.tax_number else "",
        )
        if x
    )
    # A trader's business address (S-4), else the one the payout provider
    # verified (V4-7); see ``issue``.
    recipient = e(r.recipient_name) + (f"<br>{lines(r.recipient_address)}" if r.recipient_address else "")
    if r.recipient_vat_id:
        recipient += f"<br>{w['vat_id']}{c} {e(r.recipient_vat_id)}"
    # Named by the listing; the booking id is the reference, not the service (V6-21).
    what = e(doc.line)
    rate = f"{e(label)} {pct(r.vat_rate_bps, lang)}"
    notes = "".join(f'<p class="note">{e(n)}</p>' for n in doc.notes)
    legal = "<br>".join(
        x
        for x in (
            f"{w['register']}{c} {e(doc.seller_register)}" if doc.seller_register else "",
            f"{w['directors']}{c} {e(doc.seller_directors)}" if doc.seller_directors else "",
            e(doc.seller_email),
        )
        if x
    )
    logo = (docs.ASSETS / "logo.svg").read_text()
    body = f"""<!doctype html><html lang="{lang}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{w["invoice"]} {e(r.number)}</title>
<style>
:root{{--ink:#18211a;--ink3:#5a6157;--line:#d9dcd5;--sunken:#f3f2ee;--money:#2c6048}}
body{{font:15px/1.5 "Archivo",system-ui,sans-serif;color:var(--ink);max-width:760px;margin:48px auto;padding:0 20px}}
.head{{display:flex;justify-content:space-between;align-items:flex-start}}.head svg{{height:36px;width:auto}}
.head h1{{margin:0;font-size:28px;text-align:right}}.muted{{color:var(--ink3)}}
.sum{{background:var(--sunken);border-radius:14px;padding:20px 24px;margin:32px 0;display:flex;justify-content:space-between;align-items:center}}
.sum b{{font-size:28px}}.pill{{background:var(--money);color:#fff;border-radius:999px;padding:4px 12px;font-size:13px}}
.cols{{display:flex;justify-content:space-between;gap:24px;margin:24px 0}}.cols p{{margin:0}}
td{{padding:6px 12px}}td:last-child{{text-align:right}}table{{width:100%;border-collapse:collapse}}
.note{{color:var(--ink3);font-size:13px}}footer{{border-top:1px solid var(--line);margin-top:48px;padding-top:16px;font-size:12px;color:var(--ink3);display:flex;gap:32px}}
.dl a{{color:var(--ink);margin-right:16px}}@media print{{.dl{{display:none}}}}
</style>
<div class="head">{logo}<div><h1>{w["invoice"]} {e(r.number)}</h1></div></div>
<div class="sum"><div><b>{cash(r.gross)}</b><br><span class="muted">{e(w["paid_by_withholding"].format(date=day(r.issued_at)))}</span></div><span class="pill">{w["paid"]}</span></div>
<div class="cols"><p><span class="muted">{w["from"]}</span><br><b>{e(s.name)}</b><br>{lines(s.address)}<br>{tax_ids}</p>
<p>{w["to"]}{c}<br>{recipient}</p></div>
<p>{w["date"]}{c} {day(r.issued_at)}<br>{w["service_date"]}{c} {period}
<br>{w["service"]}{c} {what}<br>{w["booking"]}{c} {e(r.booking_id)}</p>
<table><tr><td>{w["net"]}</td><td>{cash(r.net)}</td></tr>
<tr><td>{rate}</td><td>{cash(r.vat)}</td></tr>
<tr><td><b>{w["total"]}</b></td><td><b>{cash(r.gross)}</b></td></tr></table>
{notes}<p>{w["withheld"]}</p>
<p class="dl"><a href="/api/payments/invoices/{e(r.number)}.pdf">PDF</a><a href="/api/payments/invoices/{e(r.number)}.xml">XML (EN 16931)</a></p>
<footer><div>{e(s.name)}<br>{lines(s.address)}</div><div>{legal}</div></footer></html>"""
    return HTMLResponse(body)


# --- staff -------------------------------------------------------------------------------


@admin.get("/invoices/{number}.pdf", include_in_schema=False)
async def staff_invoice_pdf(
    number: str, request: Request, session: AsyncSession = Tx, _: Principal = Depends(require_admin)
) -> Response:
    """Staff read the invoice as issued (support, tax audits)."""
    r = await session.get(InvoiceRow, number)
    if r is None:
        raise NotFound("no such invoice")
    st = request.app.state.settings
    lang = r.document_lang or lang_of(_locale(request))
    return _pdf_response(_frozen_pdf(r, doc_of(r, st, lang), st, lang, _locale(request)), r.number)


class CreditIn(CamelModel):
    reason: str = Field(min_length=8, max_length=500)


class CreditNote(CamelModel):
    number: str
    corrects: str
    gross: int
    currency: str
    issued_at: Iso
    pdf_url: str


@admin.post("/invoices/{number}/credit-note", response_model=CreditNote, status_code=201)
async def staff_credit_note(
    number: str, body: CreditIn, request: Request, session: AsyncSession = Tx, _: Principal = Depends(require_admin)
) -> CreditNote:
    """Correct an issued invoice by reversing it in full. The invoice stays
    as issued; the credit note, with its own number, cancels it. A corrected
    fee is then issued as a new invoice, if one is due."""
    r = await session.get(InvoiceRow, number)
    if r is None:
        raise NotFound("no such invoice")
    cn = await credit(session, r, body.reason, issuer_of(request.app.state.settings))
    return CreditNote(
        number=cn.number,
        corrects=cn.corrects,
        gross=cn.gross,
        currency=cn.currency,
        issued_at=iso_from_datetime(cn.issued_at),
        pdf_url=f"/api/payments/credit-notes/{cn.number}.pdf",
    )
