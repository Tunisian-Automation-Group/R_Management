"""Invoices for the platform fee, issued to owners.

VAT: the fee (15% of the price, inside the total) is treated as including
the issuer's VAT (German VAT at 19% by default) for every owner. That is the conservative reading; the
reverse charge for EU business owners and OSS for private owners come once
counsel confirms them (docs/research/2026-09-launch-gaps.md, G-B2).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_principal
from cappy_common.errors import NotFound
from cappy_common.models import CamelModel, Iso
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .tables import InvoiceCounterRow, InvoiceRow

router = ApiRouter(prefix="/payments")


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
    # Germany: 10 (§ 147 AO; BEG IV cut Buchungsbelege to 8 from 2025 — confirm
    # with the tax adviser, G-B2); Austria 7, Canada 6, most US states 7.
    retention_years: int = 10


GERMANY = Issuer()


def issuer_of(settings) -> Issuer:  # noqa: ANN001
    return Issuer(
        settings.invoice_time_zone,
        settings.invoice_tax_rate_bps,
        settings.invoice_tax_label,
        settings.invoice_retention_years,
    )


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
    counter = await session.get(InvoiceCounterRow, year, with_for_update=True)
    if counter is None:
        from cappy_common.db import insert_or_ignore

        await insert_or_ignore(session, InvoiceCounterRow, year=year, last=0)
        counter = await session.get(InvoiceCounterRow, year, with_for_update=True, populate_existing=True)
    counter.last += 1
    net = round(fee_gross * 10_000 / (10_000 + issuer.tax_rate_bps))
    d = about or {}
    business = d.get("ownerBusiness") or {}
    start, end = d.get("windowStart"), d.get("windowEnd")
    row = InvoiceRow(
        number=f"CAP-{year}-{counter.last:07d}",
        booking_id=booking_id,
        owner_id=owner_id,
        net=net,
        vat_rate_bps=issuer.tax_rate_bps,
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
    )
    session.add(row)
    await session.flush()
    return row


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


def _day(t: datetime, tz: str) -> str:
    return f"{t.astimezone(ZoneInfo(tz)):%d.%m.%Y}"


def _period(r: InvoiceRow, tz: str) -> str:
    """The service date (§ 14 (4) Nr. 6 UStG): the booked window, in the
    issuer's time zone."""
    if r.service_start is None:
        return _day(r.issued_at, tz)
    a, b = _day(r.service_start, tz), _day(r.service_end or r.service_start, tz)
    return a if a == b else f"{a} – {b}"


def _view(r: InvoiceRow, tz: str) -> Invoice:
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
    )


@router.get("/invoices", response_model=list[Invoice])
async def my_invoices(
    request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> list[Invoice]:
    tz = request.app.state.settings.invoice_time_zone
    q = select(InvoiceRow).where(InvoiceRow.owner_id == p.sub).order_by(InvoiceRow.issued_at.desc()).limit(500)
    return [_view(r, tz) for r in (await session.execute(q)).scalars()]


# The invoice's words in the owner's language (V6-21). The § 14 (4) UStG
# fields are there in every language: an invoice may be in any language, and
# a German issuer's tax number and VAT ID are always on it.
LABELS: dict[str, dict[str, str]] = {
    "de": {
        "invoice": "Rechnung",
        "to": "An",
        "date": "Rechnungsdatum",
        "service_date": "Leistungsdatum",
        "service": "Leistung",
        "fee": "Vermittlungsgebühr für {title}",
        "fee_untitled": "Vermittlungsgebühr",
        "booking": "Buchungsreferenz",
        "net": "Netto",
        "total": "Gesamt",
        "vat_id": "USt-IdNr.",
        "tax_number": "Steuernummer",
        "withheld": "Der Betrag wurde bei der Auszahlung einbehalten.",
    },
    "en": {
        "invoice": "Invoice",
        "to": "To",
        "date": "Invoice date",
        "service_date": "Date of service",
        "service": "Service",
        "fee": "Platform fee for {title}",
        "fee_untitled": "Platform fee",
        "booking": "Booking reference",
        "net": "Net",
        "total": "Total",
        "vat_id": "VAT ID (USt-IdNr.)",
        "tax_number": "Tax number (Steuernummer)",
        "withheld": "The amount was withheld from the payout.",
    },
    "fr": {
        "invoice": "Facture",
        "to": "À",
        "date": "Date de facture",
        "service_date": "Date de la prestation",
        "service": "Prestation",
        "fee": "Frais de service pour {title}",
        "fee_untitled": "Frais de service",
        "booking": "Référence de réservation",
        "net": "Montant HT",
        "total": "Total TTC",
        "vat_id": "N° de TVA (USt-IdNr.)",
        "tax_number": "Numéro fiscal (Steuernummer)",
        "withheld": "Le montant a été retenu sur le versement.",
    },
}


def _lang(accept_language: str | None) -> str:
    code = (accept_language or "").strip().lower()[:2]
    return code if code in LABELS else "de" if not code else "en"


def _money(cents: int, currency: str, lang: str) -> str:
    symbol = {"EUR": "€", "GBP": "£", "USD": "$", "CAD": "$"}.get(currency.upper(), currency.upper())
    amount = f"{cents / 100:,.2f}"
    if lang == "en":
        return f"{symbol}{amount}" if len(symbol) == 1 else f"{amount} {symbol}"
    thin, nbsp = "\u202f", "\u00a0"
    if lang == "fr":
        return amount.replace(",", thin).replace(".", ",") + nbsp + symbol
    return amount.replace(",", "X").replace(".", ",").replace("X", ".") + " " + symbol


@router.get("/invoices/{number}", response_class=HTMLResponse)
async def invoice_page(
    number: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> HTMLResponse:
    """A printable invoice (the browser saves it as PDF) with the § 14 (4) UStG
    fields: issuer and recipient with addresses, the issuer's tax number or VAT
    ID, date, number, the service and its date, net, rate, tax and total. In
    the reader's language (the app's ``Accept-Language``); German without one."""
    r = await session.get(InvoiceRow, number)
    if r is None or r.owner_id != p.sub:
        raise NotFound("no such invoice")
    st = request.app.state.settings
    tz, label = st.invoice_time_zone, st.invoice_tax_label
    lang = _lang(request.headers.get("accept-language"))
    w = LABELS[lang]
    e = lambda v: html.escape(v or "")  # noqa: E731
    lines = lambda v: "<br>".join(html.escape(x.strip()) for x in (v or "").split(",") if x.strip())  # noqa: E731
    cash = lambda c: _money(c, r.currency, lang)  # noqa: E731
    tax_ids = "<br>".join(
        x
        for x in (
            f"{w['vat_id']}: {e(st.legal_vat_id)}" if st.legal_vat_id else "",
            f"{w['tax_number']}: {e(st.legal_tax_number)}" if st.legal_tax_number else "",
        )
        if x
    )
    # A trader's business address (S-4), else the one the payout provider
    # verified (V4-7); see ``issue``.
    recipient = e(r.recipient_name) + (f"<br>{lines(r.recipient_address)}" if r.recipient_address else "")
    if r.recipient_vat_id:
        recipient += f"<br>{w['vat_id']}: {e(r.recipient_vat_id)}"
    # Named by the listing; the booking id is the reference, not the service (V6-21).
    what = w["fee"].format(title=e(r.title)) if r.title else w["fee_untitled"]
    body = f"""<!doctype html><html lang="{lang}"><meta charset="utf-8"><title>{w["invoice"]} {e(r.number)}</title>
<style>body{{font:14px system-ui;max-width:640px;margin:40px auto}}td{{padding:4px 12px}}
.cols{{display:flex;justify-content:space-between;gap:24px}}</style>
<div class="cols"><p><b>{e(st.legal_company)}</b><br>{lines(st.legal_address)}<br>{tax_ids}</p>
<p>{w["to"]}:<br>{recipient}</p></div>
<h1>{w["invoice"]} {e(r.number)}</h1>
<p>{w["date"]}: {_day(r.issued_at, tz)}<br>{w["service_date"]}: {_period(r, tz)}
<br>{w["service"]}: {what}<br>{w["booking"]}: {e(r.booking_id)}</p>
<table><tr><td>{w["net"]}</td><td>{cash(r.net)}</td></tr>
<tr><td>{e(label)} {r.vat_rate_bps / 100:g} %</td><td>{cash(r.vat)}</td></tr>
<tr><td><b>{w["total"]}</b></td><td><b>{cash(r.gross)}</b></td></tr></table>
<p>{w["withheld"]}</p></html>"""
    return HTMLResponse(body)
