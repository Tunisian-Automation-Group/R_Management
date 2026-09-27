"""Legal invoice documents: the Factur-X PDF and its EN 16931 XML, the tax
treatment per recipient, immutability, credit notes and the renter's receipt
(docs/research/2026-10-invoices.md)."""

from __future__ import annotations

import hashlib
import io

import pytest
from facturx import get_xml_from_pdf, xml_check_schematron, xml_check_xsd
from fastapi.testclient import TestClient
from payments.invoices import treatment_of
from payments.main import build_app
from payments.provider import FakeProvider
from payments.settings import Settings
from pypdf import PdfReader

from cappy_common.events import BOOKING_STATUS_CHANGED, Event, reset_memory_broker
from cappy_common.ids import new_id
from cappy_common.testing import TestIssuer
from cappy_common.timeutil import now_iso

INTERNAL = {"X-Internal-Token": "i" * 40}


@pytest.fixture()
def issuer():
    return TestIssuer()


@pytest.fixture()
def app(issuer):
    reset_memory_broker()
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite://",
        internal_token="i" * 40,
        legal_company="Cappy GmbH",
        legal_address="Ohlauer Str. 5, 10999 Berlin",
        legal_vat_id="DE123456789",
        legal_tax_number="37/123/45678",
        legal_register="Amtsgericht Charlottenburg, HRB 123456 B",
        legal_directors="Ada Muster",
        legal_email="rechnung@cappy.app",
    )
    return build_app(settings, provider=FakeProvider(), verifier=issuer.verifier())


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        app.state._portal = c.portal
        yield c


def _complete(app, client, booking_id: str, business: dict | None = None, title: str = "Band saw") -> None:
    client.post(
        "/internal/intents",
        json={
            "bookingId": booking_id,
            "requesterId": "buyer",
            "ownerId": "host",
            "amount": 4600,
            "ownerNet": 4000,
            "currency": "eur",
        },
        headers=INTERNAL,
    )
    for to in ("accepted", "completed"):
        data = {"bookingId": booking_id, "from": None, "to": to, "by": "x", "title": title, "ownerName": "Nadia"}
        if business:
            data["ownerBusiness"] = business
        ev = Event(id=new_id("ev"), type=BOOKING_STATUS_CHANGED, source="booking", occurred_at=now_iso(), data=data)
        app.state._portal.call(lambda ev=ev: app.state.dispatcher.handle(ev))


def _only(client, issuer) -> dict:
    [inv] = client.get("/payments/invoices", headers=issuer.headers("host")).json()
    return inv


def _text(pdf: bytes) -> str:
    return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_the_recipients_vat_id_decides_the_tax():
    assert treatment_of("DE", None) == ("standard", "")
    assert treatment_of("DE", "DE987654321") == ("standard", "DE")
    assert treatment_of("DE", "ATU12345678") == ("reverse_charge", "AT")
    assert treatment_of("DE", "EL123456789") == ("reverse_charge", "GR")
    assert treatment_of("DE", "CHE-123.456.789 MWST") == ("not_taxable", "CH")
    assert treatment_of("DE", "GB123456789") == ("not_taxable", "GB")
    assert treatment_of("AT", "DE987654321") == ("reverse_charge", "DE")


@pytest.mark.parametrize(
    "business, treatment, vat, note",
    [
        (
            {"legalName": "Brandt Werkstatt GmbH", "address": "Oranienstr. 12, 10999 Berlin", "vatId": "DE987654321"},
            "standard",
            96,
            None,
        ),
        (
            {"legalName": "Werkstatt Wien GmbH", "address": "Gumpendorfer Str. 1, 1060 Wien", "vatId": "ATU12345678"},
            "reverse_charge",
            0,
            "Steuerschuldnerschaft des Leistungsempfängers",
        ),
        (
            {"legalName": "Atelier Zürich AG", "address": "Langstrasse 4, 8004 Zürich", "vatId": "CHE-123.456.789"},
            "not_taxable",
            0,
            "Nicht im Inland steuerbare Leistung",
        ),
    ],
)
def test_the_pdf_carries_every_mandatory_field(app, client, issuer, business, treatment, vat, note):
    """§ 14 (4) UStG / Art. 226 VAT Directive, per recipient: issuer and
    recipient with addresses and VAT IDs, tax number, register (§ 35a GmbHG),
    number, dates, the service, net, rate, tax, total; the reverse charge or
    not-taxable wording where it applies (§ 14a UStG)."""
    _complete(app, client, "bk_1", business)
    inv = _only(client, issuer)
    assert inv["taxTreatment"] == treatment and inv["vat"] == vat and inv["gross"] == 600
    pdf = client.get(inv["pdfUrl"].removeprefix("/api"), headers=issuer.headers("host"))
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    text = _text(pdf.content)
    for field in (
        "Rechnung",
        inv["number"],
        "Cappy GmbH",
        "Ohlauer Str. 5",
        "DE123456789",
        "37/123/45678",
        "HRB 123456 B",
        "Ada Muster",
        business["legalName"],
        business["address"].split(",")[0],
        business["vatId"],
        "Band saw",
        "Rechnungsdatum",
        "Leistungsdatum",
        "6,00 €",
    ):
        assert field in text, field
    if note:
        assert note in text
    # The EN 16931 XML inside is valid against the schema and the business rules.
    _, xml = get_xml_from_pdf(pdf.content, check_xsd=True)
    xml_check_schematron(xml, flavor="factur-x", level="en16931")
    category = {
        "standard": "<ram:CategoryCode>S<",
        "reverse_charge": "<ram:CategoryCode>AE<",
        "not_taxable": "<ram:CategoryCode>O<",
    }
    assert category[treatment] in xml.decode()


def test_the_xml_download_is_the_same_invoice(app, client, issuer):
    _complete(app, client, "bk_1")
    inv = _only(client, issuer)
    xml = client.get(inv["xmlUrl"].removeprefix("/api"), headers=issuer.headers("host"))
    assert xml.status_code == 200 and xml.headers["content-type"].startswith("application/xml")
    xml_check_xsd(xml.content, flavor="factur-x", level="en16931")
    xml_check_schematron(xml.content, flavor="factur-x", level="en16931")
    assert f"<ram:ID>{inv['number']}</ram:ID>" in xml.text and "<ram:TypeCode>380</ram:TypeCode>" in xml.text


def test_only_the_owner_or_staff_read_an_invoice(app, client, issuer):
    _complete(app, client, "bk_1")
    inv = _only(client, issuer)
    url = inv["pdfUrl"].removeprefix("/api")
    assert client.get(url, headers=issuer.headers("buyer")).status_code == 404
    assert (
        client.get(f"/admin/payments/invoices/{inv['number']}.pdf", headers=issuer.headers("host")).status_code == 403
    )
    staff = {"Authorization": f"Bearer {issuer.token('staff-1', **{'cognito:groups': ['admin']})}"}
    assert client.get(f"/admin/payments/invoices/{inv['number']}.pdf", headers=staff).status_code == 200


def test_an_issued_invoice_never_changes(app, client, issuer):
    """GoBD: the PDF is rendered once and kept; a later change of the
    operator's details (or the reader's language) changes nothing issued."""
    _complete(app, client, "bk_1")
    inv = _only(client, issuer)
    url = inv["pdfUrl"].removeprefix("/api")
    first = client.get(url, headers={**issuer.headers("host"), "Accept-Language": "de-DE"}).content
    app.state.settings.legal_company = "Renamed GmbH"
    app.state.settings.legal_address = "Elsewhere 1, 20095 Hamburg"
    again = client.get(url, headers={**issuer.headers("host"), "Accept-Language": "en-US"}).content
    assert again == first
    assert "Cappy GmbH" in _text(again) and "Renamed" not in _text(again)

    async def stored():
        from payments.tables import InvoiceRow

        async with app.state.db.session() as s:
            return await s.get(InvoiceRow, inv["number"])

    row = app.state._portal.call(stored)
    assert row.pdf_sha256 == hashlib.sha256(first).hexdigest() and row.document_lang == "de"
    # The web page, rendered live, still shows the issuer as it was at issue.
    page = client.get(f"/payments/invoices/{inv['number']}", headers=issuer.headers("host")).text
    assert "Cappy GmbH" in page and "Renamed" not in page


def test_a_credit_note_reverses_an_invoice_once(app, client, issuer):
    _complete(app, client, "bk_1")
    inv = _only(client, issuer)
    staff = {"Authorization": f"Bearer {issuer.token('staff-1', **{'cognito:groups': ['admin']})}"}
    url = f"/admin/payments/invoices/{inv['number']}/credit-note"
    assert (
        client.post(url, json={"reason": "Booking refunded in full"}, headers=issuer.headers("host")).status_code == 403
    )
    r = client.post(url, json={"reason": "Booking refunded in full"}, headers=staff)
    assert r.status_code == 201, r.text
    cn = r.json()
    assert cn["number"].startswith("CAP-") and "-G000001" in cn["number"] and cn["corrects"] == inv["number"]
    assert cn["gross"] == inv["gross"]
    assert client.post(url, json={"reason": "Booking refunded in full"}, headers=staff).status_code == 409
    [listed] = client.get("/payments/invoices", headers=issuer.headers("host")).json()
    assert listed["correctedBy"] == cn["number"]
    pdf = client.get(cn["pdfUrl"].removeprefix("/api"), headers=issuer.headers("host"))
    assert pdf.status_code == 200
    text = _text(pdf.content)
    assert "Rechnungskorrektur" in text and inv["number"] in text and "Booking refunded in full" in text
    _, xml = get_xml_from_pdf(pdf.content, check_xsd=True)
    xml_check_schematron(xml, flavor="factur-x", level="en16931")
    assert b"<ram:TypeCode>381</ram:TypeCode>" in xml and inv["number"].encode() in xml
    assert client.get(cn["pdfUrl"].removeprefix("/api"), headers=issuer.headers("buyer")).status_code == 404


def test_the_renter_gets_a_receipt_not_an_invoice(app, client, issuer):
    _complete(app, client, "bk_1")
    r = client.get("/payments/receipts/bk_1.pdf", headers={**issuer.headers("buyer"), "Accept-Language": "en-GB"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = _text(r.content)
    assert "Receipt" in text and "€46.00" in text and "€6.00" in text and "not a tax invoice" in text
    assert "Invoice" not in text.replace("tax invoice", "").replace("own invoice", "")
    assert client.get("/payments/receipts/bk_1.pdf", headers=issuer.headers("host")).status_code == 404
    assert client.get("/payments/receipts/nope.pdf", headers=issuer.headers("buyer")).status_code == 404
