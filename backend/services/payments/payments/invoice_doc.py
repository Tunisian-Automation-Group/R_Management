"""What an invoice, credit note or receipt says and how it looks.

Pure functions: the data comes in (the frozen invoice row and its issuer
snapshot), words, a PDF and the EN 16931 XML come out. ``invoices.py`` owns
issuing, storing and the routes; this module never touches the database.

The PDF is laid out like the invoices people trust (Stripe, Airbnb, Apple):
the brand top left, the document's name and number top right, one summary
block with the amount and its status, who from and who to, the line, the tax
block, and every legal detail of the issuer in the footer. It is a Factur-X
(ZUGFeRD 2) invoice: a PDF/A-3 with the EN 16931 CII XML attached, so a
business's accounting reads it without typing (§ 14 (1) UStG e-invoice,
mandatory to receive since 2025, to issue from 2027/2028; docs/research/
2026-10-invoices.md).
"""

# ruff: noqa: E501  (the XML and HTML templates read best one element per line)

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

ASSETS = Path(__file__).parent / "assets"

# --- words ----------------------------------------------------------------------------

# Every language has every § 14 (4) UStG field: an invoice may be in any
# language, and a German issuer's tax number and VAT ID are always on it.
LABELS: dict[str, dict[str, str]] = {
    "de": {
        "invoice": "Rechnung",
        "credit_note": "Rechnungskorrektur",
        "receipt": "Zahlungsbeleg",
        "to": "An",
        "from": "Von",
        "date": "Rechnungsdatum",
        "date_cn": "Datum",
        "date_receipt": "Bezahlt am",
        "service_date": "Leistungsdatum",
        "service": "Leistung",
        "fee": "Vermittlungsgebühr für {title}",
        "fee_untitled": "Vermittlungsgebühr",
        "booking": "Buchungsreferenz",
        "number": "Nummer",
        "qty": "Menge",
        "unit": "Einzelpreis",
        "vat": "USt.",
        "amount": "Betrag",
        "net": "Netto",
        "total": "Gesamt",
        "vat_id": "USt-IdNr.",
        "tax_number": "Steuernummer",
        "register": "Handelsregister",
        "directors": "Geschäftsführung",
        "withheld": "Der Betrag wurde bei der Auszahlung einbehalten.",
        "paid": "Bezahlt",
        "paid_by_withholding": "Einbehalten von deiner Auszahlung am {date}",
        "reverse_charge": "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge, Art. 196 MwStSystRL).",
        "not_taxable": "Nicht im Inland steuerbare Leistung; die Steuer schuldet der Leistungsempfänger.",
        "corrects": "Korrigiert Rechnung {number} vom {date}",
        "reason": "Grund",
        "refunded_cn": "Gutgeschrieben",
        "e_invoice": "Diese PDF enthält die Rechnungsdaten im Format EN 16931 (ZUGFeRD/Factur-X).",
        "page": "Seite 1 von 1",
        "rental": "Miete: {title}",
        "rental_untitled": "Miete",
        "includes_fee": "enthält die Servicegebühr von Cappy: {fee}",
        "refunded": "Erstattet",
        "total_paid": "Bezahlt, insgesamt",
        "paid_by_card": "Mit Karte bezahlt, über Cappy",
        "receipt_note": (
            "Dieser Beleg bestätigt deine Zahlung. Er ist keine Rechnung im Sinne des UStG. "
            "Die Miete erbringt die vermietende Person; Cappy nimmt die Zahlung in ihrem Namen an. "
            "Vermietet ein Unternehmen, stellt es seine Rechnung selbst aus."
        ),
    },
    "en": {
        "invoice": "Invoice",
        "credit_note": "Credit note",
        "receipt": "Receipt",
        "to": "To",
        "from": "From",
        "date": "Invoice date",
        "date_cn": "Date",
        "date_receipt": "Paid on",
        "service_date": "Date of service",
        "service": "Service",
        "fee": "Platform fee for {title}",
        "fee_untitled": "Platform fee",
        "booking": "Booking reference",
        "number": "Number",
        "qty": "Qty",
        "unit": "Unit price",
        "vat": "VAT",
        "amount": "Amount",
        "net": "Net",
        "total": "Total",
        "vat_id": "VAT ID (USt-IdNr.)",
        "tax_number": "Tax number (Steuernummer)",
        "register": "Commercial register",
        "directors": "Managing directors",
        "withheld": "The amount was withheld from the payout.",
        "paid": "Paid",
        "paid_by_withholding": "Withheld from your payout on {date}",
        "reverse_charge": "Reverse charge: VAT is due by the recipient (Art. 196 VAT Directive).",
        "not_taxable": "Not taxable in Germany; any tax is due by the recipient.",
        "corrects": "Corrects invoice {number} of {date}",
        "reason": "Reason",
        "refunded_cn": "Credited",
        "e_invoice": "This PDF carries the invoice data in EN 16931 format (ZUGFeRD/Factur-X).",
        "page": "Page 1 of 1",
        "rental": "Rental: {title}",
        "rental_untitled": "Rental",
        "includes_fee": "includes Cappy's service fee of {fee}",
        "refunded": "Refunded",
        "total_paid": "Total paid",
        "paid_by_card": "Paid by card, through Cappy",
        "receipt_note": (
            "This receipt confirms your payment. It is not a tax invoice. The rental is provided by the "
            "owner; Cappy collects the payment on their behalf. An owner who is a business issues their "
            "own invoice."
        ),
    },
    "fr": {
        "invoice": "Facture",
        "credit_note": "Avoir",
        "receipt": "Reçu",
        "to": "À",
        "from": "De",
        "date": "Date de facture",
        "date_cn": "Date",
        "date_receipt": "Payé le",
        "service_date": "Date de la prestation",
        "service": "Prestation",
        "fee": "Frais de service pour {title}",
        "fee_untitled": "Frais de service",
        "booking": "Référence de réservation",
        "number": "Numéro",
        "qty": "Qté",
        "unit": "Prix unitaire",
        "vat": "TVA",
        "amount": "Montant",
        "net": "Montant HT",
        "total": "Total TTC",
        "vat_id": "N° de TVA (USt-IdNr.)",
        "tax_number": "Numéro fiscal (Steuernummer)",
        "register": "Registre du commerce",
        "directors": "Direction",
        "withheld": "Le montant a été retenu sur le versement.",
        "paid": "Payé",
        "paid_by_withholding": "Retenu sur votre versement du {date}",
        "reverse_charge": "Autoliquidation : la TVA est due par le preneur (art. 196 de la directive TVA).",
        "not_taxable": "Prestation non imposable en Allemagne ; la taxe éventuelle est due par le preneur.",
        "corrects": "Rectifie la facture {number} du {date}",
        "reason": "Motif",
        "refunded_cn": "Crédité",
        "e_invoice": "Ce PDF contient les données de la facture au format EN 16931 (ZUGFeRD/Factur-X).",
        "page": "Page 1 sur 1",
        "rental": "Location : {title}",
        "rental_untitled": "Location",
        "includes_fee": "dont frais de service Cappy : {fee}",
        "refunded": "Remboursé",
        "total_paid": "Total payé",
        "paid_by_card": "Payé par carte, via Cappy",
        "receipt_note": (
            "Ce reçu confirme votre paiement. Ce n’est pas une facture. La location est fournie par le "
            "propriétaire ; Cappy encaisse le paiement en son nom. Un propriétaire professionnel émet sa "
            "propre facture."
        ),
    },
}


def lang_of(accept_language: str | None) -> str:
    code = (accept_language or "").strip().lower()[:2]
    return code if code in LABELS else "de" if not code else "en"


# The reader's typography (V7-10): French puts a no-break space before ':' and
# '%'; English writes 19% and the reader's own date order.
COLON = {"de": ":", "en": ":", "fr": " :"}
# The tax's name in the reader's words. ponytail: German VAT only (one issuer);
# a market's tax words come with the market -> Issuer map.
TAX = {"en": "VAT", "fr": "TVA"}


def pct(rate_bps: int, lang: str) -> str:
    n = f"{rate_bps / 100:g}"
    return f"{n}%" if lang == "en" else f"{n} %" if lang == "fr" else f"{n} %"


def date_of(t: datetime, tz: str, lang: str, locale: str) -> str:
    local = t.astimezone(ZoneInfo(tz))
    if lang == "de":
        return f"{local:%d.%m.%Y}"
    if locale.lower().startswith("en-us"):
        return f"{local.month}/{local.day}/{local.year}"
    return f"{local:%d/%m/%Y}"


def money(cents: int, currency: str, lang: str) -> str:
    symbol = {"EUR": "€", "GBP": "£", "USD": "$", "CAD": "$", "CHF": "CHF"}.get(currency.upper(), currency.upper())
    amount = f"{abs(cents) / 100:,.2f}"
    sign = "−" if cents < 0 else ""
    if lang == "en":
        return sign + (f"{symbol}{amount}" if len(symbol) == 1 else f"{amount} {symbol}")
    thin, nbsp = " ", " "
    if lang == "fr":
        return sign + amount.replace(",", thin).replace(".", ",") + nbsp + symbol
    return sign + amount.replace(",", "X").replace(".", ",").replace("X", ".") + " " + symbol


# --- the document, as data ---------------------------------------------------------------


@dataclass(frozen=True)
class Party:
    name: str
    address: str = ""  # comma-separated lines, the last "<postcode> <city>"
    vat_id: str = ""
    tax_number: str = ""
    country: str = "DE"


@dataclass(frozen=True)
class Doc:
    """One invoice, credit note or receipt, everything it prints. Built from
    the stored (frozen) row, never from live data (GoBD)."""

    kind: str  # "invoice" | "credit_note" | "receipt"
    number: str
    issued_at: datetime
    currency: str
    seller: Party
    buyer: Party
    line: str  # what the service was
    net: int
    vat: int
    gross: int
    vat_rate_bps: int
    treatment: str = "standard"  # "standard" | "reverse_charge" | "not_taxable"
    booking_id: str = ""
    service_start: datetime | None = None
    service_end: datetime | None = None
    seller_register: str = ""
    seller_directors: str = ""
    seller_email: str = ""
    corrects: str = ""  # credit note: the invoice it corrects
    corrects_date: datetime | None = None
    reason: str = ""
    # Receipt only: charged, refunded, the fee inside it.
    charged: int = 0
    refunded: int = 0
    fee: int = 0
    notes: list[str] = field(default_factory=list)


def _lines(address: str) -> list[str]:
    return [x.strip() for x in (address or "").split(",") if x.strip()]


def _postcode_city(address: str) -> tuple[str, str, str]:
    """(street, postcode, city) from "Street 1, 10115 Berlin" (best effort; a
    free-text address the owner or KYC gave)."""
    parts = _lines(address)
    street = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    m = re.match(r"^\s*([A-Z]{0,2}-?\d{3,5}(?:\s?[A-Z]{2})?)\s+(.+)$", rest)
    return (street, m.group(1), m.group(2)) if m else (street, "", rest)


# --- XML (EN 16931, CII D16B, Factur-X / ZUGFeRD 2) -----------------------------------------


def _d(t: datetime, tz: str) -> str:
    return f"{t.astimezone(ZoneInfo(tz)):%Y%m%d}"


def _a(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _party_xml(p: Party, role: str, *, vat_scheme: bool) -> str:
    street, postcode, city = _postcode_city(p.address)
    regs = ""
    if p.vat_id and vat_scheme:
        regs += f'<ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">{escape(p.vat_id)}</ram:ID></ram:SpecifiedTaxRegistration>'
    if p.tax_number and role == "Seller":
        regs += f'<ram:SpecifiedTaxRegistration><ram:ID schemeID="FC">{escape(p.tax_number)}</ram:ID></ram:SpecifiedTaxRegistration>'
    addr = (
        (f"<ram:PostcodeCode>{escape(postcode)}</ram:PostcodeCode>" if postcode else "")
        + (f"<ram:LineOne>{escape(street)}</ram:LineOne>" if street else "")
        + (f"<ram:CityName>{escape(city)}</ram:CityName>" if city else "")
        + f"<ram:CountryID>{escape(p.country or 'DE')}</ram:CountryID>"
    )
    return (
        f"<ram:{role}TradeParty><ram:Name>{escape(p.name or '-')}</ram:Name>"
        f"<ram:PostalTradeAddress>{addr}</ram:PostalTradeAddress>{regs}</ram:{role}TradeParty>"
    )


def cii_xml(doc: Doc, tz: str) -> bytes:
    """The invoice as EN 16931 CII XML (the Factur-X EN16931 profile, which
    XRechnung-capable software also reads). Credit notes are type 381 with
    positive amounts and the corrected invoice referenced."""
    if doc.kind == "receipt":
        raise ValueError("a receipt is not an invoice")
    category, rate, exemption = "S", doc.vat_rate_bps, ""
    if doc.treatment == "reverse_charge":
        category, rate = "AE", 0
        exemption = "<ram:ExemptionReason>Reverse charge</ram:ExemptionReason>"
    elif doc.treatment == "not_taxable":
        category, rate = "O", 0
        exemption = "<ram:ExemptionReason>Not subject to VAT in Germany</ram:ExemptionReason>"
    code = {
        "AE": "<ram:ExemptionReasonCode>VATEX-EU-AE</ram:ExemptionReasonCode>",
        "O": "<ram:ExemptionReasonCode>VATEX-EU-O</ram:ExemptionReasonCode>",
    }.get(category, "")
    rate_xml = "" if category == "O" else f"<ram:RateApplicablePercent>{rate / 100:g}</ram:RateApplicablePercent>"
    # BR-O-02: an "outside the scope" invoice names no seller VAT ID.
    seller_vat = category != "O"
    delivered = doc.service_start or doc.issued_at
    period = ""
    if doc.service_start and doc.service_end and _d(doc.service_start, tz) != _d(doc.service_end, tz):
        period = (
            "<ram:BillingSpecifiedPeriod>"
            f'<ram:StartDateTime><udt:DateTimeString format="102">{_d(doc.service_start, tz)}</udt:DateTimeString></ram:StartDateTime>'
            f'<ram:EndDateTime><udt:DateTimeString format="102">{_d(doc.service_end, tz)}</udt:DateTimeString></ram:EndDateTime>'
            "</ram:BillingSpecifiedPeriod>"
        )
    reference = (
        f"<ram:InvoiceReferencedDocument><ram:IssuerAssignedID>{escape(doc.corrects)}</ram:IssuerAssignedID>"
        + (
            f'<ram:FormattedIssueDateTime><qdt:DateTimeString format="102">{_d(doc.corrects_date, tz)}</qdt:DateTimeString></ram:FormattedIssueDateTime>'
            if doc.corrects_date
            else ""
        )
        + "</ram:InvoiceReferencedDocument>"
        if doc.kind == "credit_note" and doc.corrects
        else ""
    )
    notes = "".join(f"<ram:IncludedNote><ram:Content>{escape(n)}</ram:Content></ram:IncludedNote>" for n in doc.notes)
    type_code = "381" if doc.kind == "credit_note" else "380"
    # Paid already: the fee was withheld from the payout (or credited back).
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100" xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
<rsm:ExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>urn:cen.eu:en16931:2017</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter></rsm:ExchangedDocumentContext>
<rsm:ExchangedDocument><ram:ID>{escape(doc.number)}</ram:ID><ram:TypeCode>{type_code}</ram:TypeCode><ram:IssueDateTime><udt:DateTimeString format="102">{_d(doc.issued_at, tz)}</udt:DateTimeString></ram:IssueDateTime>{notes}</rsm:ExchangedDocument>
<rsm:SupplyChainTradeTransaction>
<ram:IncludedSupplyChainTradeLineItem><ram:AssociatedDocumentLineDocument><ram:LineID>1</ram:LineID></ram:AssociatedDocumentLineDocument><ram:SpecifiedTradeProduct><ram:Name>{escape(doc.line)}</ram:Name></ram:SpecifiedTradeProduct><ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice><ram:ChargeAmount>{_a(doc.net)}</ram:ChargeAmount></ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement><ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="C62">1</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery><ram:SpecifiedLineTradeSettlement><ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>{category}</ram:CategoryCode>{rate_xml}</ram:ApplicableTradeTax><ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>{_a(doc.net)}</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation></ram:SpecifiedLineTradeSettlement></ram:IncludedSupplyChainTradeLineItem>
<ram:ApplicableHeaderTradeAgreement><ram:BuyerReference>{escape(doc.booking_id or doc.number)}</ram:BuyerReference>{_party_xml(doc.seller, "Seller", vat_scheme=seller_vat)}{_party_xml(doc.buyer, "Buyer", vat_scheme=True)}</ram:ApplicableHeaderTradeAgreement>
<ram:ApplicableHeaderTradeDelivery><ram:ActualDeliverySupplyChainEvent><ram:OccurrenceDateTime><udt:DateTimeString format="102">{_d(delivered, tz)}</udt:DateTimeString></ram:OccurrenceDateTime></ram:ActualDeliverySupplyChainEvent></ram:ApplicableHeaderTradeDelivery>
<ram:ApplicableHeaderTradeSettlement><ram:InvoiceCurrencyCode>{escape(doc.currency.upper())}</ram:InvoiceCurrencyCode><ram:ApplicableTradeTax><ram:CalculatedAmount>{_a(doc.vat)}</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>{exemption}<ram:BasisAmount>{_a(doc.net)}</ram:BasisAmount><ram:CategoryCode>{category}</ram:CategoryCode>{code}{rate_xml}</ram:ApplicableTradeTax>{period}<ram:SpecifiedTradePaymentTerms><ram:Description>Paid: withheld from the payout</ram:Description></ram:SpecifiedTradePaymentTerms><ram:SpecifiedTradeSettlementHeaderMonetarySummation><ram:LineTotalAmount>{_a(doc.net)}</ram:LineTotalAmount><ram:TaxBasisTotalAmount>{_a(doc.net)}</ram:TaxBasisTotalAmount><ram:TaxTotalAmount currencyID="{escape(doc.currency.upper())}">{_a(doc.vat)}</ram:TaxTotalAmount><ram:GrandTotalAmount>{_a(doc.gross)}</ram:GrandTotalAmount><ram:TotalPrepaidAmount>{_a(doc.gross)}</ram:TotalPrepaidAmount><ram:DuePayableAmount>0.00</ram:DuePayableAmount></ram:SpecifiedTradeSettlementHeaderMonetarySummation>{reference}</ram:ApplicableHeaderTradeSettlement>
</rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
"""
    return xml.encode("utf-8")


# --- PDF -----------------------------------------------------------------------------------

_FONTS_READY = False


def _fonts() -> None:
    """Archivo (text) and Bodoni Moda (the wordmark), embedded: PDF/A needs
    every font inside the file. OFL, see assets/fonts/OFL.txt."""
    global _FONTS_READY
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for name, file in (
        ("Archivo", "Archivo-Regular.ttf"),
        ("Archivo-SemiBold", "Archivo-SemiBold.ttf"),
        ("Archivo-Bold", "Archivo-Bold.ttf"),
        ("Bodoni", "BodoniModa-Medium.ttf"),
    ):
        pdfmetrics.registerFont(TTFont(name, str(ASSETS / "fonts" / file)))
    _FONTS_READY = True


# The app's tokens, light theme (web/src/app/theme.css): ink, secondary ink,
# lines, the sunken surface and the one accent.
INK, INK3, LINE, SUNKEN, ACCENT, MONEY = "#18211a", "#5a6157", "#d9dcd5", "#f3f2ee", "#b0182e", "#2c6048"


def pdf(doc: Doc, *, tz: str, lang: str, locale: str = "") -> bytes:
    """The document as a plain PDF (A4, or US Letter for a US or Canadian
    reader). ``factur_x`` turns an invoice into a Factur-X PDF/A-3."""
    _fonts()
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4, LETTER
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    w = LABELS[lang]
    c_ = COLON[lang]
    size = LETTER if locale.lower()[:5] in ("en-us", "en-ca", "fr-ca") else A4
    width, height = size
    m = 56  # the page margin
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=size, pageCompression=1)
    title = {"invoice": w["invoice"], "credit_note": w["credit_note"], "receipt": w["receipt"]}[doc.kind]
    cv.setTitle(f"{title} {doc.number}")
    cv.setAuthor(doc.seller.name)
    cv.setSubject(doc.line)
    cv.setCreator("Cappy")
    day = lambda t: date_of(t, tz, lang, locale)  # noqa: E731
    cash = lambda v: money(v, doc.currency, lang)  # noqa: E731

    def text(x, y, s, font="Archivo", size=9.5, color=INK, right=False):  # noqa: ANN001, ANN202
        cv.setFont(font, size)
        cv.setFillColor(HexColor(color))
        (cv.drawRightString if right else cv.drawString)(x, y, s)

    def wrap(s: str, font: str, size: float, max_w: float) -> list[str]:
        out, cur = [], ""
        for word in s.split():
            # A word wider than the column (an email, a long register entry)
            # is cut by character, so it never runs into the next column.
            while stringWidth(word, font, size) > max_w:
                cut = next(i for i in range(len(word), 0, -1) if stringWidth(word[:i], font, size) <= max_w)
                if cur:
                    out.append(cur)
                    cur = ""
                out.append(word[:cut])
                word = word[cut:]
            nxt = f"{cur} {word}".strip()
            if stringWidth(nxt, font, size) <= max_w or not cur:
                cur = nxt
            else:
                out.append(cur)
                cur = word
        return out + ([cur] if cur else [])

    # Head: the wordmark, the document's name and number.
    y = height - m
    text(m, y - 24, "Cappy", font="Bodoni", size=30)
    text(width - m, y - 12, title, font="Archivo-Bold", size=20, right=True)
    text(width - m, y - 28, doc.number, size=9.5, color=INK3, right=True)

    # Summary: the amount and its status, like Stripe's "Paid" block.
    y -= 64
    cv.setFillColor(HexColor(SUNKEN))
    cv.roundRect(m, y - 64, width - 2 * m, 64, 12, stroke=0, fill=1)
    big = cash(doc.gross if doc.kind != "receipt" else doc.charged - doc.refunded)
    text(m + 20, y - 34, big, font="Archivo-Bold", size=22)
    status = {
        "invoice": w["paid_by_withholding"].format(date=day(doc.issued_at)),
        "credit_note": f"{w['refunded_cn']} · {w['corrects'].format(number=doc.corrects, date=day(doc.corrects_date or doc.issued_at))}",
        "receipt": w["paid_by_card"],
    }[doc.kind]
    text(m + 20, y - 51, status, size=9, color=INK3)
    pill = w["paid"] if doc.kind != "credit_note" else w["refunded_cn"]
    pw = stringWidth(pill, "Archivo-SemiBold", 8.5) + 20
    cv.setFillColor(HexColor(MONEY))
    cv.roundRect(width - m - 20 - pw, y - 40, pw, 18, 9, stroke=0, fill=1)
    text(width - m - 30, y - 34.5, pill, font="Archivo-SemiBold", size=8.5, color="#ffffff", right=True)

    # Facts: date, date of service, booking reference.
    y -= 96
    date_label = {"invoice": w["date"], "credit_note": w["date_cn"], "receipt": w["date_receipt"]}[doc.kind]
    facts = [(date_label, day(doc.issued_at))]
    if doc.kind != "receipt" or doc.service_start:
        start = doc.service_start or doc.issued_at
        end = doc.service_end or start
        facts.append((w["service_date"], " – ".join(dict.fromkeys((day(start), day(end))))))
    if doc.booking_id:
        facts.append((w["booking"], doc.booking_id))
    col = (width - 2 * m) / 3
    for i, (k, v) in enumerate(facts):
        text(m + i * col, y, k, size=8.5, color=INK3)
        text(m + i * col, y - 14, v, font="Archivo-SemiBold", size=10)

    # Who from, who to.
    y -= 44

    def party(x: float, heading: str, p: Party, extra: list[str]) -> float:
        text(x, y, heading, size=8.5, color=INK3)
        yy = y - 15
        text(x, yy, p.name, font="Archivo-SemiBold", size=10)
        for line in [*_lines(p.address), *extra]:
            yy -= 13
            text(x, yy, line, size=9.5)
        return yy

    seller_ids = [
        x
        for x in (
            f"{w['vat_id']}{c_} {doc.seller.vat_id}" if doc.seller.vat_id else "",
            f"{w['tax_number']}{c_} {doc.seller.tax_number}" if doc.seller.tax_number else "",
        )
        if x
    ]
    buyer_ids = [f"{w['vat_id']}{c_} {doc.buyer.vat_id}"] if doc.buyer.vat_id else []
    y1 = party(m, w["from"], doc.seller, seller_ids)
    y2 = party(m + (width - 2 * m) / 2, w["to"], doc.buyer, buyer_ids) if doc.buyer.name else y1

    # The line(s) and the tax block.
    y = min(y1, y2) - 34
    cv.setStrokeColor(HexColor(LINE))
    cv.setLineWidth(0.75)
    right = width - m
    if doc.kind == "receipt":
        cols = [(m, w["service"], False), (right, w["amount"], True)]
    else:
        cols = [
            (m, w["service"], False),
            (right - 190, w["qty"], True),
            (right - 120, w["vat"], True),
            (right, w["amount"], True),
        ]
    for x, label, r in cols:
        text(x, y, label, size=8.5, color=INK3, right=r)
    y -= 8
    cv.line(m, y, right, y)
    rows: list[tuple[str, str, str, str]]
    if doc.kind == "receipt":
        rows = [(doc.line, "", "", cash(doc.charged))]
        if doc.refunded:
            rows.append((w["refunded"], "", "", cash(-doc.refunded)))
    else:
        rate = "—" if doc.treatment != "standard" else pct(doc.vat_rate_bps, lang)
        rows = [(doc.line, "1", rate, cash(doc.net))]
    for desc, qty, rate_s, amount in rows:
        y -= 18
        lines = wrap(desc, "Archivo", 10, right - 230 - m if doc.kind != "receipt" else right - 120 - m)
        text(m, y, lines[0], size=10)
        if doc.kind != "receipt":
            text(right - 190, y, qty, size=10, right=True)
            text(right - 120, y, rate_s, size=10, right=True)
        text(right, y, amount, size=10, right=True)
        for extra in lines[1:]:
            y -= 13
            text(m, y, extra, size=10)
        y -= 10
        cv.line(m, y, right, y)
    if doc.kind == "receipt" and doc.fee:
        y -= 14
        text(m, y, w["includes_fee"].format(fee=cash(doc.fee)), size=8.5, color=INK3)

    # Totals, right aligned.
    y -= 26
    if doc.kind == "receipt":
        totals = [(w["total_paid"], cash(doc.charged - doc.refunded), True)]
    else:
        tax_word = TAX.get(lang, "USt")
        vat_label = (
            f"{tax_word} {pct(doc.vat_rate_bps, lang)}"
            if doc.treatment == "standard"
            else f"{tax_word} 0{'%' if lang == 'en' else ' %'}"
        )
        totals = [
            (w["net"], cash(doc.net), False),
            (vat_label, cash(doc.vat), False),
            (w["total"], cash(doc.gross), True),
        ]
    for label, value, strong in totals:
        font = "Archivo-Bold" if strong else "Archivo"
        text(right - 150, y, label, font=font, size=10.5 if strong else 10, color=INK if strong else INK3, right=True)
        text(right, y, value, font=font, size=10.5 if strong else 10, right=True)
        y -= 18

    # Notes: why no VAT, what the credit note corrects, the receipt's nature.
    y -= 10
    notes = list(doc.notes)
    if doc.kind == "receipt":
        notes.append(w["receipt_note"])
    for note in notes:
        for line in wrap(note, "Archivo", 9, width - 2 * m):
            text(m, y, line, size=9, color=INK3)
            y -= 12
        y -= 4

    # Footer: every legal detail of the issuer (§ 35a GmbHG business letter).
    left = [doc.seller.name, *_lines(doc.seller.address)]
    mid = [
        x
        for x in (
            f"{w['register']}{c_} {doc.seller_register}" if doc.seller_register else "",
            f"{w['directors']}{c_} {doc.seller_directors}" if doc.seller_directors else "",
            doc.seller_email,
        )
        if x
    ]
    # Each column is wrapped to its own width first; the footer then grows
    # upwards from just above the bottom line by its tallest column, so it
    # never runs into the next column or the "Page 1 of 1" line.
    columns = [
        [part for line in block for part in wrap(line, "Archivo", 7.5, col - 12)] for block in (left, mid, seller_ids)
    ]
    fy = m + 12 + (max(len(c) for c in columns) - 1) * 10
    cv.line(m, fy + 14, right, fy + 14)
    for i, parts in enumerate(columns):
        for k, part in enumerate(parts):
            text(m + i * col, fy - k * 10, part, size=7.5, color=INK3)
    bottom = w["e_invoice"] if doc.kind != "receipt" else ""
    if bottom:
        text(m, m - 6, bottom, size=7, color=INK3)
    text(right, m - 6, w["page"], size=7, color=INK3, right=True)
    cv.showPage()
    cv.save()
    return buf.getvalue()


def factur_x(pdf_bytes: bytes, xml: bytes, *, lang: str, title: str) -> bytes:
    """A Factur-X (ZUGFeRD 2) PDF/A-3: the XML checked against the EN 16931
    schema and attached as factur-x.xml. The base PDF embeds all its fonts;
    no veraPDF run here (docs/research/2026-10-invoices.md)."""
    from facturx import generate_from_binary

    return generate_from_binary(
        pdf_bytes,
        xml,
        flavor="factur-x",
        level="en16931",
        check_xsd=True,
        lang={"de": "de-DE", "en": "en", "fr": "fr-FR"}[lang],
        pdf_metadata={"author": "Cappy", "title": title, "subject": title, "keywords": "Factur-X, invoice"},
    )
