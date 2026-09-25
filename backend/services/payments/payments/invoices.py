"""Invoices for the platform fee, issued to owners.

VAT: the fee (15% of the price, inside the total) is treated as including
German VAT at 19% for every owner. That is the conservative reading; the
reverse charge for EU business owners and OSS for private owners come once
counsel confirms them (docs/research/2026-09-launch-gaps.md, G-B2).
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

from fastapi import Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_principal
from cappy_common.errors import NotFound
from cappy_common.models import CamelModel, Iso
from cappy_common.runtime import Tx
from cappy_common.timeutil import iso_from_datetime

from .tables import InvoiceCounterRow, InvoiceRow

router = ApiRouter(prefix="/payments")
VAT_BPS = 1900


async def issue(
    session: AsyncSession, *, booking_id: str, owner_id: str, fee_gross: int, currency: str
) -> InvoiceRow | None:
    """Once per booking (a redelivered event finds the one already issued)."""
    existing = (
        await session.execute(select(InvoiceRow).where(InvoiceRow.booking_id == booking_id))
    ).scalar_one_or_none()
    if existing is not None or fee_gross <= 0:
        return existing
    now = datetime.now(UTC)
    counter = await session.get(InvoiceCounterRow, now.year, with_for_update=True)
    if counter is None:
        from cappy_common.db import insert_or_ignore

        await insert_or_ignore(session, InvoiceCounterRow, year=now.year, last=0)
        counter = await session.get(InvoiceCounterRow, now.year, with_for_update=True, populate_existing=True)
    counter.last += 1
    net = round(fee_gross * 10_000 / (10_000 + VAT_BPS))
    row = InvoiceRow(
        number=f"CAP-{now.year}-{counter.last:07d}",
        booking_id=booking_id,
        owner_id=owner_id,
        net=net,
        vat_rate_bps=VAT_BPS,
        vat=fee_gross - net,
        gross=fee_gross,
        currency=currency,
        issued_at=now,
    )
    session.add(row)
    await session.flush()
    return row


class Invoice(CamelModel):
    number: str
    booking_id: str
    net: int
    vat_rate_bps: int
    vat: int
    gross: int
    currency: str
    issued_at: Iso


def _view(r: InvoiceRow) -> Invoice:
    return Invoice(
        number=r.number,
        booking_id=r.booking_id,
        net=r.net,
        vat_rate_bps=r.vat_rate_bps,
        vat=r.vat,
        gross=r.gross,
        currency=r.currency,
        issued_at=iso_from_datetime(r.issued_at),
    )


@router.get("/invoices", response_model=list[Invoice])
async def my_invoices(session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> list[Invoice]:
    q = select(InvoiceRow).where(InvoiceRow.owner_id == p.sub).order_by(InvoiceRow.issued_at.desc()).limit(500)
    return [_view(r) for r in (await session.execute(q)).scalars()]


@router.get("/invoices/{number}", response_class=HTMLResponse)
async def invoice_page(
    number: str, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> HTMLResponse:
    """A printable invoice (the browser saves it as PDF)."""
    r = await session.get(InvoiceRow, number)
    if r is None or r.owner_id != p.sub:
        raise NotFound("no such invoice")
    eur = lambda c: f"{c / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    body = f"""<!doctype html><html lang="de"><meta charset="utf-8"><title>Rechnung {html.escape(r.number)}</title>
<style>body{{font:14px system-ui;max-width:640px;margin:40px auto}}td{{padding:4px 12px}}</style>
<h1>Rechnung {html.escape(r.number)}</h1>
<p>Rechnungsdatum: {r.issued_at:%d.%m.%Y}<br>Leistung: Vermittlungsgebühr für Buchung {html.escape(r.booking_id)}</p>
<table><tr><td>Netto</td><td>{eur(r.net)}</td></tr>
<tr><td>USt {r.vat_rate_bps / 100:.0f} %</td><td>{eur(r.vat)}</td></tr>
<tr><td><b>Gesamt</b></td><td><b>{eur(r.gross)}</b></td></tr></table>
<p>Leistungserbringer und Steuernummer: siehe Impressum.</p></html>"""
    return HTMLResponse(body)
